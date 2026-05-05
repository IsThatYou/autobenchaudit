#!/usr/bin/env python3
"""Refresh the Humanity's Last Exam (HLE) leaderboard snapshot.

Source: https://labs.scale.com/leaderboard/humanitys_last_exam
  A Next.js page. The leaderboard payload lives in `self.__next_f.push`
  chunks as a JS `entries` array with one object per submission:
    {model, version, rank, score, confidenceInterval_upper,
     contaminationMessage, company, createdAt, isNew, deprecated,
     calibrationError, maxScore}

Scale also documents the benchmark at agi.safe.ai and ships the 2,500
questions behind a gated HuggingFace dataset (`cais/hle`) that requires
accepting a terms-of-use form. **Per-model, per-question predictions
are not published** for HLE as of this snapshot — Scale holds a private
subset specifically to limit training-data leakage, and the questions
themselves are not re-exported with submission results.

Outputs (all under this directory):
  leaderboard.json          # all entries scraped from the Scale page
  rows/<slug>.json          # per-row: metadata only (no task-level trials)
  rows_index.json           # one-line summary per row, sorted by accuracy
  per_task_matrix.json      # shape placeholder: empty tasks + empty matrix

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = "https://labs.scale.com/leaderboard/humanitys_last_exam"


def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "hle-leaderboard-refresh/0.1"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Scrape labs.scale.com
# --------------------------------------------------------------------------- #
def _join_next_f_chunks(html: str) -> str:
    """Concatenate + unicode-escape decode all `self.__next_f.push` payloads."""
    chunks = re.findall(r'self\.__next_f\.push\(\[\d+,\"(.+?)\"\]\)', html, re.DOTALL)
    return bytes("".join(chunks), "utf-8").decode("unicode_escape")


def _extract_entries_array(payload: str) -> list[dict]:
    """Pull the `entries` JSON array out of the decoded payload.

    Same approach as the MCP Atlas refresh: locate the anchor and balance
    brackets (while honoring string literals) to find the closing `]`.
    """
    m = re.search(r'"entries":\[\{"model":', payload)
    if not m:
        raise RuntimeError('Could not locate `"entries":[{"model":` in page source')
    start = m.start() + len('"entries":')
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
    entries = _extract_entries_array(payload)

    rows: list[dict] = []
    for e in entries:
        msg = e.get("contaminationMessage") or ""
        msg = msg.strip() or None
        rows.append(
            {
                "rank": e.get("rank"),
                "model": (e.get("model") or "").strip(),
                "company": e.get("company"),
                "version": (e.get("version") or None),
                "created_at": e.get("createdAt"),
                "deprecated": e.get("deprecated", False),
                "is_new": e.get("isNew", False),
                "contamination_message": msg,
                "accuracy": e.get("score"),  # percent, 0-100
                "ci_upper": e.get("confidenceInterval_upper"),
                "calibration_error": e.get("calibrationError"),
                "max_score": e.get("maxScore"),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def row_slug(model: str) -> str:
    """Filesystem-safe slug for a leaderboard row."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")
    return s or "row"


def write_leaderboard(rows: list[dict]) -> None:
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "source_url": LEADERBOARD_URL,
                "benchmark": "humanitys-last-exam",
                "num_entries": len(rows),
                "schema": {
                    "rank": "Leaderboard rank (UB: 1 + # models whose lower CI beats this row's upper CI)",
                    "model": "Model name as shown in the page payload (keeps reasoning-knob suffix)",
                    "company": "Provider code (google, openai, anthropic, meta, moonshot, zai, ...)",
                    "version": "Model version string (usually blank)",
                    "created_at": "ISO 8601 submission timestamp",
                    "deprecated": "True if the row is flagged deprecated",
                    "is_new": "True if the row is flagged as newly added",
                    "contamination_message": (
                        "Free-text contamination / caveat note. HLE flags "
                        "nearly every post-release submission as potentially "
                        "contaminated because the dataset is public."
                    ),
                    "accuracy": "Accuracy % over the 2,500-question benchmark (0-100)",
                    "ci_upper": "Upper half-width of the confidence interval for accuracy",
                    "calibration_error": (
                        "Calibration error % — lower is better. Higher values "
                        "indicate the model is overconfident when wrong."
                    ),
                    "max_score": "Theoretical score ceiling (~49.85% as of April 2026)",
                },
                "entries": rows,
            },
            indent=2,
        )
    )


def write_rows(rows: list[dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    # Clear stale rows to avoid leaving orphaned slugs from a previous run.
    for old in rows_dir.glob("*.json"):
        old.unlink()
    for r in rows:
        slug = row_slug(r["model"])
        entry = {
            "slug": slug,
            "model": r["model"],
            "company": r["company"],
            "rank": r["rank"],
            "created_at": r["created_at"],
            "accuracy": r["accuracy"],
            "ci_upper": r["ci_upper"],
            "calibration_error": r["calibration_error"],
            "max_score": r["max_score"],
            "deprecated": r["deprecated"],
            "is_new": r["is_new"],
            "contamination_message": r["contamination_message"],
            # No per-instance predictions are published for HLE. Shape-
            # compatible fields kept null so downstream tools don't have to
            # special-case this benchmark.
            "num_tasks": None,
            "total_trials": None,
            "total_successes": None,
            "tasks": [],
        }
        (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))


def write_rows_index(rows: list[dict]) -> None:
    missing: list[dict] = []
    for r in rows:
        acc = r["accuracy"]
        missing.append(
            {
                "slug": row_slug(r["model"]),
                "model": r["model"],
                "company": r["company"],
                "rank": r["rank"],
                "created_at": r["created_at"],
                "accuracy_pct": acc,
                # Canonical 0–1 accuracy so cross-benchmark consumers can key
                # on a single field name.
                "accuracy": (acc / 100.0) if acc is not None else None,
                "ci_upper": r["ci_upper"],
                "calibration_error": r["calibration_error"],
                "num_tasks": None,
                "total_trials": None,
                "recomputed_pass_rate": None,
            }
        )
    missing.sort(key=lambda r: -(r["accuracy_pct"] or 0))
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": 0,
                "num_missing_detail": len(missing),
                "note": (
                    "HLE publishes aggregate accuracy only. The 2,500 questions "
                    "sit behind a gated HuggingFace dataset (cais/hle) and "
                    "Scale does not re-export per-model predictions. Every row "
                    "lives in `missing_detail`; `per_task_matrix.json` is a "
                    "shape placeholder."
                ),
                "rows": [],
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_matrix_placeholder() -> None:
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "Per-model per-question results are not published for "
                    "Humanity's Last Exam. The 2,500-question dataset "
                    "(cais/hle on HuggingFace) is gated behind a "
                    "click-through agreement, and Scale withholds model "
                    "predictions to limit training-data leakage. `tasks` and "
                    "`matrix` are both empty; the file exists for shape "
                    "parity with other leaderboards."
                ),
                "tasks": [],
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
    args = ap.parse_args()

    print("=" * 72)
    print("HLE leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/2] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/2] scraping labs.scale.com leaderboard")
        rows = scrape_leaderboard()
        write_leaderboard(rows)
        print(f"  -> wrote leaderboard.json ({len(rows)} entries)")

    print("[2/2] writing rows/ + rows_index.json + per_task_matrix.json")
    write_rows(rows)
    write_rows_index(rows)
    write_matrix_placeholder()

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
