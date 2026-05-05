#!/usr/bin/env python3
"""Refresh the tau2-bench Telecom leaderboard snapshot.

Two sources used end-to-end:

  1. `https://raw.githubusercontent.com/sierra-research/tau2-bench/main/
     web/leaderboard/public/submissions/`
     Canonical per-submission aggregate metadata (`submission.json`) plus
     the list of submission IDs (`manifest.json`). Schema is committed at
     `schema.json`.
  2. `https://sierra-tau-bench-public.s3.us-west-2.amazonaws.com/submissions/`
     Public S3 bucket holding per-trial trajectories:
       submissions/<sub_id>/trajectories/<file>.json
     Each telecom trajectory file is `{timestamp, info, tasks[114],
     simulations[114 * num_trials]}`. Each simulation carries `task_id`,
     `trial`, and `reward_info.reward` in {0.0, 1.0} — the per-trial
     pass/fail signal.

This script only collects the text-mode Telecom domain (114 standard
tasks with a gpt-4.1 / gpt-5.2 user simulator). Voice-mode submissions
(different schema: results.json + audio) and the `telecom-workflow` /
`no-user` ablation variants are skipped.

Outputs (all under this directory):
  leaderboard.json           # overview rows derived from submission.json files
  rows/<slug>.json           # per-row metadata + per-task stats
  rows_index.json            # one-line summary per row, sorted by pass^1
  per_task_matrix.json       # {task: {row_slug: {pass_rate, n_trials, n_success}}}

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-details   # reuse existing rows/*.json
  python refresh.py --workers 8      # more parallelism
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent

GH_RAW = (
    "https://raw.githubusercontent.com/sierra-research/tau2-bench/main/"
    "web/leaderboard/public/submissions"
)
S3_BASE = "https://sierra-tau-bench-public.s3.us-west-2.amazonaws.com"
S3_LIST = f"{S3_BASE}/?list-type=2&prefix=submissions"


def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "tau2-bench-leaderboard-refresh/0.1"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Step 1: manifest + per-submission aggregate metadata
# --------------------------------------------------------------------------- #
def load_manifest() -> list[str]:
    """Return ordered list of submission IDs (standard + legacy). Skip voice."""
    m = json.loads(fetch(f"{GH_RAW}/manifest.json"))
    subs: list[str] = []
    subs.extend(m.get("submissions") or [])
    subs.extend(m.get("legacy_submissions") or [])
    # Voice submissions use a different schema (results.json + audio).
    return subs


def load_submission(sub_id: str) -> dict | None:
    try:
        return json.loads(fetch(f"{GH_RAW}/{sub_id}/submission.json"))
    except Exception as e:
        print(f"  ! {sub_id}: submission.json fetch failed: {e}", file=sys.stderr)
        return None


def has_telecom_results(sub: dict) -> bool:
    r = (sub.get("results") or {}).get("telecom") or {}
    return r.get("pass_1") is not None


def scrape_leaderboard(sub_ids: list[str]) -> list[dict]:
    """Fetch every submission.json and flatten into overview rows.

    Only rows with a non-null `results.telecom.pass_1` are kept.
    """
    rows: list[dict] = []
    for sub_id in sub_ids:
        sub = load_submission(sub_id)
        if sub is None:
            continue
        if not has_telecom_results(sub):
            continue
        t = sub["results"]["telecom"]
        rows.append(
            {
                "submission_id": sub_id,
                "model": sub.get("model_name"),
                "model_organization": sub.get("model_organization"),
                "submitting_organization": sub.get("submitting_organization"),
                "submission_date": sub.get("submission_date"),
                "submission_type": sub.get("submission_type"),
                "is_new": sub.get("is_new"),
                "trajectories_available": sub.get("trajectories_available", False),
                "trajectory_file": (sub.get("trajectory_files") or {}).get("telecom"),
                "reasoning_effort": sub.get("reasoning_effort"),
                "methodology": sub.get("methodology") or {},
                "model_release": sub.get("model_release") or {},
                "pass_1": t.get("pass_1"),
                "pass_2": t.get("pass_2"),
                "pass_3": t.get("pass_3"),
                "pass_4": t.get("pass_4"),
                "cost": t.get("cost"),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Step 2: resolve telecom trajectory file on S3
# --------------------------------------------------------------------------- #
_TELECOM_BAD_SUBSTRS = (
    "telecom-workflow",  # workflow ablation subset
    "no-user",           # includes no-user-op and no-user variants
    "no_user",
)


def _is_standard_telecom(key: str) -> bool:
    """A trajectory is `telecom` domain & not an ablation variant."""
    low = key.lower()
    if "telecom" not in low:
        return False
    if not low.endswith(".json"):
        return False
    if "/trajectories/" not in low:
        return False
    for bad in _TELECOM_BAD_SUBSTRS:
        if bad in low:
            return False
    return True


def list_s3_trajectory_keys(sub_id: str) -> list[str]:
    xml = fetch(f"{S3_LIST}/{sub_id}/trajectories/").decode("utf-8", errors="replace")
    return re.findall(r"<Key>([^<]+)</Key>", xml)


def resolve_telecom_file(row: dict) -> str | None:
    sub_id = row["submission_id"]
    declared = row.get("trajectory_file")
    if declared:
        return declared
    try:
        keys = list_s3_trajectory_keys(sub_id)
    except Exception as e:
        print(f"  ! {sub_id}: S3 list failed: {e}", file=sys.stderr)
        return None
    candidates = [k for k in keys if _is_standard_telecom(k)]
    if not candidates:
        return None
    # Prefer `_telecom_default_` > `_telecom_base_` > anything else,
    # then the longest filename (usually most specific).
    def score(k: str) -> tuple[int, int]:
        low = k.lower()
        if "_telecom_default_" in low:
            pref = 3
        elif "_telecom_base_" in low:
            pref = 2
        else:
            pref = 1
        return (pref, len(k))

    best = max(candidates, key=score)
    return best.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- #
# Step 3: download + aggregate per-task
# --------------------------------------------------------------------------- #
def row_slug(sub_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", sub_id).strip("_")


def fetch_trajectory(sub_id: str, filename: str) -> dict:
    url = f"{S3_BASE}/submissions/{sub_id}/trajectories/{filename}"
    raw = fetch(url)
    return json.loads(raw.decode("utf-8", errors="replace"))


def aggregate(row: dict, traj_file: str) -> dict:
    sub_id = row["submission_id"]
    d = fetch_trajectory(sub_id, traj_file)

    info = d.get("info") or {}
    tasks = d.get("tasks") or []
    sims = d.get("simulations") or []

    task_id_to_name = {}
    for t in tasks:
        tid = t.get("id")
        if tid:
            task_id_to_name[tid] = tid

    per_task: dict[str, list[dict]] = defaultdict(list)
    for s in sims:
        tid = s.get("task_id")
        if not tid:
            continue
        reward = (s.get("reward_info") or {}).get("reward")
        per_task[tid].append(
            {
                "trial": s.get("trial"),
                "reward": float(reward) if reward is not None else None,
                "termination_reason": s.get("termination_reason"),
            }
        )

    tasks_out: list[dict] = []
    for tid in sorted(per_task):
        trials = per_task[tid]
        n_trials = len(trials)
        n_success = sum(1 for t in trials if (t["reward"] or 0.0) >= 1.0)
        tasks_out.append(
            {
                "task_id": tid,
                "n_trials": n_trials,
                "n_success": n_success,
                "pass_rate": (n_success / n_trials) if n_trials else 0.0,
            }
        )

    total_trials = sum(t["n_trials"] for t in tasks_out)
    total_successes = sum(t["n_success"] for t in tasks_out)

    return {
        "slug": row_slug(sub_id),
        "submission_id": sub_id,
        "model": row["model"],
        "model_organization": row["model_organization"],
        "submitting_organization": row["submitting_organization"],
        "submission_date": row["submission_date"],
        "reasoning_effort": row.get("reasoning_effort"),
        "pass_1": row["pass_1"],
        "pass_2": row["pass_2"],
        "pass_3": row["pass_3"],
        "pass_4": row["pass_4"],
        "cost": row["cost"],
        "user_simulator": (row.get("methodology") or {}).get("user_simulator"),
        "tau2_bench_version": (row.get("methodology") or {}).get("tau2_bench_version"),
        "evaluation_date": (row.get("methodology") or {}).get("evaluation_date"),
        "trajectory_file": traj_file,
        "trajectory_url": (
            f"{S3_BASE}/submissions/{sub_id}/trajectories/{traj_file}"
        ),
        "declared_num_trials": info.get("num_trials"),
        "git_commit": info.get("git_commit"),
        "num_tasks": len(tasks_out),
        "total_trials": total_trials,
        "total_successes": total_successes,
        "recomputed_pass_rate": (
            total_successes / total_trials if total_trials else None
        ),
        "tasks": tasks_out,
    }


def fetch_all_details(
    rows: list[dict],
    resolved: dict[str, str],
    workers: int,
) -> dict[str, dict]:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)

    jobs = [(row, resolved[row["submission_id"]]) for row in rows if row["submission_id"] in resolved]

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(aggregate, row, traj_file): row
            for row, traj_file in jobs
        }
        for i, fut in enumerate(as_completed(futures), 1):
            row = futures[fut]
            try:
                entry = fut.result()
            except Exception as e:
                print(
                    f"  [{i}/{len(jobs)}] FAIL {row['submission_id']}: {e}",
                    file=sys.stderr,
                )
                continue
            (rows_dir / f"{entry['slug']}.json").write_text(
                json.dumps(entry, indent=2)
            )
            results[entry["slug"]] = entry
            rp = entry["recomputed_pass_rate"]
            rp_str = f"{rp:.3f}" if rp is not None else "n/a"
            print(
                f"  [{i}/{len(jobs)}] {entry['slug']}: "
                f"{entry['num_tasks']} tasks, "
                f"{entry['total_successes']}/{entry['total_trials']} trials, "
                f"recomputed={rp_str} (advertised pass^1={entry['pass_1']})"
            )
    return results


# --------------------------------------------------------------------------- #
# Step 4: indexes
# --------------------------------------------------------------------------- #
def build_matrix(rows_data: dict[str, dict]) -> dict:
    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    all_tasks: set[str] = set()
    for slug, row in rows_data.items():
        for t in row["tasks"]:
            all_tasks.add(t["task_id"])
            matrix[t["task_id"]][slug] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
            }
    return {"tasks": sorted(all_tasks), "matrix": dict(matrix)}


def build_rows_index(
    rows: list[dict],
    resolved: dict[str, str],
    rows_data: dict[str, dict],
) -> dict:
    out_rows: list[dict] = []
    missing: list[dict] = []
    for row in rows:
        sub_id = row["submission_id"]
        slug = row_slug(sub_id)
        traj = resolved.get(sub_id)
        entry = rows_data.get(slug)

        pass_1 = row["pass_1"]
        summary = {
            "slug": slug,
            "submission_id": sub_id,
            "model": row["model"],
            "model_organization": row["model_organization"],
            "submitting_organization": row["submitting_organization"],
            "submission_date": row["submission_date"],
            "reasoning_effort": row.get("reasoning_effort"),
            "user_simulator": (row.get("methodology") or {}).get("user_simulator"),
            "pass_1": pass_1,
            "pass_2": row["pass_2"],
            "pass_3": row["pass_3"],
            "pass_4": row["pass_4"],
            "cost": row["cost"],
            "trajectory_file": traj,
            # Canonical 0–1 pass rate so cross-benchmark consumers (the
            # visualizer, in particular) can key on a single field name.
            "accuracy": (pass_1 / 100.0) if pass_1 is not None else None,
        }
        if entry:
            summary["num_tasks"] = entry["num_tasks"]
            summary["total_trials"] = entry["total_trials"]
            summary["declared_num_trials"] = entry["declared_num_trials"]
            summary["recomputed_pass_rate"] = entry["recomputed_pass_rate"]
            out_rows.append(summary)
        else:
            missing.append(summary)
    out_rows.sort(key=lambda r: -(r["pass_1"] or 0))
    missing.sort(key=lambda r: -(r["pass_1"] or 0))
    return {
        "num_rows": len(rows),
        "num_with_detail": len(out_rows),
        "num_missing_detail": len(missing),
        "rows": out_rows,
        "missing_detail": missing,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-details", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    print("=" * 72)
    print("tau2-bench telecom leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/4] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/4] loading manifest + submission.json files")
        sub_ids = load_manifest()
        print(f"  {len(sub_ids)} submission IDs in manifest (text + legacy)")
        rows = scrape_leaderboard(sub_ids)
        leaderboard_path.write_text(
            json.dumps(
                {
                    "source": "github.com/sierra-research/tau2-bench",
                    "benchmark": "tau2-bench-telecom",
                    "num_entries": len(rows),
                    "schema": {
                        "submission_id": "Canonical tau2-bench submission ID (model_org_date)",
                        "model": "Model display name",
                        "pass_1": "Pass^1 (avg-per-trial) success rate, percent",
                        "pass_2": "Pass^2 metric, percent",
                        "pass_3": "Pass^3 metric, percent",
                        "pass_4": "Pass^4 — all 4 trials pass, percent",
                        "cost": "Average USD cost per trajectory",
                        "trajectory_file": "Filename in submissions/<id>/trajectories/",
                        "trajectories_available": "Whether submission.json declares trajectories",
                        "methodology.user_simulator": "LLM driving the user side of the conversation",
                        "methodology.tau2_bench_version": "Library version used",
                        "reasoning_effort": "Reasoning effort setting if applicable (high/low/none/enabled)",
                    },
                    "entries": rows,
                },
                indent=2,
            )
        )
        print(f"  -> wrote leaderboard.json ({len(rows)} entries with telecom results)")

    print("[2/4] resolving telecom trajectory filenames")
    resolved: dict[str, str] = {}
    missing_trajs: list[str] = []
    for row in rows:
        sub_id = row["submission_id"]
        f = resolve_telecom_file(row)
        if f:
            resolved[sub_id] = f
            src = "declared" if row.get("trajectory_file") else "s3-discovered"
            print(f"  ok   {sub_id:55s} {src:15s} {f}")
        else:
            missing_trajs.append(sub_id)
            print(f"  miss {sub_id}")
    print(f"  resolved {len(resolved)}/{len(rows)} trajectories")

    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    if args.skip_details:
        print("[3/4] skip detail fetch — reading existing rows/*.json")
        rows_data: dict[str, dict] = {}
        for f in rows_dir.glob("*.json"):
            d = json.loads(f.read_text())
            rows_data[d["slug"]] = d
    else:
        print(f"[3/4] downloading {len(resolved)} trajectory files ({args.workers} workers)")
        rows_data = fetch_all_details(rows, resolved, args.workers)

    print("[4/4] building rows_index.json + per_task_matrix.json")
    (HERE / "rows_index.json").write_text(
        json.dumps(build_rows_index(rows, resolved, rows_data), indent=2)
    )
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(build_matrix(rows_data), indent=2)
    )

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list(rows_dir.glob("*.json")))
    print(f"  rows/  ({n} files)")


if __name__ == "__main__":
    main()
