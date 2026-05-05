#!/usr/bin/env python3
"""Refresh the Terminal-Bench 2.0 leaderboard snapshot.

Two sources used end-to-end:

  1. `https://www.tbench.ai/leaderboard/terminal-bench/2.0`
     The overview page carries every leaderboard row's aggregate accuracy.
  2. `https://www.tbench.ai/leaderboard/terminal-bench/2.0/<agent>/<version>/<model@provider,...>`
     A detail page per row with the per-task pass rate (`avgResolutionRate`),
     trial count, and success count for all 89 tasks.

Both pages are Next.js server-rendered; the data is embedded in the RSC stream
as `self.__next_f.push([0, "..."])` chunks. We extract the JSON directly — no
API key needed.

Outputs (all under this directory):
  leaderboard.json           # 123 overview rows
  rows/<key>.json            # per-row: metadata + per-task stats
  per_task_matrix.json       # {task: {row_key: {pass_rate, n_trials, n_success}}}

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --workers 8      # adjust fetch parallelism
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent

BASE = "https://www.tbench.ai/leaderboard/terminal-bench/2.0"


# --------------------------------------------------------------------------- #
# Shared: Next.js RSC payload extraction
# --------------------------------------------------------------------------- #
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[\d+,("(?:[^"\\]|\\.)*")')


def fetch(url: str, retries: int = 4) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "tbench-leaderboard-refresh/2.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def rsc_payloads(html: str) -> list[str]:
    return [json.loads(m) for m in _PUSH_RE.findall(html)]


def slice_bracket_json(payload: str, key: str) -> str | None:
    """Extract a balanced JSON array value following `"<key>":`."""
    needle = f'"{key}":['
    i = payload.find(needle)
    if i < 0:
        return None
    i += len(f'"{key}":')
    depth = 0
    j = i
    in_str = False
    esc = False
    while j < len(payload):
        c = payload[j]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return payload[i : j + 1]
        j += 1
    return None


# --------------------------------------------------------------------------- #
# Step 1: scrape tbench.ai leaderboard overview
# --------------------------------------------------------------------------- #
def scrape_leaderboard() -> list[dict]:
    for payload in rsc_payloads(fetch(BASE)):
        raw = slice_bracket_json(payload, "rows")
        if raw is not None:
            return json.loads(raw)
    raise RuntimeError("Could not locate leaderboard rows in page payload")


def write_leaderboard(rows: list[dict], out: Path) -> None:
    out.write_text(
        json.dumps(
            {
                "source_url": BASE,
                "benchmark": "terminal-bench",
                "version": "2.0",
                "num_entries": len(rows),
                "schema": {
                    "agent": "Agent display name",
                    "model": "List of model display names",
                    "agentOrganization": "Organization running the agent",
                    "modelOrganization": "Organization of model provider(s)",
                    "date": "Submission date (YYYY-MM-DD)",
                    "accuracy": "Mean pass rate across trials (0-1)",
                    "stderr": "Standard error of the accuracy",
                    "integrationMethod": "API / etc.",
                    "agentUrl": "Agent homepage / repo",
                    "verified": "Whether the submission was verified by maintainers",
                    "agentName": "Agent internal slug (URL component)",
                    "agentVersion": "Agent version slug (URL component)",
                    "modelNames": "Internal model identifiers (URL component)",
                    "modelProviders": "Model provider slugs (URL component)",
                    "key": "Unique row key",
                },
                "entries": rows,
            },
            indent=2,
        )
    )
    print(f"  -> wrote {out.relative_to(HERE)} ({len(rows)} entries)")


# --------------------------------------------------------------------------- #
# Step 2: per-row detail page → per-task stats
# --------------------------------------------------------------------------- #
def detail_url(row: dict) -> str:
    agent = urllib.parse.quote(row["agentName"], safe="")
    version = urllib.parse.quote(row["agentVersion"], safe="")
    model_pairs = ",".join(
        f"{m}@{p}" for m, p in zip(row["modelNames"], row["modelProviders"])
    )
    model = urllib.parse.quote(model_pairs, safe="")
    return f"{BASE}/{agent}/{version}/{model}"


_TASK_RE = re.compile(
    r'\{"taskName":"([^"]+)","taskChecksum":"([^"]+)","nTrials":(\d+),'
    r'"avgResolutionRate":([0-9.eE+-]+),"successCount":(\d+)\}'
)


def parse_tasks(html: str) -> list[dict]:
    """Return the detail page's per-task performance list.

    The data sits inside an RSC chunk as `"data":[{"taskName":...},...]`. We
    find the chunk, extract that array, and regex the items — simpler than
    fully decoding the React tree.
    """
    for payload in rsc_payloads(html):
        if '"taskName":"' not in payload or '"successCount"' not in payload:
            continue
        raw = slice_bracket_json(payload, "data")
        if raw is None:
            continue
        items: list[dict] = []
        for tname, checksum, n, rate, ok in _TASK_RE.findall(raw):
            items.append(
                {
                    "task_name": tname,
                    "task_checksum": checksum,
                    "n_trials": int(n),
                    "n_success": int(ok),
                    "pass_rate": float(rate),
                }
            )
        if items:
            return items
    return []


def row_key_slug(row: dict) -> str:
    """Filesystem-safe unique slug for a row.

    `row["key"]` is already globally unique but can contain spaces and commas.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", row["key"]).strip("_")


def fetch_row_detail(row: dict) -> tuple[dict, list[dict], str]:
    url = detail_url(row)
    html = fetch(url)
    tasks = parse_tasks(html)
    return row, tasks, url


def fetch_all_details(rows: list[dict], workers: int) -> dict[str, dict]:
    """Fetch and store per-row detail JSONs under rows/."""
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)

    results: dict[str, dict] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_row_detail, row): row for row in rows}
        for i, fut in enumerate(as_completed(futures), 1):
            row = futures[fut]
            slug = row_key_slug(row)
            try:
                _, tasks, url = fut.result()
            except Exception as e:
                errors.append(f"{slug}: {e}")
                print(f"  [{i}/{len(rows)}] FAIL {slug}: {e}", file=sys.stderr)
                continue
            if not tasks:
                errors.append(f"{slug}: no tasks found")
                print(f"  [{i}/{len(rows)}] EMPTY {slug}", file=sys.stderr)

            entry = {
                "key": row["key"],
                "slug": slug,
                "agent": row["agent"],
                "model": row["model"],
                "agent_organization": row["agentOrganization"],
                "model_organization": row["modelOrganization"],
                "date": row["date"],
                "accuracy": row["accuracy"],
                "stderr": row["stderr"],
                "verified": row["verified"],
                "detail_url": url,
                "agent_name": row["agentName"],
                "agent_version": row["agentVersion"],
                "model_names": row["modelNames"],
                "model_providers": row["modelProviders"],
                "num_tasks": len(tasks),
                "total_trials": sum(t["n_trials"] for t in tasks),
                "total_successes": sum(t["n_success"] for t in tasks),
                "tasks": tasks,
            }
            (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))
            results[slug] = entry
            if i % 10 == 0 or i == len(rows):
                print(f"  [{i}/{len(rows)}] fetched")
    return results


# --------------------------------------------------------------------------- #
# Step 3: per-task matrix
# --------------------------------------------------------------------------- #
def build_matrix(rows_data: dict[str, dict]) -> dict:
    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    all_tasks: set[str] = set()
    for slug, row in rows_data.items():
        for t in row["tasks"]:
            all_tasks.add(t["task_name"])
            matrix[t["task_name"]][slug] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
            }
    return {"tasks": sorted(all_tasks), "matrix": dict(matrix)}


def build_rows_index(rows_data: dict[str, dict]) -> list[dict]:
    out = []
    for slug, row in rows_data.items():
        recomputed = (
            row["total_successes"] / row["total_trials"] if row["total_trials"] else None
        )
        out.append(
            {
                "slug": slug,
                "key": row["key"],
                "agent": row["agent"],
                "model": row["model"],
                "date": row["date"],
                "accuracy": row["accuracy"],
                "verified": row["verified"],
                "num_tasks": row["num_tasks"],
                "total_trials": row["total_trials"],
                "recomputed_pass_rate": recomputed,
            }
        )
    out.sort(key=lambda r: -(r["accuracy"] or 0))
    return out


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
    print("Terminal-Bench 2.0 leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/3] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/3] scraping tbench.ai leaderboard overview")
        rows = scrape_leaderboard()
        write_leaderboard(rows, leaderboard_path)

    if args.skip_details:
        print("[2/3] skip detail fetch — loading existing rows/*.json")
        rows_data = {}
        for f in (HERE / "rows").glob("*.json"):
            d = json.loads(f.read_text())
            rows_data[d["slug"]] = d
    else:
        print(f"[2/3] fetching per-row detail pages ({args.workers} workers, {len(rows)} rows)")
        rows_data = fetch_all_details(rows, args.workers)

    print("[3/3] building rows_index.json + per_task_matrix.json")
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {"num_rows": len(rows_data), "rows": build_rows_index(rows_data)}, indent=2
        )
    )
    matrix = build_matrix(rows_data)
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
    print(f"  tasks covered: {len(matrix['tasks'])}")


if __name__ == "__main__":
    main()
