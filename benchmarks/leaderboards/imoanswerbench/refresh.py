#!/usr/bin/env python3
"""Refresh the IMO-AnswerBench leaderboard snapshot.

IMO-AnswerBench is part of the IMO-Bench suite introduced in "Towards
Robust Mathematical Reasoning" (Luong et al., EMNLP 2025,
arXiv:2511.01846). 400 short-answer Olympiad problems across Algebra,
Combinatorics, Geometry, and Number Theory, at four difficulty tiers
(pre-IMO, IMO-Easy, IMO-Medium, IMO-Hard). `answerbench_v2.csv`
(2026-02-12) superseded the original `answerbench.csv` after some
problems were found to be ambiguous or incorrect — we use v2.

Sources used end-to-end:

  1. https://llm-stats.com/benchmarks/imo-answerbench
     A Next.js page whose `models` array inside `self.__next_f.push`
     chunks carries one object per submission:
     `{rank, model_name, organization_name, score, verified,
       self_reported, self_reported_source, announcement_date,
       input_cost_per_million, output_cost_per_million, context_window,
       param_count, is_open_source, ...}`.
     llm-stats aggregates self-reported scores from model-provider blog
     posts and release announcements. **All entries are self-reported**
     (the `verified_count` in the page header is 0).
  2. github.com/google-deepmind/superhuman/tree/main/imobench/
     Ships `answerbench_v2.csv` (400 rows) with the canonical problem
     IDs + Category + Subcategory + Source + short ground-truth answer.
     We include this as `tasks.json` so a per-instance view is possible
     the moment anyone publishes per-model predictions.
  3. Paper abstract (arXiv:2511.01846) — the authors report Gemini Deep
     Think (IMO Gold) at 80.0% on IMO-AnswerBench. llm-stats currently
     tracks open-source leaders only, so we seed one hard-coded row
     (`paper_reference=True`) to reflect this canonical number. Remove
     the row if/when llm-stats starts tracking Gemini.

The official `imobench.github.io` page does not host an AnswerBench
leaderboard — only ProofBench leaderboards. Scores on provider blogs
are therefore the de-facto source of truth.

Outputs (all under this directory):
  leaderboard.json          # entries from llm-stats + paper reference row
  rows/<slug>.json          # per-row: metadata only (no per-question results)
  rows_index.json           # one-line summary per row, sorted by score
  tasks.json                # 400 problems from answerbench_v2.csv (id, category, subcategory, source)
  per_task_matrix.json      # shape placeholder: tasks populated, matrix empty

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-tasks     # reuse existing tasks.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = "https://llm-stats.com/benchmarks/imo-answerbench"
ANSWERBENCH_CSV_URL = (
    "https://raw.githubusercontent.com/google-deepmind/superhuman/"
    "main/imobench/answerbench_v2.csv"
)

# Hard-coded reference row from the paper (arXiv:2511.01846 abstract).
# llm-stats doesn't list Google/proprietary systems, so without this row
# the leaderboard would omit the benchmark's own headline baseline.
PAPER_REFERENCE_ROWS: list[dict] = [
    {
        "rank": None,
        "model_name": "Gemini Deep Think (IMO Gold)",
        "organization_name": "Google DeepMind",
        "score": 0.80,
        "verified": False,
        "self_reported": False,
        "self_reported_source": "https://arxiv.org/abs/2511.01846",
        "announcement_date": "2025-11-03",
        "param_count": None,
        "is_open_source": False,
        "paper_reference": True,
    },
]


def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 imoanswerbench-leaderboard-refresh/0.1"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Step 1: scrape llm-stats.com
# --------------------------------------------------------------------------- #
def _join_next_f_chunks(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[\d+,\"(.+?)\"\]\)', html, re.DOTALL)
    return bytes("".join(chunks), "utf-8").decode("unicode_escape")


def _extract_models_array(payload: str) -> list[dict]:
    """Pull the `models` JSON array out of the llm-stats page payload.

    We anchor on `"models":[` and balance brackets (honoring string
    literals) until the matching `]`.
    """
    m = re.search(r'"models":\[\{', payload)
    if not m:
        raise RuntimeError('Could not locate `"models":[{` in page source')
    start = m.start() + len('"models":')
    depth = 0
    in_str = False
    esc = False
    i = start
    while i < len(payload):
        ch = payload[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(payload[start : i + 1])


def scrape_leaderboard() -> list[dict]:
    html = fetch(LEADERBOARD_URL).decode("utf-8", errors="replace")
    payload = _join_next_f_chunks(html)
    models = _extract_models_array(payload)

    rows: list[dict] = []
    for m in models:
        rows.append(
            {
                "rank": m.get("rank"),
                "model_name": m.get("model_name"),
                "organization_name": m.get("organization_name"),
                "organization_id": m.get("organization_id"),
                "score": m.get("score"),  # 0-1 fraction
                "verified": bool(m.get("verified")),
                "self_reported": bool(m.get("self_reported")),
                "self_reported_source": m.get("self_reported_source"),
                "announcement_date": m.get("announcement_date"),
                "param_count": m.get("param_count"),
                "is_open_source": m.get("is_open_source"),
                "input_cost_per_million": m.get("input_cost_per_million"),
                "output_cost_per_million": m.get("output_cost_per_million"),
                "context_window": m.get("context_window"),
                "paper_reference": False,
            }
        )

    # Seed the paper-reference row so the headline baseline is visible.
    for r in PAPER_REFERENCE_ROWS:
        if not any(
            existing["model_name"] == r["model_name"] for existing in rows
        ):
            rows.append(dict(r))

    rows.sort(key=lambda r: -(r["score"] or 0))
    return rows


# --------------------------------------------------------------------------- #
# Step 2: task enumeration from answerbench_v2.csv
# --------------------------------------------------------------------------- #
def fetch_tasks() -> list[dict]:
    raw = fetch(ANSWERBENCH_CSV_URL).decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    tasks: list[dict] = []
    for row in reader:
        ans = (row.get("Short Answer") or "").strip()
        # Short answers can be long LaTeX — cap the preview.
        if len(ans) > 120:
            ans = ans[:120] + "…"
        tasks.append(
            {
                "task_id": row["Problem ID"],
                "category": (row.get("Category") or "").strip(),
                "subcategory": (row.get("Subcategory") or "").strip(),
                "source": (row.get("Source") or "").strip(),
                "short_answer_preview": ans,
            }
        )
    tasks.sort(key=lambda t: t["task_id"])
    return tasks


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def row_slug(model: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")
    return s or "row"


def write_leaderboard(rows: list[dict]) -> None:
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "source_url": LEADERBOARD_URL,
                "benchmark": "imo-answerbench",
                "num_entries": len(rows),
                "num_tasks": 400,
                "schema": {
                    "rank": "Leaderboard rank from llm-stats (null for paper_reference rows)",
                    "model_name": "Model name as reported by llm-stats / the paper",
                    "organization_name": "Provider (Moonshot AI, StepFun, Alibaba/Qwen, Zhipu AI, Meituan, DeepSeek, Google DeepMind, ...)",
                    "organization_id": "llm-stats organization slug",
                    "score": "Accuracy as a 0-1 fraction on the 400-problem benchmark",
                    "verified": "True if llm-stats verified the score (currently always false)",
                    "self_reported": "True if the score came from a provider-published blog/post",
                    "self_reported_source": "URL of the source announcement",
                    "announcement_date": "Date the score was announced (YYYY-MM-DD)",
                    "param_count": "Total parameter count (not active/expert count)",
                    "is_open_source": "True if the model weights are publicly released",
                    "input_cost_per_million": "USD per 1M input tokens (provider listed by llm-stats)",
                    "output_cost_per_million": "USD per 1M output tokens",
                    "context_window": "Maximum input context length (tokens)",
                    "paper_reference": "True for hard-coded rows from arXiv:2511.01846 that llm-stats doesn't track",
                },
                "entries": rows,
            },
            indent=2,
        )
    )


def write_rows(rows: list[dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    # Drop stale per-row files so leaderboard churn doesn't leave orphans.
    for old in rows_dir.glob("*.json"):
        old.unlink()
    for r in rows:
        slug = row_slug(r["model_name"])
        entry = {
            "slug": slug,
            "model": r["model_name"],
            "organization": r["organization_name"],
            "rank": r["rank"],
            "score": r["score"],
            "verified": r["verified"],
            "self_reported": r["self_reported"],
            "self_reported_source": r["self_reported_source"],
            "announcement_date": r["announcement_date"],
            "param_count": r["param_count"],
            "is_open_source": r["is_open_source"],
            "paper_reference": r.get("paper_reference", False),
            # No per-model per-question data is published anywhere; these
            # fields stay null for shape parity with other leaderboards.
            "num_tasks": None,
            "total_trials": None,
            "total_successes": None,
            "tasks": [],
        }
        (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))


def write_rows_index(rows: list[dict]) -> None:
    missing: list[dict] = []
    for r in rows:
        score = r["score"]
        missing.append(
            {
                "slug": row_slug(r["model_name"]),
                "model": r["model_name"],
                "organization": r["organization_name"],
                "rank": r["rank"],
                "announcement_date": r["announcement_date"],
                # Canonical 0–1 accuracy lives in `accuracy`; `score_pct` is
                # the same value rescaled for display.
                "accuracy": score,
                "score_pct": (score * 100.0) if score is not None else None,
                "self_reported": r["self_reported"],
                "self_reported_source": r["self_reported_source"],
                "paper_reference": r.get("paper_reference", False),
                "is_open_source": r["is_open_source"],
                "num_tasks": None,
                "total_trials": None,
                "recomputed_pass_rate": None,
            }
        )
    missing.sort(key=lambda r: -(r["accuracy"] or 0))
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": 0,
                "num_missing_detail": len(missing),
                "note": (
                    "IMO-AnswerBench has no official aggregate leaderboard — "
                    "imobench.github.io only hosts ProofBench rankings. We "
                    "mirror llm-stats.com, which collects self-reported "
                    "scores from provider blogs, and seed one paper-"
                    "reference row (Gemini Deep Think IMO Gold, 80.0%). No "
                    "per-model per-question data has been released, so "
                    "every row lives under `missing_detail`."
                ),
                "rows": [],
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_tasks_and_matrix(tasks: list[dict]) -> None:
    (HERE / "tasks.json").write_text(
        json.dumps(
            {
                "source_url": ANSWERBENCH_CSV_URL,
                "num_tasks": len(tasks),
                "note": (
                    "400 problems from answerbench_v2.csv (supersedes the "
                    "original answerbench.csv as of 2026-02-12). Categories: "
                    "Algebra, Combinatorics, Geometry, Number Theory, plus "
                    "one legacy 'Functional Equation' row that survived the "
                    "v2 relabel. Four difficulty tiers (pre-IMO, IMO-Easy, "
                    "IMO-Medium, IMO-Hard) are *not* encoded in the CSV — "
                    "the paper reports them as a separate per-problem tag."
                ),
                "schema": {
                    "task_id": "Canonical problem ID (e.g. imo-bench-algebra-001)",
                    "category": "Top-level category (Algebra / Combinatorics / Geometry / Number theory)",
                    "subcategory": "Finer-grained topic tag (e.g. Inequality, Graph Theory)",
                    "source": "Original competition attribution",
                    "short_answer_preview": "First 120 chars of the ground-truth answer",
                },
                "tasks": tasks,
            },
            indent=2,
        )
    )
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "No per-model per-question results are published. The "
                    "`tasks` list is populated so downstream tooling has a "
                    "canonical key space; `matrix` stays empty until someone "
                    "releases per-instance predictions."
                ),
                "tasks": [t["task_id"] for t in tasks],
                "matrix": {},
            },
            indent=2,
        )
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-tasks", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("IMO-AnswerBench leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/3] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/3] scraping llm-stats.com leaderboard")
        rows = scrape_leaderboard()
        write_leaderboard(rows)
        print(f"  -> wrote leaderboard.json ({len(rows)} entries)")

    print("[2/3] writing rows/ + rows_index.json")
    write_rows(rows)
    write_rows_index(rows)

    tasks_path = HERE / "tasks.json"
    if args.skip_tasks and tasks_path.exists():
        print("[3/3] skip tasks — reusing tasks.json")
    else:
        print("[3/3] downloading answerbench_v2.csv from GitHub")
        tasks = fetch_tasks()
        write_tasks_and_matrix(tasks)
        print(f"  -> wrote tasks.json + per_task_matrix.json ({len(tasks)} tasks)")

    print()
    print("done. outputs:")
    for f in (
        "leaderboard.json",
        "rows_index.json",
        "tasks.json",
        "per_task_matrix.json",
    ):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list((HERE / "rows").glob("*.json")))
    print(f"  rows/  ({n} files)")


if __name__ == "__main__":
    main()
