#!/usr/bin/env python3
"""Refresh the LongBench v2 leaderboard snapshot.

LongBench v2 (arXiv:2412.15204, THUDM/Tsinghua + Z.ai) is a 503-question
multiple-choice benchmark covering long-context reasoning from 8k to 2M
words. Each question has difficulty (easy/hard), length (short/medium/long),
and domain/sub_domain labels. Scoring is accuracy % (4-way MCQ).

Sources:

  1. https://longbench2.github.io/
     Project site. The leaderboard is **hard-coded inline** as an HTML
     table inside `index.html` — the referenced JS files
     (`static/js/results/*.js`) 404. We parse the `<tbody>` of
     `<table id="results">` directly.

  2. https://datasets-server.huggingface.co/rows?dataset=zai-org/LongBench-v2&config=default&split=train
     Paginated rows API for the 503-question universe. We fetch metadata
     only (drop `context`, `question`, `choice_*` to keep the snapshot
     small) so subset recomputation by difficulty/length/domain stays
     possible even though per-model predictions aren't published.

**Per-instance predictions are NOT published**. The upstream repo
(THUDM/LongBench) only ships the eval code (`pred.py`, `result.py`); no
`pred/`, `results/`, or submissions directory exists on GitHub or HF.
Aggregate scores are published across six cuts — Overall / Easy / Hard /
Short / Medium / Long — each reported with and without CoT. Reasoning
models (flagged 🧠 in the table) report CoT only.

Outputs (all under this directory):
  leaderboard.json          # 36 rows with all 12 metric cuts + metadata
  rows/<slug>.json          # per-row: metadata only (no task-level trials)
  rows_index.json           # one-line summary per row, sorted by overall
  per_task_matrix.json      # task universe from HF; matrix empty (shape)

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-tasks     # skip HF task-universe fetch
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = "https://longbench2.github.io/"

HF_DATASET = "zai-org/LongBench-v2"  # THUDM/LongBench-v2 redirects here
HF_ROWS_API = (
    "https://datasets-server.huggingface.co/rows"
    f"?dataset={urllib.parse.quote(HF_DATASET, safe='')}"
    "&config=default&split=train"
)
HF_ROWS_PAGE = 100  # datasets-server max is usually 100


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "longbench-v2-leaderboard-refresh/0.1"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Leaderboard scrape
# --------------------------------------------------------------------------- #
BRAIN = "\U0001f9e0"  # 🧠 marker for native-reasoning models

# Non-greedy row match anywhere inside the `results` tbody.
ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
TBODY_RE = re.compile(
    r'<table[^>]*id="results"[^>]*>.*?<tbody>(.*?)</tbody>', re.DOTALL
)
HREF_RE = re.compile(r'href="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    """Strip tags + collapse whitespace + decode HTML entities."""
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _num_or_none(cell: str) -> float | None:
    """`-` (or empty) means "not reported"; anything else is a percent."""
    s = _clean(cell).replace("-", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _split_model_cell(cell: str) -> dict:
    """Pull model name, link, company, and reasoning flag from the first td."""
    href_m = HREF_RE.search(cell)
    link = href_m.group(1) if href_m else None

    # Company: the last small-gray <p> inside the cell.
    company = None
    for m in re.finditer(
        r'<p[^>]*color:\s*#858383[^>]*>(.*?)</p>', cell, re.DOTALL
    ):
        company = _clean(m.group(1)) or None
    # Some rows inline the company <p> with no closing </p> before the </td>;
    # fall back to a looser pattern.
    if not company:
        m2 = re.search(
            r'color:\s*#858383[^>]*>([^<]+)', cell, re.DOTALL
        )
        if m2:
            company = _clean(m2.group(1)) or None

    reasoning = BRAIN in cell

    # Model name: strip the <p> (company) and the 🧠 span, keep the <a>'s text.
    name_cell = re.sub(
        r'<p[^>]*color:\s*#858383.*?(</p>|</b>|</td>)', "", cell, flags=re.DOTALL
    )
    name_cell = name_cell.replace(BRAIN, "")
    name = _clean(name_cell)
    return {"model": name, "link": link, "company": company, "reasoning": reasoning}


BASELINE_NAMES = {"Human", "Random"}


def scrape_leaderboard() -> tuple[list[dict], list[dict]]:
    """Return (model_rows, baseline_rows).

    The upstream table embeds two reference rows — `Human` (53.7%, 15-min
    constraint) and `Random` (25%, MCQ floor). Keep them separately so
    consumers can compare models against both without polluting rankings.
    """
    html = fetch(LEADERBOARD_URL).decode("utf-8", errors="replace")
    m = TBODY_RE.search(html)
    if not m:
        raise RuntimeError("could not locate <tbody> of #results table")
    body = m.group(1)

    rows: list[dict] = []
    baselines: list[dict] = []
    for row_m in ROW_RE.finditer(body):
        cells = TD_RE.findall(row_m.group(1))
        if len(cells) < 17:
            # Header/stray row — skip.
            continue
        model_info = _split_model_cell(cells[1])
        target = baselines if model_info["model"] in BASELINE_NAMES else rows
        target.append(
            {
                "model": model_info["model"],
                "link": model_info["link"],
                "company": model_info["company"],
                "reasoning": model_info["reasoning"],
                "params": _clean(cells[2]) or None,
                "context": _clean(cells[3]) or None,
                "date": _clean(cells[4]) or None,
                "overall_wo_cot": _num_or_none(cells[5]),
                "overall_w_cot": _num_or_none(cells[6]),
                "easy_wo_cot": _num_or_none(cells[7]),
                "easy_w_cot": _num_or_none(cells[8]),
                "hard_wo_cot": _num_or_none(cells[9]),
                "hard_w_cot": _num_or_none(cells[10]),
                "short_wo_cot": _num_or_none(cells[11]),
                "short_w_cot": _num_or_none(cells[12]),
                "medium_wo_cot": _num_or_none(cells[13]),
                "medium_w_cot": _num_or_none(cells[14]),
                "long_wo_cot": _num_or_none(cells[15]),
                "long_w_cot": _num_or_none(cells[16]),
            }
        )
    return rows, baselines


# --------------------------------------------------------------------------- #
# Task universe (HF datasets-server, rows API)
# --------------------------------------------------------------------------- #
TASK_METADATA_FIELDS = ("_id", "domain", "sub_domain", "difficulty", "length", "answer")


def fetch_tasks() -> list[dict]:
    offset = 0
    out: list[dict] = []
    total: int | None = None
    while True:
        url = f"{HF_ROWS_API}&offset={offset}&length={HF_ROWS_PAGE}"
        body = json.loads(fetch(url))
        if total is None:
            total = body.get("num_rows_total")
        batch = body.get("rows", [])
        if not batch:
            break
        for r in batch:
            row = r.get("row", {})
            out.append({k: row.get(k) for k in TASK_METADATA_FIELDS})
        offset += len(batch)
        if total is not None and offset >= total:
            break
    return out


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def row_slug(model: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")
    return s or "row"


SCHEMA = {
    "model": "Model name as shown on the leaderboard",
    "link": "Canonical link for the model (HF / provider page)",
    "company": "Submitter / provider (Google, OpenAI, Anthropic, Alibaba, ...)",
    "reasoning": (
        "True for native-reasoning models (🧠 in the source table). "
        "Reasoning models natively use CoT, so only w/ CoT is reported."
    ),
    "params": "Self-reported parameter count (e.g. '72B', '1T'); '-' if unknown",
    "context": "Advertised context window (e.g. '128k', '1M', '2M')",
    "date": "Release / submission date (YYYY-MM-DD)",
    "overall_wo_cot": "Overall accuracy % without CoT (null if not reported)",
    "overall_w_cot": "Overall accuracy % with CoT (null if not reported)",
    "easy_wo_cot": "Accuracy % on easy questions, no CoT",
    "easy_w_cot": "Accuracy % on easy questions, with CoT",
    "hard_wo_cot": "Accuracy % on hard questions, no CoT",
    "hard_w_cot": "Accuracy % on hard questions, with CoT",
    "short_wo_cot": "Accuracy % on short (≤32k) questions, no CoT",
    "short_w_cot": "Accuracy % on short (≤32k) questions, with CoT",
    "medium_wo_cot": "Accuracy % on medium (32k–128k) questions, no CoT",
    "medium_w_cot": "Accuracy % on medium (32k–128k) questions, with CoT",
    "long_wo_cot": "Accuracy % on long (128k–2M) questions, no CoT",
    "long_w_cot": "Accuracy % on long (128k–2M) questions, with CoT",
}


def write_leaderboard(rows: list[dict], baselines: list[dict], num_tasks: int) -> None:
    entries = sorted(
        rows, key=lambda r: -(r.get("overall_w_cot") or r.get("overall_wo_cot") or -1)
    )
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "source_url": LEADERBOARD_URL,
                "source_dataset": f"https://huggingface.co/datasets/{HF_DATASET}",
                "benchmark": "longbench-v2",
                "split": "train",  # only split published; it's the test set
                "scoring": "accuracy % (4-way MCQ, single trial)",
                "num_entries": len(entries),
                "num_tasks": num_tasks,
                "splits": {
                    "difficulty": ["easy", "hard"],
                    "length": ["short (0-32k)", "medium (32k-128k)", "long (128k-2M)"],
                    "cot": ["w/o CoT", "w/ CoT"],
                },
                "baselines": baselines,
                "schema": SCHEMA,
                "entries": entries,
            },
            indent=2,
        )
    )


def write_rows(rows: list[dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for old in rows_dir.glob("*.json"):
        old.unlink()
    seen: dict[str, int] = {}
    for r in rows:
        slug = row_slug(r["model"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}__{seen[slug]}"
        else:
            seen[slug] = 1
        entry = {
            "slug": slug,
            **r,
            # No per-instance predictions are published for LongBench v2.
            # Shape-compatible fields kept null so downstream tools can
            # treat this uniformly with other leaderboards.
            "num_tasks": None,
            "total_trials": None,
            "total_successes": None,
            "tasks": [],
        }
        (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))


def write_rows_index(rows: list[dict]) -> None:
    missing: list[dict] = []
    seen: dict[str, int] = {}
    for r in rows:
        slug = row_slug(r["model"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}__{seen[slug]}"
        else:
            seen[slug] = 1
        # Canonical overall = w/ CoT when reported, else w/o CoT. Expressed
        # as both percent (original units) and 0-1 for cross-benchmark keys.
        overall_pct = r.get("overall_w_cot") or r.get("overall_wo_cot")
        missing.append(
            {
                "slug": slug,
                "model": r["model"],
                "company": r["company"],
                "reasoning": r["reasoning"],
                "params": r["params"],
                "context": r["context"],
                "date": r["date"],
                "overall_pct": overall_pct,
                "accuracy": (overall_pct / 100.0) if overall_pct is not None else None,
                "overall_w_cot": r.get("overall_w_cot"),
                "overall_wo_cot": r.get("overall_wo_cot"),
                "easy_w_cot": r.get("easy_w_cot"),
                "hard_w_cot": r.get("hard_w_cot"),
                "short_w_cot": r.get("short_w_cot"),
                "medium_w_cot": r.get("medium_w_cot"),
                "long_w_cot": r.get("long_w_cot"),
                "num_tasks": None,
                "total_trials": None,
                "recomputed_pass_rate": None,
            }
        )
    missing.sort(key=lambda r: -(r["overall_pct"] or 0))
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": 0,
                "num_missing_detail": len(missing),
                "note": (
                    "LongBench v2 publishes aggregate accuracy only. The "
                    "503-question dataset is public (zai-org/LongBench-v2 on "
                    "HF) but upstream does not ship per-model predictions — "
                    "the repo (THUDM/LongBench) only includes eval code. "
                    "Every row lives in `missing_detail`; `per_task_matrix. "
                    "json` carries the task universe but an empty matrix."
                ),
                "rows": [],
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_matrix(tasks: list[dict]) -> None:
    """Task universe + empty matrix.

    Unlike HLE (where the dataset is also gated), LongBench v2's tasks are
    public, so we list them with difficulty/length/domain labels. The
    `matrix` stays empty because no submission publishes per-question
    predictions — downstream tools can still filter task_ids by attribute
    if they later obtain a predictions dump.
    """
    task_levels = {
        t["_id"]: {
            "difficulty": t.get("difficulty"),
            "length": t.get("length"),
            "domain": t.get("domain"),
            "sub_domain": t.get("sub_domain"),
        }
        for t in tasks
    }
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "Per-model per-question predictions are not published for "
                    "LongBench v2. The 503-question dataset itself is public "
                    "(zai-org/LongBench-v2), so we list every task_id with its "
                    "difficulty/length/domain labels in `tasks` and "
                    "`task_levels`. `matrix` is empty; the file exists for "
                    "shape parity with other leaderboards."
                ),
                "tasks": [
                    {
                        "task_id": t["_id"],
                        "difficulty": t.get("difficulty"),
                        "length": t.get("length"),
                        "domain": t.get("domain"),
                        "sub_domain": t.get("sub_domain"),
                    }
                    for t in tasks
                ],
                "task_levels": task_levels,
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
    print("LongBench v2 leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    matrix_path = HERE / "per_task_matrix.json"
    if args.skip_tasks:
        if matrix_path.exists():
            tasks = [
                {
                    "_id": t["task_id"],
                    "difficulty": t.get("difficulty"),
                    "length": t.get("length"),
                    "domain": t.get("domain"),
                    "sub_domain": t.get("sub_domain"),
                }
                for t in json.loads(matrix_path.read_text()).get("tasks", [])
            ]
            print(f"[1/4] skip tasks — reused {len(tasks)} tasks from per_task_matrix.json")
        else:
            tasks = []
            print("[1/4] skip tasks — no matrix cached, tasks list will be empty")
    else:
        print("[1/4] fetching task universe from HF datasets-server")
        tasks = fetch_tasks()
        print(f"  {len(tasks)} tasks")

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[2/4] skip scrape — reusing leaderboard.json")
        cached = json.loads(leaderboard_path.read_text())
        rows = cached["entries"]
        baselines = cached.get("baselines", [])
    else:
        print("[2/4] scraping longbench2.github.io leaderboard")
        rows, baselines = scrape_leaderboard()
        print(f"  scraped {len(rows)} model rows + {len(baselines)} baselines")

    print("[3/4] writing leaderboard.json + rows/")
    write_leaderboard(rows, baselines, num_tasks=len(tasks))
    write_rows(rows)

    print("[4/4] writing rows_index.json + per_task_matrix.json")
    write_rows_index(rows)
    write_matrix(tasks)

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list((HERE / "rows").glob("*.json")))
    print(f"  rows/  ({n} files)")


if __name__ == "__main__":
    main()
