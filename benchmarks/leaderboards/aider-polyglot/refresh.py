#!/usr/bin/env python3
"""Refresh the Aider Polyglot leaderboard snapshot.

Single source — the leaderboard YAML that backs https://aider.chat/docs/leaderboards/:

  https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml

Each entry is an aggregate row: pass rates / counts, token and cost totals,
edit-format metadata. Aider does NOT publish per-exercise pass/fail — individual
benchmark runs produce a local `tmp.benchmarks/<dirname>/` with `.aider.results.json`
per exercise, but those folders are never uploaded. So there is no per_task_matrix
to build, and no rows/ directory with per-exercise data.

Outputs (all under this directory):
  leaderboard.json   # raw entries, verbatim from YAML, plus header metadata
  rows_index.json    # normalized per-row summary, sorted by pass_rate_2 desc

Usage:
  python refresh.py          # full refresh
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import time
import urllib.request
from pathlib import Path

import yaml


def _json_default(o):
    """YAML parses `date: 2025-02-25` as a date — stringify for JSON."""
    if isinstance(o, (_dt.date, _dt.datetime)):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

HERE = Path(__file__).resolve().parent

YAML_URL = (
    "https://raw.githubusercontent.com/Aider-AI/aider/main/"
    "aider/website/_data/polyglot_leaderboard.yml"
)


def fetch(url: str, retries: int = 4) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "aider-polyglot-leaderboard-refresh/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def write_leaderboard(entries: list[dict], out: Path) -> None:
    out.write_text(
        json.dumps(
            {
                "source_url": YAML_URL,
                "benchmark": "aider-polyglot",
                "num_entries": len(entries),
                "note": (
                    "Aider does not publish per-exercise pass/fail data. Every field "
                    "here is aggregate. `pass_rate_2` is the headline metric (pct "
                    "cases solved in <=2 attempts)."
                ),
                "schema": {
                    "dirname": "Unique slug (timestamp--run-name); matches the local tmp.benchmarks/<dirname>",
                    "model": "Model display name",
                    "edit_format": "diff | whole | architect | ...",
                    "editor_model": "Secondary editor model for architect mode (null otherwise)",
                    "editor_edit_format": "Edit format used by the editor model",
                    "reasoning_effort": "Reasoning-effort setting (for models that expose it)",
                    "commit_hash": "Aider commit at which the run was executed",
                    "date": "Run date (YYYY-MM-DD)",
                    "versions": "Aider version string",
                    "test_cases / total_tests": "Number of exercises in the run (normally 225)",
                    "pass_rate_1 / pass_rate_2": "Pct solved in 1 / <=2 attempts",
                    "pass_num_1 / pass_num_2": "Absolute counts for those rates",
                    "percent_cases_well_formed": "Pct of model outputs that parsed correctly",
                    "num_malformed_responses / num_with_malformed_responses": "Counts of parse failures",
                    "error_outputs": "Count of model errors",
                    "user_asks": "Count of times the model asked the user a question",
                    "lazy_comments": "Count of TODO-style lazy comments detected",
                    "syntax_errors / indentation_errors": "Post-edit code errors",
                    "exhausted_context_windows": "Count of runs that hit the context limit",
                    "test_timeouts": "Count of exercises whose tests timed out",
                    "seconds_per_case": "Wall-clock seconds per exercise",
                    "total_cost": "Total USD spent on the run",
                    "prompt_tokens / completion_tokens / thinking_tokens": "Token totals (newer entries only)",
                    "command": "Aider command used to run this model",
                },
                "entries": entries,
            },
            indent=2,
            default=_json_default,
        )
    )
    print(f"  -> wrote {out.relative_to(HERE)} ({len(entries)} entries)")


_INDEX_KEYS = (
    "dirname",
    "model",
    "edit_format",
    "editor_model",
    "editor_edit_format",
    "reasoning_effort",
    "date",
    "versions",
    "test_cases",
    "pass_rate_1",
    "pass_rate_2",
    "pass_num_1",
    "pass_num_2",
    "percent_cases_well_formed",
    "total_cost",
    "seconds_per_case",
    "prompt_tokens",
    "completion_tokens",
    "thinking_tokens",
)


def build_rows_index(entries: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for e in entries:
        pr2 = e.get("pass_rate_2")
        row = {
            "slug": e.get("dirname"),
            "accuracy": (pr2 / 100.0) if isinstance(pr2, (int, float)) else None,
        }
        for k in _INDEX_KEYS:
            if k in e:
                row[k] = e[k]
        rows.append(row)
    rows.sort(key=lambda r: -(r["accuracy"] or 0))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.parse_args()

    print("=" * 72)
    print("Aider Polyglot leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    print("[1/2] fetching polyglot_leaderboard.yml")
    data = yaml.safe_load(fetch(YAML_URL))
    if not isinstance(data, list):
        raise RuntimeError("Expected YAML top-level to be a list")
    print(f"  parsed {len(data)} entries")

    print("[2/2] writing leaderboard.json + rows_index.json")
    write_leaderboard(data, HERE / "leaderboard.json")
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {"num_rows": len(data), "rows": build_rows_index(data)},
            indent=2,
            default=_json_default,
        )
    )

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    print("  (no rows/ or per_task_matrix.json — per-exercise data is not published upstream)")


if __name__ == "__main__":
    main()
