#!/usr/bin/env python3
"""Refresh the SWE-bench Pro (Public) leaderboard snapshot.

Sources used end-to-end:

  1. https://labs.scale.com/leaderboard/swe_bench_pro_public
     The public leaderboard is rendered by Scale Labs' Next.js app. The
     ordered entry list is embedded in the page's RSC payload as
     `"entries":[...]`. We parse that out — no auth, no API key.
  2. https://github.com/scaleapi/SWE-bench_Pro-os (path: `traj/<folder>/eval_results.json`)
     Per-submission per-instance pass/fail (`{instance_id: bool}`, ~730 keys).
     Nine submissions have pre-graded results committed here.
  3. s3://scaleapi-results/swe-bench-pro/<folder>/eval/<instance>/_output.json
     Raw test outputs for every submission (incl. ones not on GitHub). We
     grade per SWE-bench Pro's rule: `resolved = (fail_to_pass ∪ pass_to_pass) ⊆ passed_tests`.
     Requires AWS credentials configured for the scaleapi-results bucket.
  4. https://datasets-server.huggingface.co/rows?dataset=ScaleAI/SWE-bench_Pro&...
     Canonical task universe (731 instance IDs) + `fail_to_pass` /
     `pass_to_pass` test lists used for grading.

SWE-bench Pro is pass@1 — n_trials == 1 per task.

Outputs (all under this directory):
  leaderboard.json           # ~24 leaderboard entries from Scale Labs
  rows/<folder>.json         # one per S3/GitHub submission with per-instance pass/fail
  rows_index.json            # summary of every row
  per_task_matrix.json       # {task: {row_slug: {pass_rate, n_trials, n_success, evaluated}}}

Usage:
  python refresh.py                   # full refresh (GitHub + S3 if AWS creds present)
  python refresh.py --skip-scrape     # reuse leaderboard.json
  python refresh.py --skip-details    # reuse rows/*.json
  python refresh.py --no-s3           # only GitHub submissions
  python refresh.py --workers 8
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = "https://labs.scale.com/leaderboard/swe_bench_pro_public"
TRAJ_API = "https://api.github.com/repos/scaleapi/SWE-bench_Pro-os/contents/traj"
TRAJ_RAW = (
    "https://raw.githubusercontent.com/scaleapi/SWE-bench_Pro-os/main/traj/{folder}/eval_results.json"
)

S3_BUCKET = "s3://scaleapi-results/swe-bench-pro"
S3_CACHE_DIR = Path(os.environ.get("SBP_S3_CACHE", "/tmp/sbp_s3_cache"))

HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=ScaleAI%2FSWE-bench_Pro&config=default&split=test"
    "&offset={offset}&length={length}"
)
HF_TOTAL_INSTANCES = 731


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "swe-bench-pro-leaderboard-refresh/1.0"}
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
# Step 1: scrape labs.scale.com RSC payload
# --------------------------------------------------------------------------- #
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[\d+,\s*("(?:[^"\\]|\\.)*")\s*\]\)')


def _slice_bracket_json(payload: str, key: str) -> str | None:
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


def scrape_leaderboard() -> list[dict]:
    html = fetch(LEADERBOARD_URL)
    for raw in _PUSH_RE.findall(html):
        payload = json.loads(raw)
        if '"score"' not in payload or '"entries":[' not in payload:
            continue
        arr = _slice_bracket_json(payload, "entries")
        if arr is None:
            continue
        entries = json.loads(arr)
        if entries and isinstance(entries, list) and "model" in entries[0]:
            return entries
    raise RuntimeError("Could not locate leaderboard entries in Scale Labs RSC payload")


def _slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_").lower()


def write_leaderboard(entries: list[dict], out: Path) -> None:
    out.write_text(
        json.dumps(
            {
                "source_url": LEADERBOARD_URL,
                "benchmark": "swe-bench-pro",
                "split": "public",
                "num_entries": len(entries),
                "note": (
                    "Entries here are the live Scale Labs leaderboard (aggregate only). "
                    "Per-instance data lives under `rows/` and is keyed by the traj "
                    "folder name in scaleapi/SWE-bench_Pro-os. The two are not 1:1 — "
                    "the repo publishes per-instance data for 9 submissions "
                    "(5 paper + 4 from the Oct 2025 snapshot), while the leaderboard "
                    "shows 24 models (newer ones are S3-only with AWS auth)."
                ),
                "schema": {
                    "model": "Model display name",
                    "version": "Model version string (often empty)",
                    "rank": "Leaderboard rank (ties allowed)",
                    "score": "Pct of public set resolved (0-100)",
                    "confidenceInterval_upper": "95% CI half-width",
                    "contaminationMessage": "Warning string from Scale if present",
                    "company": "Model provider",
                    "isNew / new": "Recently added flag",
                    "createdAt": "When this row was added",
                    "deprecated": "Whether Scale marks the row deprecated",
                    "maxScore": "Upper bound of the CI",
                },
                "entries": entries,
            },
            indent=2,
        )
    )
    print(f"  -> wrote {out.relative_to(HERE)} ({len(entries)} entries)")


# --------------------------------------------------------------------------- #
# Step 2: per-submission per-instance data from traj/
# --------------------------------------------------------------------------- #
def list_traj_folders() -> list[str]:
    data = fetch_json(TRAJ_API + "?per_page=100")
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected traj listing: {data!r}")
    return sorted(x["name"] for x in data if x.get("type") == "dir")


# --------------------------------------------------------------------------- #
# S3: list + sync + grade
# --------------------------------------------------------------------------- #
def _aws_available() -> bool:
    return shutil.which("aws") is not None


def list_s3_folders() -> list[str]:
    """List top-level submission folders in the Scale results bucket."""
    try:
        out = subprocess.run(
            ["aws", "s3", "ls", f"{S3_BUCKET}/"],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"aws s3 ls failed: {e.stderr.strip()}") from e
    folders: list[str] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("PRE ") and line.endswith("/"):
            folders.append(line[4:-1])
    return sorted(folders)


def _aws_cp(src: str, dest: Path) -> bool:
    """Copy a single S3 object if it exists. Returns True on success."""
    r = subprocess.run(
        ["aws", "s3", "cp", src, str(dest), "--only-show-errors"],
        capture_output=True, text=True, timeout=120,
    )
    return r.returncode == 0


def try_fetch_prebuilt_eval_results(folder: str) -> dict[str, bool] | None:
    """Some S3 folders ship a pre-graded `eval_results.json`. Try a few known
    locations; return the parsed dict or None if none exists."""
    candidates = [
        f"{S3_BUCKET}/{folder}/eval_results.json",
        f"{S3_BUCKET}/{folder}/output/eval_results.json",
        f"{S3_BUCKET}/{folder}/eval/eval_results.json",
    ]
    S3_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = S3_CACHE_DIR / f"{folder}__eval_results.json"
    for src in candidates:
        if _aws_cp(src, dest):
            try:
                data = json.loads(dest.read_text())
            except Exception:
                continue
            if isinstance(data, dict) and data:
                return data
    return None


def sync_s3_eval(folder: str) -> Path:
    """Sync all `_output.json` files under the submission's eval dir.

    Tries both `s3://<folder>/eval/` and `s3://<folder>/output/` (a
    layout variant used by a few folders). `aws s3 sync` is idempotent.
    """
    dest = S3_CACHE_DIR / folder
    dest.mkdir(parents=True, exist_ok=True)
    # Try `eval/` first, then `output/` — whichever has files wins.
    for subdir in ("eval", "output"):
        subprocess.run(
            [
                "aws", "s3", "sync",
                f"{S3_BUCKET}/{folder}/{subdir}/",
                str(dest) + "/",
                "--exclude", "*",
                "--include", "*/_output.json",
                "--only-show-errors",
            ],
            check=False, timeout=1200,  # skip layout-not-present failures
        )
    return dest


# --------------------------------------------------------------------------- #
# HF dataset: fetch instance metadata needed for grading
# --------------------------------------------------------------------------- #
def _coerce_str_list(v) -> list[str]:
    """HF returns the test lists as stringified Python lists."""
    if isinstance(v, list):
        return list(v)
    if isinstance(v, str) and v:
        try:
            return list(eval(v))  # matches swe_bench_pro_eval.py's own parse
        except Exception:
            try:
                return list(json.loads(v))
            except Exception:
                return []
    return []


def fetch_hf_rows() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    page = 100
    while offset < HF_TOTAL_INSTANCES:
        url = HF_ROWS_URL.format(offset=offset, length=page)
        data = fetch_json(url)
        batch = [r.get("row", {}) for r in data.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
    return rows


def hf_build_test_index(rows: list[dict]) -> dict[str, dict[str, set[str]]]:
    return {
        r["instance_id"]: {
            "f2p": set(_coerce_str_list(r.get("fail_to_pass"))),
            "p2p": set(_coerce_str_list(r.get("pass_to_pass"))),
        }
        for r in rows
        if r.get("instance_id")
    }


def _parse_instance_id(dir_name: str) -> str:
    """S3 dir names already match HF `instance_id` verbatim (both carry the
    `instance_` prefix). Kept as a function in case the convention changes."""
    return dir_name


def grade_s3_folder(local_dir: Path, tests_idx: dict[str, dict[str, set[str]]]) -> dict[str, bool]:
    """Apply SWE-bench Pro's resolution rule to every instance in local_dir.

    Rule (from scaleapi/SWE-bench_Pro-os/swe_bench_pro_eval.py):
        passed = {t["name"] for t in output["tests"] if t["status"] == "PASSED"}
        resolved = (f2p | p2p) <= passed
    """
    eval_results: dict[str, bool] = {}
    for inst_dir in sorted(local_dir.iterdir()):
        if not inst_dir.is_dir():
            continue
        out_path = inst_dir / "_output.json"
        if not out_path.exists():
            continue
        iid = _parse_instance_id(inst_dir.name)
        tests = tests_idx.get(iid)
        if tests is None:
            continue
        try:
            out = json.loads(out_path.read_text())
        except Exception:
            eval_results[iid] = False
            continue
        passed = {t.get("name") for t in out.get("tests", []) if t.get("status") == "PASSED"}
        eval_results[iid] = (tests["f2p"] | tests["p2p"]).issubset(passed)
    return eval_results


def _classify(folder: str) -> dict:
    """Heuristic tagging of a traj folder."""
    if folder.endswith("-paper"):
        return {"run_type": "paper", "config_note": "cost limit $2"}
    if re.search(r"-\d{8}$", folder):
        return {
            "run_type": "leaderboard_snapshot",
            "config_note": "250 turns, uncapped cost (matches current leaderboard config)",
        }
    return {"run_type": "other", "config_note": ""}


def fetch_github_eval_results(folder: str) -> tuple[dict[str, bool], str]:
    url = TRAJ_RAW.format(folder=folder)
    data = fetch_json(url)
    if not isinstance(data, dict):
        raise RuntimeError(f"{url}: not a dict")
    return data, url


def _row_entry(
    folder: str,
    payload: dict[str, bool],
    source_label: str,
    source_url: str,
) -> dict:
    resolved = {k for k, v in payload.items() if v is True}
    evaluated = set(payload.keys())
    return {
        "slug": folder,
        "folder": folder,
        **_classify(folder),
        "source": source_label,
        "results_url": source_url,
        "num_instances_reported": len(payload),
        "num_resolved": len(resolved),
        "recomputed_pass_rate": (
            len(resolved) / len(payload) if payload else None
        ),
        "resolved_instance_ids": sorted(resolved),
        # Set of instance IDs this submission actually evaluated. Differs
        # from the canonical 731 universe for paper runs and submissions
        # that only evaluated a subset. Use to distinguish "fail" from
        # "not evaluated" in downstream subset-accuracy recomputation.
        "evaluated_instance_ids": sorted(evaluated),
    }


def fetch_all_details(
    folders: list[str],
    workers: int,
    *,
    use_s3: bool,
    tests_idx: dict[str, dict[str, set[str]]] | None = None,
) -> dict[str, dict]:
    """For each folder, use GitHub's pre-graded eval_results.json if available;
    otherwise sync the S3 `eval/` dir and grade locally."""
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)

    try:
        gh_folders = set(list_traj_folders())
    except Exception as e:
        print(f"  WARN: couldn't list GitHub traj folders: {e}")
        gh_folders = set()

    results: dict[str, dict] = {}
    gh_targets = [f for f in folders if f in gh_folders]
    s3_targets = [f for f in folders if f not in gh_folders]

    # --- GitHub path (fast, parallel) --------------------------------------- #
    if gh_targets:
        print(f"  GitHub: fetching {len(gh_targets)} pre-graded eval_results.json files")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_github_eval_results, f): f for f in gh_targets}
            for i, fut in enumerate(as_completed(futs), 1):
                folder = futs[fut]
                try:
                    payload, url = fut.result()
                except Exception as e:
                    print(f"  [{i}/{len(gh_targets)}] FAIL {folder}: {e}", file=sys.stderr)
                    continue
                entry = _row_entry(folder, payload, "github", url)
                (rows_dir / f"{folder}.json").write_text(json.dumps(entry, indent=2))
                results[folder] = entry
                print(f"  [gh {i}/{len(gh_targets)}] {folder} ({entry['num_resolved']}/{entry['num_instances_reported']})")

    # --- S3 path (sync then grade) ------------------------------------------ #
    if s3_targets:
        if not use_s3:
            print(f"  skipping {len(s3_targets)} S3-only folders (--no-s3)")
        elif not _aws_available():
            print(f"  WARN: aws CLI not installed; skipping {len(s3_targets)} S3-only folders")
        elif tests_idx is None:
            print(f"  WARN: no test index loaded; skipping {len(s3_targets)} S3-only folders")
        else:
            print(f"  S3: processing {len(s3_targets)} S3-only folders via {S3_CACHE_DIR}")
            for i, folder in enumerate(s3_targets, 1):
                # Prefer pre-graded eval_results.json where Scale provides it.
                prebuilt = try_fetch_prebuilt_eval_results(folder)
                if prebuilt is not None:
                    entry = _row_entry(
                        folder, prebuilt, "s3_prebuilt",
                        f"{S3_BUCKET}/{folder}/ (pre-graded eval_results.json)",
                    )
                    (rows_dir / f"{folder}.json").write_text(json.dumps(entry, indent=2))
                    results[folder] = entry
                    print(
                        f"  [s3 {i}/{len(s3_targets)}] {folder} "
                        f"({entry['num_resolved']}/{entry['num_instances_reported']}) [prebuilt]"
                    )
                    continue
                # Else sync per-instance test outputs and grade ourselves.
                try:
                    local_dir = sync_s3_eval(folder)
                except Exception as e:
                    print(f"  [s3 {i}/{len(s3_targets)}] FAIL sync {folder}: {e}", file=sys.stderr)
                    continue
                try:
                    payload = grade_s3_folder(local_dir, tests_idx)
                except Exception as e:
                    print(f"  [s3 {i}/{len(s3_targets)}] FAIL grade {folder}: {e}", file=sys.stderr)
                    continue
                if not payload:
                    print(f"  [s3 {i}/{len(s3_targets)}] {folder} — no per-instance data found", file=sys.stderr)
                    continue
                entry = _row_entry(
                    folder, payload, "s3_graded",
                    f"{S3_BUCKET}/{folder}/eval/ (graded via swe_bench_pro_eval.py rule)",
                )
                (rows_dir / f"{folder}.json").write_text(json.dumps(entry, indent=2))
                results[folder] = entry
                print(
                    f"  [s3 {i}/{len(s3_targets)}] {folder} "
                    f"({entry['num_resolved']}/{entry['num_instances_reported']}) [graded]"
                )

    return results


# --------------------------------------------------------------------------- #
# Step 3: task universe + per-task attach
# --------------------------------------------------------------------------- #
def hf_task_universe() -> list[str]:
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
    seen, out = set(), []
    for iid in ids:
        if iid not in seen:
            seen.add(iid)
            out.append(iid)
    return sorted(out)


def task_universe(rows_data: dict[str, dict]) -> list[str]:
    try:
        ids = hf_task_universe()
        if ids:
            print(f"  task universe: {len(ids)} instances (HF canonical)")
            return ids
    except Exception as e:
        print(f"  WARN: HF fetch failed: {e}; falling back to union")
    all_ids: set[str] = set()
    for row in rows_data.values():
        all_ids.update(row.get("resolved_instance_ids") or [])
    return sorted(all_ids)


def attach_per_task_stats(rows_data: dict[str, dict], tasks: list[str]) -> None:
    for row in rows_data.values():
        resolved = set(row["resolved_instance_ids"])
        evaluated = set(row.get("evaluated_instance_ids") or [])
        row["num_tasks"] = len(tasks)
        row["total_trials"] = len(tasks)
        row["total_successes"] = sum(1 for t in tasks if t in resolved)
        row["tasks"] = [
            {
                "task_name": t,
                "evaluated": t in evaluated,
                "n_trials": 1 if t in evaluated else 0,
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
                "evaluated": t["evaluated"],
            }
    return {"tasks": tasks, "matrix": dict(matrix)}


def build_rows_index(rows_data: dict[str, dict]) -> list[dict]:
    out = []
    for slug, row in rows_data.items():
        out.append(
            {
                "slug": slug,
                "folder": row["folder"],
                "run_type": row["run_type"],
                "config_note": row["config_note"],
                # As reported in the submission's own eval_results.json (may
                # differ from the canonical universe: paper runs often used
                # a superset of tasks).
                "num_instances_reported": row["num_instances_reported"],
                "num_resolved_reported": row["num_resolved"],
                "recomputed_pass_rate": row["recomputed_pass_rate"],
                # Projected onto the 731-instance canonical Public universe.
                "num_canonical_tasks": row["num_tasks"],
                "num_resolved_on_canonical": row["total_successes"],
                "accuracy": (
                    row["total_successes"] / row["total_trials"]
                    if row["total_trials"] else None
                ),
            }
        )
    out.sort(key=lambda r: -(r.get("accuracy") or 0))
    return out


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
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-details", action="store_true")
    ap.add_argument("--no-s3", action="store_true", help="Skip S3-only submissions; only use GitHub pre-graded files")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    print("=" * 72)
    print("SWE-bench Pro (Public) leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/3] skip scrape — reusing leaderboard.json")
    else:
        print("[1/3] scraping labs.scale.com leaderboard")
        entries = scrape_leaderboard()
        write_leaderboard(entries, leaderboard_path)

    if args.skip_details:
        print("[2/3] skip detail fetch — loading existing rows/*.json")
        rows_data = {}
        for f in (HERE / "rows").glob("*.json"):
            d = json.loads(f.read_text())
            rows_data[d["slug"]] = d
    else:
        # Collect the union of submission folders from GitHub + S3
        gh_folders: list[str] = []
        s3_folders: list[str] = []
        try:
            gh_folders = list_traj_folders()
            print(f"  found {len(gh_folders)} folders on GitHub (pre-graded)")
        except Exception as e:
            print(f"  WARN: GitHub listing failed: {e}")
        if not args.no_s3 and _aws_available():
            try:
                s3_folders = list_s3_folders()
                print(f"  found {len(s3_folders)} folders on S3")
            except Exception as e:
                print(f"  WARN: S3 listing failed: {e}")
        elif args.no_s3:
            print("  --no-s3: skipping S3 listing")
        else:
            print("  aws CLI unavailable; skipping S3")

        all_folders = sorted(set(gh_folders) | set(s3_folders))
        print(f"  total unique folders: {len(all_folders)}")

        # Load HF test index if we have any S3-only folders to grade
        tests_idx: dict[str, dict[str, set[str]]] | None = None
        s3_only = [f for f in all_folders if f not in set(gh_folders)]
        if s3_only and not args.no_s3 and _aws_available():
            print(f"  fetching HF test-list index for {HF_TOTAL_INSTANCES} instances (needed to grade S3 submissions)")
            hf_rows = fetch_hf_rows()
            tests_idx = hf_build_test_index(hf_rows)
            print(f"  indexed {len(tests_idx)} instances")

        print(f"[2/3] building rows/*.json for {len(all_folders)} submissions")
        rows_data = fetch_all_details(
            all_folders, args.workers, use_s3=not args.no_s3, tests_idx=tests_idx
        )

    print("[3/3] building task universe + per_task_matrix.json + rows_index.json")
    tasks = task_universe(rows_data)
    attach_per_task_stats(rows_data, tasks)
    write_detail_files(rows_data)

    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows_data),
                "num_tasks": len(tasks),
                "note": (
                    "These rows are the subset of leaderboard submissions with public "
                    "per-instance data (GitHub traj/ folder). Most newer leaderboard "
                    "entries are S3-only and absent here."
                ),
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
