#!/usr/bin/env python3
"""Refresh the DABStep (Finance Agent) leaderboard snapshot.

DABStep — Data Agent Benchmark for Multi-step reasoning — is a finance-domain
agent benchmark from Adyen. Agents answer questions grounded in a corpus of
anonymized Adyen payment data plus domain docs. 450 scored tasks (72 easy,
378 hard). pass@1 — one trial per task per submission.

All artifacts live in one HuggingFace dataset repo (adyen/DABstep). Per-task
pass/fail is published for every submission as a JSONL file, which makes
subset recomputation trivial.

Sources used end-to-end:

  1. https://huggingface.co/api/datasets/adyen/DABstep/tree/main/data%2Fsubmissions
     Paginated listing of every submission file. Names follow
     `v1__{submission_id}__{DD-MM-YYYY}.jsonl`.
  2. https://huggingface.co/datasets/adyen/DABstep/resolve/main/data/submissions/<file>
     One JSONL per submission, 450 rows, each with the same metadata
     (agent_name, model_family, organisation, repo_url, date, validated)
     plus per-task `agent_answer`.
  3. https://huggingface.co/datasets/adyen/DABstep/resolve/main/data/task_scores/<file>
     One JSONL per submission, 450 rows: submission_id, task_id, score (bool),
     level (easy/hard), agent_answer. This is the per-task pass/fail matrix.
  4. https://huggingface.co/datasets/adyen/DABstep/resolve/main/data/tasks/all.jsonl
     Canonical 450-task universe with question, answer (empty in the public
     copy — gold is in the private adyen/DABstep-internal repo), guidelines,
     level.

The official HF Space (adyen/DABstep) splits the leaderboard into `validated`
and `unvalidated`. Submissions are `validated=False` by default — maintainers
flip the flag after review. We keep both but tag each row so downstream
analysis can filter. Spam/low-quality unvalidated submissions dominate the
raw count (~1.8k files) but tend to score near zero.

Outputs (all under this directory):
  leaderboard.json           # all submissions, aggregate scores by level
  rows/<slug>.jsonl          # per-row: metadata + per-task stats (450 tasks)
  rows_index.json            # sorted summary, with recomputed pass rates
  per_task_matrix.json       # {task: {slug: {pass_rate, n_trials, n_success}}}

Usage:
  python refresh.py                  # full refresh (~2-3 min, 8 workers)
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-details   # reuse rows/*.json
  python refresh.py --workers 16     # adjust fetch parallelism
  python refresh.py --validated-only # skip unvalidated submissions
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

HF_DATASET = "adyen/DABstep"
HF_TREE_API = (
    f"https://huggingface.co/api/datasets/{HF_DATASET}/tree/main/"
    "data%2F{subdir}?expand=false&limit=1000"
)
HF_RAW = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main/data"

TASKS_URL = f"{HF_RAW}/tasks/all.jsonl"

# v1__<submission_id>__<DD-MM-YYYY>.jsonl
FILENAME_RE = re.compile(r"^v1__(?P<sid>.+)__(?P<date>\d{2}-\d{2}-\d{4})\.jsonl$")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _open(url: str, retries: int = 8):
    """HTTP open with retries. Longer backoff on 429 to ride out rate limits."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "dabstep-leaderboard-refresh/1.0"}
            )
            return urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                # Respect Retry-After if present; else exponential backoff.
                ra = e.headers.get("Retry-After") if hasattr(e, "headers") else None
                delay = float(ra) if ra and ra.replace(".", "", 1).isdigit() else min(
                    60.0, 5.0 * (2**attempt)
                )
                time.sleep(delay)
            else:
                time.sleep(1.5 * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def fetch_text(url: str) -> str:
    with _open(url) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> object:
    return json.loads(fetch_text(url))


def fetch_jsonl(url: str) -> list[dict]:
    out: list[dict] = []
    for line in fetch_text(url).splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def fetch_paginated_tree(subdir: str) -> list[dict]:
    """List every file under data/<subdir>, following HF tree pagination."""
    url = HF_TREE_API.format(subdir=subdir)
    files: list[dict] = []
    while url:
        with _open(url) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            link = resp.headers.get("Link") or ""
        files.extend(json.loads(body))
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return files


# --------------------------------------------------------------------------- #
# Step 1: enumerate submissions
# --------------------------------------------------------------------------- #
def enumerate_submissions() -> list[dict]:
    """Return [{sid, date, submissions_path, task_scores_path}] for each file."""
    sub_files = fetch_paginated_tree("submissions")
    score_files = {f["path"].split("/")[-1] for f in fetch_paginated_tree("task_scores")}
    entries: list[dict] = []
    for f in sub_files:
        name = f["path"].split("/")[-1]
        m = FILENAME_RE.match(name)
        if not m:
            print(f"  skip: unexpected filename {name}")
            continue
        if name not in score_files:
            # Can happen if scoring hasn't run yet — skip, no per-task data.
            continue
        # submission_id may contain spaces + dots — percent-encode for URL.
        quoted = urllib.parse.quote(name, safe="._-")
        entries.append(
            {
                "submission_id": m.group("sid"),
                "date": m.group("date"),
                "submissions_filename": name,
                "submissions_url": f"{HF_RAW}/submissions/{quoted}",
                "task_scores_url": f"{HF_RAW}/task_scores/{quoted}",
            }
        )
    # Stable order; dedupe in case of duplicate submission_id (keep latest date).
    by_sid: dict[str, dict] = {}
    for e in entries:
        prev = by_sid.get(e["submission_id"])
        if prev is None or _date_key(e["date"]) >= _date_key(prev["date"]):
            by_sid[e["submission_id"]] = e
    return sorted(by_sid.values(), key=lambda e: e["submission_id"])


def _date_key(d: str) -> tuple[int, int, int]:
    dd, mm, yyyy = d.split("-")
    return (int(yyyy), int(mm), int(dd))


def _slugify(submission_id: str) -> str:
    """Filesystem-safe slug. submission_ids allow spaces; folders shouldn't."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", submission_id).strip("_") or "unknown"


# --------------------------------------------------------------------------- #
# Step 2: fetch tasks (canonical universe)
# --------------------------------------------------------------------------- #
def fetch_tasks() -> list[dict]:
    tasks = fetch_jsonl(TASKS_URL)
    for t in tasks:
        # question/answer text can be large; keep only metadata relevant to
        # subset selection. Gold answers are private (in DABstep-internal).
        t.pop("question", None)
        t.pop("answer", None)
        t.pop("guidelines", None)
    return tasks


# --------------------------------------------------------------------------- #
# Step 3: per-submission fetch + score assembly
# --------------------------------------------------------------------------- #
def _metadata_from_submissions(rows: list[dict]) -> dict:
    """All rows share the same metadata; take it from the first row."""
    if not rows:
        return {}
    r = rows[0]
    return {
        "agent_name": r.get("agent_name"),
        "model_family": r.get("model_family"),
        "organisation": r.get("organisation"),
        "repo_url": r.get("repo_url"),
        "date": r.get("date"),
        "validated": bool(r.get("validated", False)),
    }


def fetch_one_submission(entry: dict, tasks: list[dict]) -> dict | None:
    sid = entry["submission_id"]
    try:
        # submissions file: metadata (first row) only — we already have answers
        # in task_scores, so don't persist 450 duplicate rows.
        sub_rows = fetch_jsonl(entry["submissions_url"])
        score_rows = fetch_jsonl(entry["task_scores_url"])
    except Exception as e:
        print(f"  WARN: {sid}: fetch failed — {e}")
        return None

    meta = _metadata_from_submissions(sub_rows)

    # Index scores by task_id; tolerate missing tasks (n_trials becomes 0).
    scores_by_task: dict[str, dict] = {}
    for r in score_rows:
        tid = str(r.get("task_id"))
        scores_by_task[tid] = {
            "score": bool(r.get("score", False)),
            "level": r.get("level"),
            "agent_answer": r.get("agent_answer"),
        }

    per_task: list[dict] = []
    success = 0
    by_level: dict[str, list[int]] = defaultdict(list)
    missing: list[str] = []
    for t in tasks:
        tid = str(t["task_id"])
        level = t.get("level")
        if tid in scores_by_task:
            s = scores_by_task[tid]
            n_success = 1 if s["score"] else 0
            per_task.append(
                {
                    "task_name": tid,
                    "level": s["level"] or level,
                    "n_trials": 1,
                    "n_success": n_success,
                    "pass_rate": float(n_success),
                }
            )
            success += n_success
            by_level[s["level"] or level or "unknown"].append(n_success)
        else:
            missing.append(tid)
            per_task.append(
                {
                    "task_name": tid,
                    "level": level,
                    "n_trials": 0,
                    "n_success": 0,
                    "pass_rate": None,
                }
            )

    total_trials = sum(1 for t in per_task if t["n_trials"] == 1)
    easy = by_level.get("easy", [])
    hard = by_level.get("hard", [])

    return {
        "slug": _slugify(sid),
        "submission_id": sid,
        "submissions_filename": entry["submissions_filename"],
        "submissions_url": entry["submissions_url"],
        "task_scores_url": entry["task_scores_url"],
        "agent_name": meta.get("agent_name"),
        "model_family": meta.get("model_family"),
        "organisation": meta.get("organisation"),
        "repo_url": meta.get("repo_url"),
        "date": meta.get("date") or entry["date"],
        "validated": meta.get("validated", False),
        "num_tasks": len(tasks),
        "total_trials": total_trials,
        "total_successes": success,
        "pass_rate": (success / total_trials) if total_trials else None,
        "easy_pass_rate": (sum(easy) / len(easy)) if easy else None,
        "hard_pass_rate": (sum(hard) / len(hard)) if hard else None,
        "num_easy": len(easy),
        "num_hard": len(hard),
        "missing_task_ids": missing,
        "tasks": per_task,
    }


def fetch_all_submissions(
    entries: list[dict], tasks: list[dict], workers: int, validated_only: bool
) -> tuple[dict[str, dict], list[str]]:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    out: dict[str, dict] = {}
    failed: list[str] = []

    # Resume: load any rows we already have on disk; skip refetching.
    cached_by_sid: dict[str, dict] = {}
    for f in rows_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("submission_id"):
                cached_by_sid[d["submission_id"]] = d
        except Exception:
            pass
    if cached_by_sid:
        print(f"  resuming — {len(cached_by_sid)} rows already on disk")

    todo: list[dict] = []
    for e in entries:
        sid = e["submission_id"]
        if sid in cached_by_sid:
            row = cached_by_sid[sid]
            if validated_only and not row.get("validated"):
                continue
            slug = row["slug"]
            if slug in out:
                slug = f"{slug}__{row['date']}"
                row["slug"] = slug
            out[slug] = row
        else:
            todo.append(e)

    print(f"  {len(todo)} submissions to fetch ({len(entries) - len(todo)} cached)")

    if not todo:
        return out, failed

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_one_submission, e, tasks): e for e in todo}
        done = 0
        for fut in as_completed(futs):
            entry = futs[fut]
            done += 1
            try:
                row = fut.result()
            except Exception as e:
                failed.append(entry["submission_id"])
                print(f"  WARN: {entry['submission_id']}: {e}")
                continue
            if row is None:
                failed.append(entry["submission_id"])
                continue
            if validated_only and not row["validated"]:
                continue
            slug = row["slug"]
            if slug in out:
                slug = f"{slug}__{row['date']}"
                row["slug"] = slug
            out[slug] = row
            (rows_dir / f"{slug}.json").write_text(json.dumps(row, indent=2))
            if done % 100 == 0 or done == len(todo):
                print(f"  [{done}/{len(todo)}] kept {len(out)}, failed {len(failed)}")
    return out, failed


# --------------------------------------------------------------------------- #
# Step 4: rows_index, per_task_matrix, leaderboard.json
# --------------------------------------------------------------------------- #
def build_rows_index(rows_data: dict[str, dict]) -> list[dict]:
    out = []
    for slug, row in rows_data.items():
        out.append(
            {
                "slug": slug,
                "submission_id": row["submission_id"],
                "agent_name": row["agent_name"],
                "model_family": row["model_family"],
                "organisation": row["organisation"],
                "date": row["date"],
                "validated": row["validated"],
                "num_tasks": row["num_tasks"],
                "total_trials": row["total_trials"],
                "total_successes": row["total_successes"],
                "pass_rate": row["pass_rate"],
                "easy_pass_rate": row["easy_pass_rate"],
                "hard_pass_rate": row["hard_pass_rate"],
            }
        )
    # Match the HF Space: sort by hard, then easy, then overall.
    out.sort(
        key=lambda r: (
            -(r["hard_pass_rate"] or 0),
            -(r["easy_pass_rate"] or 0),
            -(r["pass_rate"] or 0),
        )
    )
    return out


def build_per_task_matrix(rows_data: dict[str, dict], tasks: list[dict]) -> dict:
    task_levels = {str(t["task_id"]): t.get("level") for t in tasks}
    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    for slug, row in rows_data.items():
        for t in row["tasks"]:
            if t["n_trials"] == 0:
                continue
            matrix[t["task_name"]][slug] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
            }
    return {
        "tasks": [
            {"task_id": str(t["task_id"]), "level": t.get("level")} for t in tasks
        ],
        "task_levels": task_levels,
        "matrix": dict(matrix),
    }


def build_leaderboard(rows_data: dict[str, dict], tasks: list[dict]) -> dict:
    entries = []
    for slug, row in rows_data.items():
        entries.append(
            {
                "slug": slug,
                "submission_id": row["submission_id"],
                "agent_name": row["agent_name"],
                "model_family": row["model_family"],
                "organisation": row["organisation"],
                "repo_url": row["repo_url"],
                "date": row["date"],
                "validated": row["validated"],
                "pass_rate": row["pass_rate"],
                "easy_pass_rate": row["easy_pass_rate"],
                "hard_pass_rate": row["hard_pass_rate"],
                "num_easy": row["num_easy"],
                "num_hard": row["num_hard"],
                "total_trials": row["total_trials"],
                "total_successes": row["total_successes"],
            }
        )
    entries.sort(
        key=lambda r: (
            -(r["hard_pass_rate"] or 0),
            -(r["easy_pass_rate"] or 0),
            -(r["pass_rate"] or 0),
        )
    )
    return {
        "source_dataset": f"https://huggingface.co/datasets/{HF_DATASET}",
        "source_space": f"https://huggingface.co/spaces/{HF_DATASET}",
        "benchmark": "dabstep",
        "split": "default",
        "scoring": "pass@1 — one trial per task per submission",
        "num_entries": len(entries),
        "num_validated": sum(1 for e in entries if e["validated"]),
        "num_tasks": len(tasks),
        "num_easy": sum(1 for t in tasks if t.get("level") == "easy"),
        "num_hard": sum(1 for t in tasks if t.get("level") == "hard"),
        "schema": {
            "slug": "Filesystem-safe submission id (our row key)",
            "submission_id": "Original submission_id = '<organisation>-<agent_name>'",
            "agent_name": "Agent display name",
            "model_family": "Self-reported backing model family",
            "organisation": "Submitter org (' | user <hf_username>' appended by HF Space)",
            "repo_url": "Code/repo link (optional, often empty)",
            "date": "Submission date (DD-MM-YYYY)",
            "validated": "Whether Adyen maintainers verified the submission",
            "pass_rate": "Overall pass rate across all scored tasks (0-1)",
            "easy_pass_rate": "Pass rate on easy tasks (0-1)",
            "hard_pass_rate": "Pass rate on hard tasks (0-1)",
        },
        "entries": entries,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-scrape", action="store_true", help="Reuse existing leaderboard.json")
    ap.add_argument("--skip-details", action="store_true", help="Reuse existing rows/*.json")
    ap.add_argument("--workers", type=int, default=8, help="Concurrent fetches (default 8)")
    ap.add_argument(
        "--validated-only",
        action="store_true",
        help="Skip submissions with validated=False (drops the spam tail)",
    )
    args = ap.parse_args()

    print("=" * 72)
    print("DABStep (Finance Agent) leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    print("[1/4] fetching task universe")
    tasks = fetch_tasks()
    print(f"  {len(tasks)} tasks")

    leaderboard_path = HERE / "leaderboard.json"
    rows_dir = HERE / "rows"

    if args.skip_details:
        print("[2/4] skip detail fetch — loading existing rows/*.json")
        rows_data: dict[str, dict] = {}
        for f in rows_dir.glob("*.json"):
            d = json.loads(f.read_text())
            rows_data[d["slug"]] = d
        failed: list[str] = []
    else:
        print("[2/4] enumerating submission files on HF")
        entries = enumerate_submissions()
        print(f"  {len(entries)} submissions with scores on HF")
        print(f"[3/4] fetching per-submission data ({args.workers} workers)")
        rows_data, failed = fetch_all_submissions(
            entries, tasks, args.workers, args.validated_only
        )

    print("[4/4] building leaderboard.json + rows_index.json + per_task_matrix.json")

    leaderboard_path.write_text(
        json.dumps(build_leaderboard(rows_data, tasks), indent=2)
    )
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows_data),
                "num_validated": sum(1 for r in rows_data.values() if r["validated"]),
                "num_tasks": len(tasks),
                "failed": sorted(failed),
                "rows": build_rows_index(rows_data),
            },
            indent=2,
        )
    )
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(build_per_task_matrix(rows_data, tasks), indent=2)
    )

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    if rows_dir.exists():
        n = len(list(rows_dir.glob("*.json")))
        print(f"  rows/  ({n} files)")
    print(f"  tasks covered: {len(tasks)}")
    n_val = sum(1 for r in rows_data.values() if r["validated"])
    print(f"  validated: {n_val} / {len(rows_data)} rows")


if __name__ == "__main__":
    main()
