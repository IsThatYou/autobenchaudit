#!/usr/bin/env python3
"""Streaming per-benchmark audit pipeline with cleanup.

For each YAML config under configs/multi_domain_all/<domain>/<benchmark>.yaml:
  1. audit-benchmark   (skip if benchmark_audit.json + benchmark_audit_report.md exist)
  2. collect-evidence  (skip if artifact_manifest.yaml + collection_report.md exist)
  3. sample-tasks      (skip if sampled_tasks.json exists)
  4. audit-tasks       (run on first --batch pending sampled task IDs)
  5. cleanup           (rm -rf benchmark_repo_dir + benchmark_data_dir on success)

Tracking lives in configs/multi_domain_all/streaming_pipeline_tracking.json.
Use --status to print the current progress table without doing any work.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from bench_audit.evidence_collection import load_collection_config
from bench_audit.evidence_collection.runner import resolve_output_root

CONFIG_DIR = ROOT_DIR / "configs" / "multi_domain_all"
TRACKER_PATH = CONFIG_DIR / "streaming_pipeline_tracking.json"
LOCK_PATH = CONFIG_DIR / ".streaming_pipeline.lock"
PYTHON = str(ROOT_DIR / ".venv" / "bin" / "python")
RUBRIC = str(ROOT_DIR / "rubrics" / "task_rubric_ambiguity_v3.txt")

STAGES = (
    "stage_benchmark_audit",
    "stage_collect_evidence",
    "stage_sample_tasks",
    "stage_audit_tasks",
)

_print_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def discover_configs(domain: str | None, explicit: list[str]) -> list[str]:
    if explicit:
        return [str(Path(c)) for c in explicit]
    base = CONFIG_DIR / domain if domain else CONFIG_DIR
    if domain and not base.is_dir():
        sys.exit(f"Unknown domain: {domain}")
    if domain:
        files = sorted(base.glob("*.yaml"))
    else:
        files = sorted(p for p in base.glob("*/*.yaml"))
    return [str(p.relative_to(ROOT_DIR)) for p in files]


def with_tracker_lock(fn):
    """Acquire an exclusive flock on LOCK_PATH while running fn(tracker_dict)."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        tracker = read_tracker()
        result = fn(tracker)
        write_tracker(tracker)
        return result


def read_tracker() -> dict[str, Any]:
    if not TRACKER_PATH.exists():
        return {}
    try:
        return json.loads(TRACKER_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def write_tracker(tracker: dict[str, Any]) -> None:
    tracker["updated_at"] = now_iso()
    tracker["summary"] = compute_summary(tracker.get("configs", []))
    tmp = TRACKER_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tracker, indent=2) + "\n")
    os.replace(tmp, TRACKER_PATH)


def compute_summary(entries: list[dict[str, Any]]) -> dict[str, int]:
    total = len(entries)
    done = sum(1 for e in entries if e.get("overall") == "done")
    in_progress = sum(1 for e in entries if e.get("overall") == "in_progress")
    failed = sum(1 for e in entries if e.get("overall") == "failed")
    pending = total - done - in_progress - failed
    cleaned = sum(1 for e in entries if e.get("cleanup") == "done")
    freed = sum(int(e.get("repo_size_freed_mb", 0) or 0) for e in entries)
    return {
        "total": total,
        "done": done,
        "in_progress": in_progress,
        "failed": failed,
        "pending": pending,
        "cleaned": cleaned,
        "freed_mb": freed,
    }


def init_tracker(configs: list[str]) -> None:
    def _init(tracker: dict[str, Any]) -> None:
        existing_by_cfg = {e["config"]: e for e in tracker.get("configs", [])}
        new_entries = []
        for cfg in configs:
            if cfg in existing_by_cfg:
                new_entries.append(existing_by_cfg[cfg])
                continue
            try:
                bench_name = load_collection_config(cfg).benchmark_name
            except Exception:
                bench_name = Path(cfg).stem
            new_entries.append({
                "config": cfg,
                "benchmark_name": bench_name,
                "overall": "pending",
                "stage_benchmark_audit": "pending",
                "stage_collect_evidence": "pending",
                "stage_sample_tasks": "pending",
                "stage_audit_tasks": "pending",
                "cleanup": "n/a",
                "started_at": None,
                "finished_at": None,
                "repo_size_freed_mb": 0,
                "error": None,
            })
        tracker["configs"] = new_entries
        tracker.setdefault("started_at", now_iso())

    with_tracker_lock(_init)


def update_entry(config: str, **fields: Any) -> None:
    def _update(tracker: dict[str, Any]) -> None:
        for entry in tracker.get("configs", []):
            if entry["config"] == config:
                entry.update(fields)
                break

    with_tracker_lock(_update)


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def dir_size_mb(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _, files in os.walk(path, followlinks=False):
        for f in files:
            fp = Path(root) / f
            try:
                total += fp.stat(follow_symlinks=False).st_size
            except (OSError, ValueError):
                pass
    return total // (1024 * 1024)


def stage_done_outputs(stage: str, output_root: Path) -> bool:
    if stage == "stage_benchmark_audit":
        return (output_root / "benchmark_audit.json").exists() and (
            output_root / "benchmark_audit_report.md"
        ).exists()
    if stage == "stage_collect_evidence":
        return (output_root / "artifact_manifest.yaml").exists() and (
            output_root / "collection_report.md"
        ).exists()
    if stage == "stage_sample_tasks":
        return (output_root / "sampled_tasks.json").exists()
    if stage == "stage_audit_tasks":
        return False
    raise ValueError(stage)


def pending_task_ids(output_root: Path, batch: int) -> list[str]:
    sample_file = output_root / "sampled_tasks.json"
    if not sample_file.exists():
        return []
    sampled = json.loads(sample_file.read_text())
    audit_dir = output_root / "task_audits_static"
    pending = [
        tid
        for tid in sampled.get("task_ids", [])
        if not (audit_dir / f"{tid}.json").exists()
    ]
    if batch > 0:
        pending = pending[:batch]
    return pending


def run_subprocess(cmd: list[str], audit_run_dir: str) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["AUDIT_RUN_DIR"] = audit_run_dir
    proc = subprocess.run(cmd, env=env, cwd=str(ROOT_DIR))
    return proc.returncode


def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60):02d}m"


def run_pipeline_for_config(
    config: str,
    index_label: str,
    args: argparse.Namespace,
    audit_run_dir: str,
) -> bool:
    bench_cfg = load_collection_config(config)
    output_root = Path(resolve_output_root(bench_cfg))
    repo_dir = Path(bench_cfg.benchmark_repo_dir)
    data_dir = Path(bench_cfg.benchmark_data_dir)
    bench_name = bench_cfg.benchmark_name
    label = f"{index_label} {bench_name:<32}"

    update_entry(
        config,
        overall="in_progress",
        started_at=now_iso(),
        error=None,
    )

    success = True

    # Stage 1: benchmark audit
    stage = "stage_benchmark_audit"
    if not args.force and stage_done_outputs(stage, output_root):
        log(f"{label} STAGE benchmark_audit  SKIP (already done)")
        update_entry(config, **{stage: "done"})
    else:
        log(f"{label} STAGE benchmark_audit  RUNNING")
        update_entry(config, **{stage: "running"})
        cmd = [
            PYTHON, "-m", "bench_audit", "audit-benchmark",
            "--config", config,
            "--timeout", str(args.timeout),
        ]
        if args.force:
            cmd.append("--force")
        t0 = time.monotonic()
        rc = run_subprocess(cmd, audit_run_dir)
        elapsed = time.monotonic() - t0
        if rc == 0:
            log(f"{label} STAGE benchmark_audit  DONE ({fmt_duration(elapsed)})")
            update_entry(config, **{stage: "done"})
        else:
            log(f"{label} STAGE benchmark_audit  FAILED rc={rc}")
            update_entry(config, **{stage: "failed"}, overall="failed",
                         error=f"benchmark_audit exit={rc}",
                         finished_at=now_iso())
            return False

    # Stage 2: collect evidence
    stage = "stage_collect_evidence"
    if not args.force and stage_done_outputs(stage, output_root):
        log(f"{label} STAGE collect_evidence SKIP (already done)")
        update_entry(config, **{stage: "done"})
    else:
        log(f"{label} STAGE collect_evidence RUNNING")
        update_entry(config, **{stage: "running"})
        cmd = [PYTHON, "-m", "bench_audit", "collect-evidence", "--config", config]
        if args.force:
            cmd.append("--force")
        t0 = time.monotonic()
        rc = run_subprocess(cmd, audit_run_dir)
        elapsed = time.monotonic() - t0
        if rc == 0:
            log(f"{label} STAGE collect_evidence DONE ({fmt_duration(elapsed)})")
            update_entry(config, **{stage: "done"})
        else:
            log(f"{label} STAGE collect_evidence FAILED rc={rc}")
            update_entry(config, **{stage: "failed"}, overall="failed",
                         error=f"collect_evidence exit={rc}",
                         finished_at=now_iso())
            return False

    # Stage 3a: sample tasks
    stage = "stage_sample_tasks"
    if not args.force and stage_done_outputs(stage, output_root):
        log(f"{label} STAGE sample_tasks     SKIP (already done)")
        update_entry(config, **{stage: "done"})
    else:
        log(f"{label} STAGE sample_tasks     RUNNING")
        update_entry(config, **{stage: "running"})
        cmd = [
            PYTHON, str(ROOT_DIR / "scripts" / "sample_tasks.py"),
            "--config", config,
            "--max-tasks", str(args.max_tasks),
            "--seed", str(args.seed),
        ]
        if args.force:
            cmd.append("--force")
        t0 = time.monotonic()
        rc = run_subprocess(cmd, audit_run_dir)
        elapsed = time.monotonic() - t0
        if rc == 0:
            log(f"{label} STAGE sample_tasks     DONE ({fmt_duration(elapsed)})")
            update_entry(config, **{stage: "done"})
        else:
            log(f"{label} STAGE sample_tasks     FAILED rc={rc}")
            update_entry(config, **{stage: "failed"}, overall="failed",
                         error=f"sample_tasks exit={rc}",
                         finished_at=now_iso())
            return False

    # Stage 3b: audit tasks (batch)
    stage = "stage_audit_tasks"
    pending = pending_task_ids(output_root, args.batch)
    if not pending:
        log(f"{label} STAGE audit_tasks      SKIP (no pending tasks)")
        update_entry(config, **{stage: "done"})
    else:
        log(f"{label} STAGE audit_tasks      RUNNING ({len(pending)} tasks)")
        update_entry(config, **{stage: "running"})
        cmd = [
            PYTHON, "-m", "bench_audit", "audit-tasks",
            "--config", config,
            "--tasks", *pending,
            "--mode", "static",
            "--rubric-text", RUBRIC,
            "--timeout", "1000",
            "--max-workers", str(args.workers),
        ]
        t0 = time.monotonic()
        rc = run_subprocess(cmd, audit_run_dir)
        elapsed = time.monotonic() - t0
        if rc == 0:
            remaining = pending_task_ids(output_root, 0)
            status = "done" if not remaining else "partial"
            log(
                f"{label} STAGE audit_tasks      "
                f"{'DONE' if status == 'done' else f'PARTIAL ({len(remaining)} left)'} "
                f"({fmt_duration(elapsed)})"
            )
            update_entry(config, **{stage: status})
        else:
            log(f"{label} STAGE audit_tasks      FAILED rc={rc}")
            update_entry(config, **{stage: "failed"}, overall="failed",
                         error=f"audit_tasks exit={rc}",
                         finished_at=now_iso())
            return False

    # Cleanup
    if args.keep:
        log(f"{label} CLEANUP                SKIP (--keep)")
        update_entry(config, cleanup="kept (--keep)", overall="done",
                     finished_at=now_iso())
        return True

    repo_size = dir_size_mb(repo_dir)
    data_size = dir_size_mb(data_dir)
    total_freed = repo_size + data_size

    cleanup_errors = []
    for path in (repo_dir, data_dir):
        if path.exists():
            try:
                shutil.rmtree(path)
            except OSError as exc:
                cleanup_errors.append(f"{path}: {exc}")

    parent = repo_dir.parent
    if parent.exists() and parent != Path(parent.anchor):
        try:
            parent.rmdir()
        except OSError:
            pass

    if cleanup_errors:
        log(f"{label} CLEANUP                ERROR: {'; '.join(cleanup_errors)}")
        update_entry(
            config,
            cleanup="failed",
            overall="done",
            repo_size_freed_mb=total_freed,
            finished_at=now_iso(),
            error="; ".join(cleanup_errors),
        )
    else:
        log(f"{label} CLEANUP                freed {total_freed} MB")
        update_entry(
            config,
            cleanup="done",
            overall="done",
            repo_size_freed_mb=total_freed,
            finished_at=now_iso(),
        )

    return True


def cmd_status() -> None:
    if not TRACKER_PATH.exists():
        print(f"No tracker yet at {TRACKER_PATH}")
        return
    tracker = read_tracker()
    summary = tracker.get("summary", compute_summary(tracker.get("configs", [])))
    print(
        f"PROGRESS: {summary['done']}/{summary['total']} done, "
        f"{summary['in_progress']} in_progress, "
        f"{summary['failed']} failed, {summary['pending']} pending"
    )
    print(f"DISK FREED: {summary['freed_mb']} MB ({summary['cleaned']} benchmarks cleaned)")
    updated = tracker.get("updated_at")
    if updated:
        print(f"LAST UPDATE: {updated}")
    print()

    in_prog = [e for e in tracker.get("configs", []) if e.get("overall") == "in_progress"]
    if in_prog:
        print("IN PROGRESS:")
        for e in in_prog:
            running_stage = next(
                (s for s in STAGES if e.get(s) == "running"), "?"
            )
            started = e.get("started_at") or "?"
            print(f"  {e['benchmark_name']:<36} {running_stage}  started={started}")
        print()

    failed = [e for e in tracker.get("configs", []) if e.get("overall") == "failed"]
    if failed:
        print("FAILED:")
        for e in failed:
            failed_stage = next(
                (s for s in STAGES if e.get(s) == "failed"), "?"
            )
            print(f"  {e['benchmark_name']:<36} {failed_stage}  {e.get('error', '')}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-j", dest="parallel", type=int, default=1,
                        help="Number of benchmarks to run concurrently (default 1)")
    parser.add_argument("--workers", type=int, default=1,
                        help="--max-workers passed to audit-tasks (default 1)")
    parser.add_argument("--max-tasks", type=int, default=100,
                        help="Max sampled tasks per benchmark (default 100)")
    parser.add_argument("--batch", type=int, default=0,
                        help="Audit only first N pending tasks per benchmark (default 0 = all)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Sampling seed (default 42)")
    parser.add_argument("--timeout", type=int, default=1200,
                        help="Timeout for audit-benchmark (default 1200)")
    parser.add_argument("--domain", default=None,
                        help="Only run configs under configs/multi_domain_all/<domain>/")
    parser.add_argument("--config", action="append", default=[],
                        help="Specific config file(s); may be repeated")
    parser.add_argument("--keep", action="store_true",
                        help="Skip cleanup of benchmark_repo_dir/benchmark_data_dir")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all stages even if outputs already exist")
    parser.add_argument("--status", action="store_true",
                        help="Print tracker summary and exit")
    parser.add_argument("--reset-tracker", action="store_true",
                        help="Delete the tracker file before starting")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return 0

    if args.reset_tracker and TRACKER_PATH.exists():
        TRACKER_PATH.unlink()
        print(f"Removed {TRACKER_PATH}")

    audit_run_dir = os.environ.get(
        "AUDIT_RUN_DIR",
        str(ROOT_DIR / "data" / "multi_domain_all"),
    )

    configs = discover_configs(args.domain, args.config)
    if not configs:
        sys.exit("No configs found.")

    init_tracker(configs)

    total = len(configs)
    print(f"=== Streaming pipeline: {total} benchmarks, j={args.parallel}, "
          f"workers={args.workers}, batch={args.batch}, max_tasks={args.max_tasks} ===")
    print(f"AUDIT_RUN_DIR={audit_run_dir}")
    print(f"Tracker: {TRACKER_PATH}")
    print()

    counter = {"i": 0}
    counter_lock = threading.Lock()

    def worker(cfg: str) -> tuple[str, bool]:
        with counter_lock:
            counter["i"] += 1
            i = counter["i"]
        label = f"[{i:>3}/{total}]"
        try:
            ok = run_pipeline_for_config(cfg, label, args, audit_run_dir)
        except Exception as exc:
            log(f"{label} {cfg}  CRASH: {exc!r}")
            update_entry(cfg, overall="failed", error=repr(exc),
                         finished_at=now_iso())
            ok = False
        return cfg, ok

    passed = failed = 0
    if args.parallel <= 1:
        for cfg in configs:
            _, ok = worker(cfg)
            if ok:
                passed += 1
            else:
                failed += 1
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = [pool.submit(worker, cfg) for cfg in configs]
            for fut in as_completed(futures):
                _, ok = fut.result()
                if ok:
                    passed += 1
                else:
                    failed += 1

    print()
    print(f"=== Finished: {passed} passed, {failed} failed (of {total}) ===")
    print(f"Run `bash scripts/multi_domain_streaming_pipeline.sh --status` for the tracker view.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
