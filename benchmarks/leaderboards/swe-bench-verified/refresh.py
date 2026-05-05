#!/usr/bin/env python3
"""Refresh the SWE-bench Verified leaderboard snapshot.

Sources used end-to-end:

  1. https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json
     A Jekyll-style data file with every leaderboard row across all SWE-bench
     variants. We keep the `Verified` slice (~180 rows). Each row has a
     `folder` pointer into SWE-bench/experiments.
  2. https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/<split>/<folder>/...
     Per-submission evaluation output. Two schemas in the wild:
       - `results/results.json` with a `resolved` list of instance IDs
         (classic submissions, stored under `evaluation/verified/`).
       - `per_instance_details.json` with `{instance_id: {resolved, cost,
         api_calls}}` (maintainer `mini-*` baselines, stored under
         `evaluation/bash-only/`, but still listed on the Verified board).
     SWE-bench Verified is pass@1 — n_trials == 1 per task.
  3. https://datasets-server.huggingface.co/rows?dataset=SWE-bench/SWE-bench_Verified&...
     Canonical list of 500 instance IDs, used as the task universe.

Outputs (all under this directory):
  leaderboard.json           # overview rows (Verified slice)
  rows/<folder>.json         # per-row: metadata + per-task stats (500 tasks)
  rows_index.json            # sorted summary, with recomputed_pass_rate
  per_task_matrix.json       # {task: {row_slug: {pass_rate, n_trials, n_success}}}

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-details   # reuse rows/*.json
  python refresh.py --workers 16     # adjust fetch parallelism
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARDS_URL = (
    "https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json"
)
EXPERIMENTS_RAW = "https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation"
# Submissions folders can live under either of these splits:
CANDIDATE_SPLITS = ("verified", "bash-only")
LEADERBOARD_NAME = "Verified"

HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=SWE-bench%2FSWE-bench_Verified&config=default&split=test"
    "&offset={offset}&length={length}"
)
HF_TOTAL_INSTANCES = 500


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "swe-bench-leaderboard-refresh/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def fetch_json(url: str) -> object:
    return json.loads(fetch(url))


# --------------------------------------------------------------------------- #
# Step 1: scrape swe-bench.github.io leaderboards.json (Verified slice)
# --------------------------------------------------------------------------- #
def scrape_leaderboard() -> list[dict]:
    data = fetch_json(LEADERBOARDS_URL)
    if not isinstance(data, dict) or "leaderboards" not in data:
        raise RuntimeError("Unexpected leaderboards.json shape")
    for lb in data["leaderboards"]:
        if lb.get("name") == LEADERBOARD_NAME:
            return lb["results"]
    raise RuntimeError(f"Leaderboard {LEADERBOARD_NAME!r} not found")


def _parse_tags(tags: list[str]) -> dict:
    """Best-effort split of `tags` strings like 'Model: foo', 'Org: bar'."""
    out: dict = {"model": [], "org": [], "system": []}
    for raw in tags or []:
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        key = k.strip().lower()
        val = v.strip()
        if key == "model":
            out["model"].append(val)
        elif key == "org":
            out["org"].append(val)
        elif key == "system":
            out["system"].append(val)
    return out


def write_leaderboard(rows: list[dict], out: Path) -> None:
    out.write_text(
        json.dumps(
            {
                "source_url": LEADERBOARDS_URL,
                "benchmark": "swe-bench",
                "split": "verified",
                "num_entries": len(rows),
                "schema": {
                    "folder": "Submission folder in SWE-bench/experiments (also our row slug)",
                    "name": "Display name",
                    "date": "Submission date (YYYY-MM-DD)",
                    "resolved": "Aggregate % of instances resolved (0-100)",
                    "checked": "Whether maintainers verified the submission",
                    "os_model": "Open-source model",
                    "os_system": "Open-source agent/system",
                    "site": "Submission homepage / repo",
                    "logo": "Logo URL list",
                    "logs": "S3 path to execution logs",
                    "trajs": "S3 path to trajectories (if released)",
                    "tags": "Raw tag strings ('Model: X', 'Org: Y', 'System: Z')",
                    "cost / instance_cost / instance_calls": "Reported cost metrics (often null)",
                    "warning": "Maintainer warning string (e.g. contamination flag)",
                },
                "entries": rows,
            },
            indent=2,
        )
    )
    print(f"  -> wrote {out.relative_to(HERE)} ({len(rows)} entries)")


# --------------------------------------------------------------------------- #
# Step 2: per-row detail: fetch per-instance results for each submission
# --------------------------------------------------------------------------- #
def _candidate_urls(folder: str) -> list[str]:
    """Known result-file locations, in priority order."""
    urls: list[str] = []
    for split in CANDIDATE_SPLITS:
        urls.append(f"{EXPERIMENTS_RAW}/{split}/{folder}/results/results.json")
        urls.append(f"{EXPERIMENTS_RAW}/{split}/{folder}/per_instance_details.json")
    return urls


def _parse_result_payload(data: object) -> set[str]:
    """Extract the resolved-instance set from either known schema.

    Schema A (classic `results/results.json`):
        {"resolved": ["instance_id", ...], "generated": [...], ...}
    Schema B (`per_instance_details.json`):
        {"instance_id": {"resolved": true/false, "cost": ..., ...}, ...}
    """
    if isinstance(data, dict):
        if isinstance(data.get("resolved"), list):
            return set(data["resolved"])
        # Per-instance details dict: keys are instance IDs, values carry bool
        if data and all(isinstance(v, dict) for v in data.values()):
            return {k for k, v in data.items() if v.get("resolved") is True}
    raise RuntimeError("unrecognized result payload shape")


def fetch_row_results(row: dict) -> tuple[dict, set[str], str]:
    last_err: Exception | None = None
    for url in _candidate_urls(row["folder"]):
        try:
            data = fetch_json(url)
        except Exception as e:
            last_err = e
            continue
        try:
            return row, _parse_result_payload(data), url
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f"no usable results file for {row['folder']}: {last_err}"
    )


def fetch_all_details(rows: list[dict], workers: int) -> tuple[dict[str, dict], list[str]]:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)

    results: dict[str, dict] = {}
    missing: list[str] = []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_row_results, row): row for row in rows}
        for i, fut in enumerate(as_completed(futures), 1):
            row = futures[fut]
            slug = row["folder"]
            try:
                _, resolved, url = fut.result()
            except Exception:
                # Common case: maintainers withheld per-instance data
                # (e.g., submissions flagged by git_peek_suspicious_commits).
                missing.append(slug)
                continue
            entry = {
                "slug": slug,
                "folder": slug,
                "name": row.get("name"),
                "date": row.get("date"),
                "resolved_pct": row.get("resolved"),
                "accuracy": (row["resolved"] / 100.0) if row.get("resolved") is not None else None,
                "checked": row.get("checked"),
                "os_model": row.get("os_model"),
                "os_system": row.get("os_system"),
                "site": row.get("site"),
                "logo": row.get("logo"),
                "logs": row.get("logs"),
                "trajs": row.get("trajs"),
                "cost": row.get("cost"),
                "instance_cost": row.get("instance_cost"),
                "instance_calls": row.get("instance_calls"),
                "warning": row.get("warning"),
                "tags": row.get("tags") or [],
                "parsed_tags": _parse_tags(row.get("tags") or []),
                "results_url": url,
                "num_resolved": len(resolved),
                "resolved_instance_ids": sorted(resolved),
            }
            (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))
            results[slug] = entry
            if i % 20 == 0 or i == len(rows):
                print(f"  [{i}/{len(rows)}] fetched ({len(results)} ok, {len(missing)} missing)")

    if missing:
        print(
            f"  {len(missing)} row(s) have no per-instance data in SWE-bench/experiments:"
        )
        for slug in missing:
            print(f"    - {slug}")
    return results, missing


# --------------------------------------------------------------------------- #
# Step 3: task universe, per-row task arrays, matrix, index
# --------------------------------------------------------------------------- #
def hf_task_universe() -> list[str]:
    """All 500 canonical SWE-bench Verified instance IDs, fetched from HF."""
    ids: list[str] = []
    offset = 0
    page = 100
    while offset < HF_TOTAL_INSTANCES:
        url = HF_ROWS_URL.format(offset=offset, length=page)
        data = fetch_json(url)
        rows = data.get("rows", []) if isinstance(data, dict) else []
        if not rows:
            break
        for r in rows:
            iid = r.get("row", {}).get("instance_id")
            if iid:
                ids.append(iid)
        offset += len(rows)
    # De-dup while preserving first-seen order (dataset already has unique IDs)
    seen, out = set(), []
    for iid in ids:
        if iid not in seen:
            seen.add(iid)
            out.append(iid)
    return sorted(out)


def task_universe(rows_data: dict[str, dict]) -> list[str]:
    """Canonical task universe; falls back to union if HF is unreachable."""
    try:
        ids = hf_task_universe()
        if len(ids) == HF_TOTAL_INSTANCES:
            print(f"  task universe: {len(ids)} instances (HF canonical)")
            return ids
        print(
            f"  WARN: HF returned {len(ids)} ids (expected {HF_TOTAL_INSTANCES}); "
            f"falling back to union"
        )
    except Exception as e:
        print(f"  WARN: HF fetch failed: {e}; falling back to union")
    all_ids: set[str] = set()
    for row in rows_data.values():
        all_ids.update(row.get("resolved_instance_ids") or [])
    return sorted(all_ids)


def attach_per_task_stats(rows_data: dict[str, dict], tasks: list[str]) -> None:
    """Materialize per-task {n_trials=1, n_success, pass_rate} for every task on every row."""
    for row in rows_data.values():
        resolved = set(row["resolved_instance_ids"])
        row["num_tasks"] = len(tasks)
        row["total_trials"] = len(tasks)  # pass@1
        row["total_successes"] = len(resolved)
        row["tasks"] = [
            {
                "task_name": t,
                "n_trials": 1,
                "n_success": 1 if t in resolved else 0,
                "pass_rate": 1.0 if t in resolved else 0.0,
            }
            for t in tasks
        ]


def build_matrix(rows_data: dict[str, dict], tasks: list[str]) -> dict:
    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    for slug, row in rows_data.items():
        for t in row["tasks"]:
            matrix[t["task_name"]][slug] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
            }
    return {"tasks": tasks, "matrix": dict(matrix)}


def build_rows_index(rows_data: dict[str, dict]) -> list[dict]:
    out = []
    for slug, row in rows_data.items():
        recomputed = (
            row["total_successes"] / row["total_trials"] if row["total_trials"] else None
        )
        out.append(
            {
                "slug": slug,
                "folder": row["folder"],
                "name": row["name"],
                "date": row["date"],
                "accuracy": row["accuracy"],
                "checked": row["checked"],
                "os_model": row["os_model"],
                "os_system": row["os_system"],
                "num_tasks": row["num_tasks"],
                "total_trials": row["total_trials"],
                "num_resolved": row["num_resolved"],
                "recomputed_pass_rate": recomputed,
            }
        )
    out.sort(key=lambda r: -(r["accuracy"] or 0))
    return out


# --------------------------------------------------------------------------- #
# Rewrite detail files with attached task arrays (after universe is known)
# --------------------------------------------------------------------------- #
def write_detail_files(rows_data: dict[str, dict]) -> None:
    rows_dir = HERE / "rows"
    for slug, row in rows_data.items():
        (rows_dir / f"{slug}.json").write_text(json.dumps(row, indent=2))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-scrape", action="store_true", help="Reuse existing leaderboard.json")
    ap.add_argument("--skip-details", action="store_true", help="Reuse existing rows/*.json")
    ap.add_argument("--workers", type=int, default=8, help="Concurrent detail fetches (default 8)")
    args = ap.parse_args()

    print("=" * 72)
    print("SWE-bench Verified leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/3] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/3] scraping swe-bench.github.io leaderboards.json")
        rows = scrape_leaderboard()
        write_leaderboard(rows, leaderboard_path)

    if args.skip_details:
        print("[2/3] skip detail fetch — loading existing rows/*.json")
        rows_data = {}
        for f in (HERE / "rows").glob("*.json"):
            d = json.loads(f.read_text())
            rows_data[d["slug"]] = d
        missing = [r["folder"] for r in rows if r["folder"] not in rows_data]
    else:
        print(f"[2/3] fetching per-row detail files ({args.workers} workers, {len(rows)} rows)")
        rows_data, missing = fetch_all_details(rows, args.workers)

    print("[3/3] building task universe + per_task_matrix.json + rows_index.json")
    tasks = task_universe(rows_data)
    attach_per_task_stats(rows_data, tasks)
    write_detail_files(rows_data)

    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows_data),
                "num_tasks": len(tasks),
                "missing_detail": sorted(missing),
                "rows": build_rows_index(rows_data),
            },
            indent=2,
        )
    )
    matrix = build_matrix(rows_data, tasks)
    (HERE / "per_task_matrix.json").write_text(json.dumps(matrix, indent=2))

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    rows_dir = HERE / "rows"
    if rows_dir.exists():
        n = len(list(rows_dir.glob("*.json")))
        print(f"  rows/  ({n} files)")
    print(f"  tasks covered: {len(tasks)}")


if __name__ == "__main__":
    main()
