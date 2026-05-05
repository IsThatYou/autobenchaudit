#!/usr/bin/env python3
"""Refresh the Vals AI Finance Agent leaderboard snapshot.

Vals AI's Finance Agent benchmark evaluates agents on core financial-analyst
tasks. The benchmark itself is private (537 questions total; only 50 are
public on HuggingFace; 337 are held out permanently). **Vals does not publish
per-question pass/fail data for any submission.** The finest breakdown they
expose publicly is aggregate accuracy per model within each of nine task
categories (plus an overall score):

  - simple_retrieval_quantitative
  - simple_retrieval_qualitative
  - complex_retrieval
  - numerical_reasoning
  - financial_modeling           (= "Financial Modeling / Projections")
  - market_analysis
  - beat_or_miss
  - trends
  - adjustments

So in this snapshot, *one "task" equals one category*, not one question.
If/when Vals AI publishes per-instance results, this script's `per_task_matrix`
output can be swapped to index on question_id.

Source (single page):

  https://www.vals.ai/benchmarks/finance_agent

It's an Astro-rendered site. The entire leaderboard payload is embedded in
the page HTML as props on the `BenchmarkView` Astro island. We parse it out
directly — no public API, no auth required. The payload shape (after
unwrapping Astro's `[0, value]` type markers) is:

  benchmarkView
    metadata: {benchmark, slug, updated, total_models, models: [...], tasks: {slug: label, ...}}
    tasks:
      <category_slug>:
        <model_key>:
          accuracy, stderr, latency, cost_per_test,
          temperature, top_p, max_output_tokens,
          reasoning, reasoning_effort, verbosity, compute_effort,
          provider

Outputs (all under this directory):
  leaderboard.json       # 45 model rows with overall + per-category accuracy
  rows/<slug>.json       # per-model detail: metadata + per-category stats
  rows_index.json        # sorted summary
  per_task_matrix.json   # {category: {model_slug: {accuracy, stderr, cost_per_test, latency}}}

Usage:
  python refresh.py
"""

from __future__ import annotations

import argparse
import csv
import html as htmllib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

SOURCE_URL = "https://www.vals.ai/benchmarks/finance_agent"
BENCHMARK_SLUG = "finance_agent"

# The 50-question public split is stored in the benchmark-repos mirror. The
# repo-relative path lets refresh.py be run from anywhere; the --public-csv
# flag lets callers override when the file lives elsewhere (e.g. CI).
REPO_ROOT = HERE.parents[3]
DEFAULT_PUBLIC_CSV = (
    REPO_ROOT / "data" / "benchmark_repos" / "finance_agent" / "data" / "public.csv"
)
TOTAL_QUESTIONS = 537  # private set; public.csv covers 50 of them


# --------------------------------------------------------------------------- #
# HTTP + Astro island extraction
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; vals-leaderboard-refresh/1.0)"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def _peel(x):
    """Strip Astro's `[type_marker, value]` envelopes recursively."""
    if isinstance(x, list) and len(x) == 2 and isinstance(x[0], int):
        return _peel(x[1])
    if isinstance(x, dict):
        return {k: _peel(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_peel(v) for v in x]
    return x


def extract_benchmark_view(html: str) -> dict:
    """Pull the BenchmarkView Astro island's props JSON out of the page."""
    for m in re.finditer(r"<astro-island\s([^>]+)>", html):
        attrs = m.group(1)
        url = re.search(r'component-url="([^"]+)"', attrs)
        if not url or "BenchmarkView" not in url.group(1):
            continue
        props_attr = re.search(r'props="([^"]+)"', attrs)
        if not props_attr:
            continue
        raw = json.loads(htmllib.unescape(props_attr.group(1)))
        peeled = _peel(raw)
        bv = peeled.get("benchmarkView", peeled)
        # Some variants nest again under a "default" key — unwrap to the one
        # that actually has metadata+tasks.
        if "metadata" not in bv and isinstance(bv.get("default"), dict):
            bv = bv["default"]
        return bv
    raise RuntimeError("BenchmarkView astro-island not found in page HTML")


# --------------------------------------------------------------------------- #
# Build outputs
# --------------------------------------------------------------------------- #
def _slugify(model_key: str) -> str:
    """anthropic/claude-opus-4-7 -> anthropic_claude-opus-4-7 (matches Vals' URL slugs)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_key).strip("_")


def build_rows(bv: dict) -> dict[str, dict]:
    """Pivot from {category: {model: stats}} to one row per model."""
    meta = bv["metadata"]
    task_dict: dict[str, dict[str, dict]] = bv["tasks"]
    categories = [c for c in task_dict.keys() if c != "overall"]
    category_labels = meta.get("tasks", {})

    rows: dict[str, dict] = {}
    for model_key in meta.get("models", []):
        overall = task_dict.get("overall", {}).get(model_key, {})
        slug = _slugify(model_key)
        tasks_out = []
        for cat in categories:
            cell = task_dict.get(cat, {}).get(model_key) or {}
            tasks_out.append(
                {
                    "task_name": cat,
                    "task_label": category_labels.get(cat, cat),
                    "accuracy": cell.get("accuracy"),
                    "stderr": cell.get("stderr"),
                    "latency": cell.get("latency"),
                    "cost_per_test": cell.get("cost_per_test"),
                }
            )
        rows[slug] = {
            "slug": slug,
            "model_key": model_key,
            "provider": overall.get("provider"),
            "overall_accuracy": overall.get("accuracy"),
            "overall_stderr": overall.get("stderr"),
            "overall_latency": overall.get("latency"),
            "overall_cost_per_test": overall.get("cost_per_test"),
            "temperature": overall.get("temperature"),
            "top_p": overall.get("top_p"),
            "max_output_tokens": overall.get("max_output_tokens"),
            "reasoning": overall.get("reasoning"),
            "reasoning_effort": overall.get("reasoning_effort"),
            "verbosity": overall.get("verbosity"),
            "compute_effort": overall.get("compute_effort"),
            "num_categories": len(categories),
            "tasks": tasks_out,
        }
    return rows


def build_rows_index(rows: dict[str, dict]) -> list[dict]:
    out = []
    for slug, r in rows.items():
        out.append(
            {
                "slug": slug,
                "model_key": r["model_key"],
                "provider": r["provider"],
                "overall_accuracy": r["overall_accuracy"],
                "overall_stderr": r["overall_stderr"],
                "overall_cost_per_test": r["overall_cost_per_test"],
                "overall_latency": r["overall_latency"],
                "reasoning": r["reasoning"],
                "reasoning_effort": r["reasoning_effort"],
                "compute_effort": r["compute_effort"],
            }
        )
    out.sort(key=lambda r: -(r["overall_accuracy"] or 0))
    return out


def build_per_task_matrix(bv: dict, rows: dict[str, dict]) -> dict:
    """Matrix keyed on category → {model_slug: {accuracy, stderr, ...}}."""
    task_dict: dict[str, dict[str, dict]] = bv["tasks"]
    category_labels = bv["metadata"].get("tasks", {})
    categories = list(task_dict.keys())  # include "overall" as a row too
    matrix: dict[str, dict[str, dict]] = {}
    for cat in categories:
        cells = {}
        for model_key, stats in task_dict.get(cat, {}).items():
            slug = _slugify(model_key)
            cells[slug] = {
                "accuracy": stats.get("accuracy"),
                "stderr": stats.get("stderr"),
                "cost_per_test": stats.get("cost_per_test"),
                "latency": stats.get("latency"),
            }
        matrix[cat] = cells
    return {
        "tasks": [
            {"task_id": c, "label": category_labels.get(c, c)} for c in categories
        ],
        "note": (
            "Vals AI does not publish per-question results. The finest grain "
            "is aggregate accuracy per model per category (9 categories + overall). "
            "Each matrix cell is an aggregate, not per-instance pass/fail."
        ),
        "matrix": matrix,
    }


def build_public_questions(bv: dict, csv_path: Path) -> dict | None:
    """Build the public-split question → category-slug mapping.

    Vals's leaderboard is per-category, but the public HuggingFace split
    publishes each question's category in a "Question Type" column. Emitting
    this mapping alongside the leaderboard lets downstream consumers (the
    visualizer's run pipeline) tag each audited task with its Vals category
    slug, so per-task audit severities can be aggregated up to the category
    level automatically — no manual assignment needed.

    Returns None if the CSV isn't present (the leaderboard data is still
    valid without it; the mapping is an optional enrichment).
    """
    if not csv_path.exists():
        return None

    # label → slug from the scraped benchmark view. Every CSV "Question Type"
    # must resolve against this; if a label doesn't match, we surface the
    # discrepancy loudly rather than silently dropping questions.
    category_labels = bv["metadata"].get("tasks", {})
    label_to_slug = {
        label: slug for slug, label in category_labels.items() if slug != "overall"
    }

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    questions: list[dict] = []
    unmatched: list[str] = []
    counts: dict[str, int] = {}
    for idx, row in enumerate(rows):
        label = (row.get("Question Type") or "").strip()
        slug = label_to_slug.get(label)
        if slug is None:
            unmatched.append(label)
            continue
        counts[slug] = counts.get(slug, 0) + 1
        questions.append(
            {
                "csv_row": idx,
                "category_slug": slug,
                "question_type_label": label,
                "question": (row.get("Question") or "").strip(),
            }
        )

    if unmatched:
        raise RuntimeError(
            "CSV Question Type values don't match leaderboard category labels. "
            f"Unknown labels: {sorted(set(unmatched))!r}. "
            f"Known labels: {sorted(label_to_slug)!r}."
        )

    return {
        "source": str(csv_path.relative_to(REPO_ROOT)),
        "note": (
            "Maps each of the 50 public questions to one of the 9 Vals Finance "
            "Agent category slugs via the CSV's 'Question Type' column. Use "
            "this to aggregate per-task audit severities up to the category "
            "level without manual assignment. Covers only the public split; "
            f"Vals's full benchmark is {TOTAL_QUESTIONS} questions."
        ),
        "num_questions": len(questions),
        "num_total_questions": TOTAL_QUESTIONS,
        "num_by_category_slug": dict(sorted(counts.items())),
        "category_label_to_slug": dict(sorted(label_to_slug.items())),
        "questions": questions,
    }


def build_leaderboard(bv: dict, rows: dict[str, dict]) -> dict:
    meta = bv["metadata"]
    entries = []
    for slug, r in rows.items():
        category_scores = {
            t["task_name"]: t["accuracy"] for t in r["tasks"]
        }
        entries.append(
            {
                "slug": slug,
                "model_key": r["model_key"],
                "provider": r["provider"],
                "overall_accuracy": r["overall_accuracy"],
                "overall_stderr": r["overall_stderr"],
                "overall_cost_per_test": r["overall_cost_per_test"],
                "overall_latency": r["overall_latency"],
                "temperature": r["temperature"],
                "top_p": r["top_p"],
                "reasoning": r["reasoning"],
                "reasoning_effort": r["reasoning_effort"],
                "verbosity": r["verbosity"],
                "compute_effort": r["compute_effort"],
                "category_accuracy": category_scores,
            }
        )
    entries.sort(key=lambda r: -(r["overall_accuracy"] or 0))

    return {
        "source_url": SOURCE_URL,
        "benchmark": meta.get("benchmark"),
        "slug": meta.get("slug"),
        "benchmark_id": meta.get("benchmark_id"),
        "description": meta.get("description"),
        "industry": meta.get("industry"),
        "dataset_type": meta.get("dataset_type"),  # "private"
        "updated": meta.get("updated"),
        "num_entries": len(entries),
        "num_categories": len(meta.get("tasks", {})) - 1,  # minus "overall"
        "categories": {k: v for k, v in meta.get("tasks", {}).items() if k != "overall"},
        "per_question_data_available": False,
        "scoring_note": (
            "Accuracy values are percentage correct on the private evaluation "
            "set; stderr is what Vals AI reports on the page. Vals does not "
            "publish per-question pass/fail."
        ),
        "schema": {
            "slug": "Filesystem-safe model id (underscores, matches /models/<slug> URL)",
            "model_key": "Original provider/model key (e.g. anthropic/claude-opus-4-7)",
            "provider": "Provider display name",
            "overall_accuracy": "Aggregate accuracy across all categories (0-100, percent)",
            "overall_stderr": "Standard error on overall accuracy (percentage points)",
            "overall_cost_per_test": "USD cost per evaluation example",
            "category_accuracy": "Per-category accuracy, keyed by category slug",
            "reasoning / reasoning_effort / compute_effort": "Reasoning config as reported",
        },
        "entries": entries,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--html-cache",
        default=None,
        help="Path to a previously-saved page HTML (skip the network fetch)",
    )
    ap.add_argument(
        "--public-csv",
        default=str(DEFAULT_PUBLIC_CSV),
        help=(
            "Path to the 50-question public split CSV. Used to emit "
            "public_questions.json (question → category slug mapping). "
            "If the file is missing the step is skipped."
        ),
    )
    args = ap.parse_args()

    print("=" * 72)
    print("Vals AI Finance Agent leaderboard refresh")
    print(f"  source: {SOURCE_URL}")
    print(f"  output: {HERE}")
    print("=" * 72)

    if args.html_cache:
        html = Path(args.html_cache).read_text()
        print(f"[1/3] loaded cached HTML ({len(html):,} bytes)")
    else:
        print("[1/3] fetching page HTML")
        html = fetch(SOURCE_URL)
        print(f"       got {len(html):,} bytes")

    print("[2/3] extracting BenchmarkView astro-island props")
    bv = extract_benchmark_view(html)
    meta = bv["metadata"]
    print(
        f"       benchmark={meta.get('benchmark')!r}  "
        f"models={meta.get('total_models')}  updated={meta.get('updated')}"
    )

    print("[3/3] building outputs")
    rows = build_rows(bv)
    (HERE / "rows").mkdir(exist_ok=True)
    for slug, r in rows.items():
        (HERE / "rows" / f"{slug}.json").write_text(json.dumps(r, indent=2))

    (HERE / "leaderboard.json").write_text(
        json.dumps(build_leaderboard(bv, rows), indent=2)
    )
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_categories": len([c for c in bv["tasks"] if c != "overall"]),
                "updated": meta.get("updated"),
                "rows": build_rows_index(rows),
            },
            indent=2,
        )
    )
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(build_per_task_matrix(bv, rows), indent=2)
    )

    csv_path = Path(args.public_csv)
    public_questions = build_public_questions(bv, csv_path)
    if public_questions is None:
        print(
            f"       public.csv not found at {csv_path} — "
            "skipping public_questions.json"
        )
    else:
        (HERE / "public_questions.json").write_text(
            json.dumps(public_questions, indent=2)
        )
        counts = public_questions["num_by_category_slug"]
        print(
            f"       public_questions: {public_questions['num_questions']} "
            f"across {len(counts)} categories"
        )

    print()
    print("done. outputs:")
    for f in (
        "leaderboard.json",
        "rows_index.json",
        "per_task_matrix.json",
        "public_questions.json",
    ):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list((HERE / "rows").glob("*.json")))
    print(f"  rows/  ({n} files)")


if __name__ == "__main__":
    main()
