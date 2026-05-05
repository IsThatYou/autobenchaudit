#!/usr/bin/env python3
"""Refresh the MCP Atlas leaderboard snapshot.

Two sources used end-to-end:

  1. https://labs.scale.com/leaderboard/mcp_atlas
     A Next.js page whose leaderboard payload lives in `self.__next_f.push`
     chunks. The primary score (Pass Rate % over all 1,000 tasks, with CI
     upper bound + createdAt + company + rank) is serialized as a JS
     `entries` array; the Public 500 score appears in a separate HTML
     `tableRow` block. We pull from both and join by model name.
  2. https://huggingface.co/datasets/ScaleAI/MCP-Atlas
     The 500-task public subset (single parquet file). We enumerate task
     IDs + ENABLED_TOOLS size + a prompt preview so consumers can key a
     per-task view even though Scale does not publish per-model,
     per-instance pass/fail data.

No per-instance model results are published by Scale (April 2026 snapshot).
Every row therefore lands in `rows_index.json` → `missing_detail` and
`rows/<slug>.json` carries metadata only (no `tasks` array).
`per_task_matrix.json` contains the task list with an empty matrix — the
shape matches other leaderboards so tools can be reused once per-task data
becomes available.

Outputs (all under this directory):
  leaderboard.json          # 18 leaderboard entries with both pass-rate metrics
  rows/<slug>.json          # per-row: metadata only (no task-level trials)
  rows_index.json           # one-line summary per row, sorted by pass_at_1_all
  tasks.json                # 500 tasks from the HF parquet (id, enabled_tools count, prompt preview)
  per_task_matrix.json      # task list + empty matrix (no per-task results published)

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-tasks     # reuse existing tasks.json (skip parquet download)
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = "https://labs.scale.com/leaderboard/mcp_atlas"
HF_PARQUET_URL = (
    "https://huggingface.co/datasets/ScaleAI/MCP-Atlas/resolve/main/MCP-Atlas.parquet"
)


def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "mcp-atlas-leaderboard-refresh/0.1"}
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Step 1: scrape labs.scale.com leaderboard page
# --------------------------------------------------------------------------- #
def _join_next_f_chunks(html: str) -> str:
    """Concatenate + unescape all self.__next_f.push payloads.

    Each chunk is a JS string with `\\n`, `\\"`, etc. We decode via
    `unicode_escape` so downstream JSON-ish substrings parse cleanly.
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[\d+,\"(.+?)\"\]\)', html, re.DOTALL)
    return bytes("".join(chunks), "utf-8").decode("unicode_escape")


def _extract_entries_array(payload: str) -> list[dict]:
    """Pull the leaderboard `entries` array out of the Next.js payload.

    The array is literal JSON in the page source (an array of model objects
    with fields like `model`, `score`, `rank`, `company`, `createdAt`). We
    locate it by its opening anchor — `"entries":[` followed by a `{"model":`
    — and balance brackets to find the end.
    """
    anchor_re = re.compile(r'"entries":\[\{"model":')
    m = anchor_re.search(payload)
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

    raw = payload[start : i + 1]
    return json.loads(raw)


def _extract_public500_table(payload: str) -> dict[str, tuple[float, float]]:
    """Pull the per-model (all_1000, public_500) pair from the HTML table.

    The leaderboard also renders a plain `tableRow` list with three cells:
    `[model_name, "xx.x%", "yy.y%"]`. Only rows whose last two cells both
    end in `%` and whose first cell is a recognizable model name belong to
    the main leaderboard (there are separate failure-taxonomy tables on the
    same page that must be filtered out).
    """
    out: dict[str, tuple[float, float]] = {}
    for m in re.finditer(r'"cells":\[([^\]]+)\]', payload):
        cells_raw = m.group(1)
        cells = re.findall(r'"((?:[^"\\]|\\.)*)"', cells_raw)
        if len(cells) < 3:
            continue
        name, c1, c2 = cells[0], cells[1], cells[2]
        # both trailing cells must be "xx.x%"
        if not (c1.endswith("%") and c2.endswith("%")):
            continue
        # skip rows where the value looks like a range (taxonomy table)
        if "-" in c1 or "-" in c2 or "~" in c1:
            continue
        try:
            v1 = float(c1.rstrip("%"))
            v2 = float(c2.rstrip("%"))
        except ValueError:
            continue
        # normalize tabs/extra spaces in model name
        clean_name = re.sub(r"\s+", " ", name.replace("\\t", " ")).strip()
        out[clean_name] = (v1, v2)
    return out


def _norm_model(name: str) -> str:
    """Loose match key: lowercase, drop all non-alphanumerics."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _base_model_token(name: str) -> str:
    """Drop parenthesized knob text; keep only the leading model identifier.

    e.g. "GPT-5.4 (reasoning = xhigh)" → "gpt54"
         "OpenAI o3 Pro" → "openaio3pro"
    Used for reconciling the JS `entries` array (labels like
    `thinking_level = high`) against the HTML table (labels like
    `reasoning_effort = high`) when the knob text disagrees.
    """
    base = re.split(r"[\(\[]", name, 1)[0]
    return _norm_model(base)


def scrape_leaderboard() -> list[dict]:
    html = fetch(LEADERBOARD_URL).decode("utf-8", errors="replace")
    payload = _join_next_f_chunks(html)

    entries = _extract_entries_array(payload)
    public_table = _extract_public500_table(payload)

    # Normalized-name index for the HTML table. We keep both a fully-
    # normalized key and a "base model token" key (parenthesized knob text
    # stripped) so we can recover when the React `entries` array names a
    # row with a different reasoning knob than the HTML table does.
    table_by_norm: dict[str, tuple[str, tuple[float, float]]] = {}
    table_by_score: dict[float, list[tuple[str, tuple[float, float]]]] = {}
    for tname, pair in public_table.items():
        table_by_norm[_norm_model(tname)] = (tname, pair)
        table_by_score.setdefault(round(pair[0], 1), []).append((tname, pair))

    rows: list[dict] = []
    used_table_names: set[str] = set()
    for e in entries:
        model = e["model"]
        norm = _norm_model(model)
        pub_match = table_by_norm.get(norm)
        # fallback 1: either direction prefix match on fully-normalized names
        if pub_match is None:
            for k, v in table_by_norm.items():
                if v[0] in used_table_names:
                    continue
                if k.startswith(norm) or norm.startswith(k):
                    pub_match = v
                    break
        # fallback 2: match by All-1000 score + base-model prefix. Handles
        # cases where the knob name differs between the two payloads
        # (`reasoning = xhigh` vs `reasoning_effort = xhigh`) or the table
        # carries a provider prefix (`OpenAI o3 Pro` vs `o3 pro`).
        if pub_match is None:
            entry_base = _base_model_token(model)
            candidates = table_by_score.get(round(e["score"], 1), [])
            for tname, pair in candidates:
                if tname in used_table_names:
                    continue
                tbase = _base_model_token(tname)
                if (
                    tbase == entry_base
                    or tbase.startswith(entry_base)
                    or entry_base.startswith(tbase)
                    or entry_base in tbase
                    or tbase in entry_base
                ):
                    pub_match = (tname, pair)
                    break

        pass_at_1_all = e["score"]
        pass_at_1_pub: float | None = None
        table_model_name: str | None = None
        if pub_match is not None:
            table_model_name, (v1, v2) = pub_match
            pass_at_1_pub = v2
            used_table_names.add(table_model_name)
            # sanity-check the join: v1 (All 1000 column) should match score
            if abs(v1 - pass_at_1_all) > 0.15:
                print(
                    f"  warn: All-1000 mismatch for {model!r}: "
                    f"entries.score={pass_at_1_all} vs table={v1}",
                    file=sys.stderr,
                )

        rows.append(
            {
                "rank": e.get("rank"),
                "model": model,
                "model_table_name": table_model_name,
                "company": e.get("company"),
                "version": e.get("version") or None,
                "created_at": e.get("createdAt"),
                "deprecated": e.get("deprecated", False),
                "is_new": e.get("isNew", False),
                "contamination_message": e.get("contaminationMessage") or None,
                # Pass rates are advertised as percentages (0-100).
                "pass_at_1_all_1000": pass_at_1_all,
                "pass_at_1_public_500": pass_at_1_pub,
                "ci_upper_all_1000": e.get("confidenceInterval_upper"),
                "max_score": e.get("maxScore"),
            }
        )

    unmatched = [r["model"] for r in rows if r["pass_at_1_public_500"] is None]
    if unmatched:
        print(
            f"  warn: {len(unmatched)} leaderboard rows had no Public-500 "
            f"match: {unmatched}",
            file=sys.stderr,
        )
    return rows


# --------------------------------------------------------------------------- #
# Step 2: fetch task list from the HF parquet
# --------------------------------------------------------------------------- #
def fetch_task_list() -> list[dict]:
    import pyarrow.parquet as pq  # type: ignore

    raw = fetch(HF_PARQUET_URL)
    table = pq.read_table(io.BytesIO(raw))
    df = table.to_pandas()
    expected = {"TASK", "ENABLED_TOOLS", "PROMPT"}
    missing = expected - set(df.columns)
    if missing:
        raise RuntimeError(f"parquet missing columns: {missing}")

    tasks: list[dict] = []
    for _, r in df.iterrows():
        enabled = r["ENABLED_TOOLS"]
        # ENABLED_TOOLS is stored as a JSON string or list — normalize to count
        if isinstance(enabled, str):
            try:
                enabled_list = json.loads(enabled)
            except json.JSONDecodeError:
                enabled_list = [enabled]
        elif isinstance(enabled, (list, tuple)):
            enabled_list = list(enabled)
        else:
            enabled_list = []
        prompt = r["PROMPT"]
        if not isinstance(prompt, str):
            prompt = str(prompt)
        tasks.append(
            {
                "task_id": r["TASK"],
                "enabled_tools_count": len(enabled_list),
                "prompt_preview": prompt[:240] + ("…" if len(prompt) > 240 else ""),
            }
        )
    tasks.sort(key=lambda t: t["task_id"])
    return tasks


# --------------------------------------------------------------------------- #
# Step 3: writers
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
                "benchmark": "mcp-atlas",
                "num_entries": len(rows),
                "schema": {
                    "rank": "Leaderboard rank (UB: 1 + # models whose lower CI beats this row's upper CI)",
                    "model": "Model name as shown in the React entries array (preferred, includes reasoning knobs)",
                    "model_table_name": "Alternative name used in the HTML table — matched via normalized-prefix join",
                    "company": "Provider code (anthropic, openai, google, meta, kimi, zai, ...)",
                    "version": "Model version string (usually blank for MCP Atlas)",
                    "created_at": "ISO 8601 submission timestamp from the page payload",
                    "deprecated": "True if the leaderboard marks this entry as deprecated",
                    "is_new": "True if the leaderboard flags this entry as recently added",
                    "contamination_message": "Free-text contamination note (usually null)",
                    "pass_at_1_all_1000": "Pass Rate (%) over the full 1,000-task benchmark",
                    "pass_at_1_public_500": "Pass Rate (%) over the 500-task public subset (HuggingFace release)",
                    "ci_upper_all_1000": "Upper half-width of the confidence interval for pass_at_1_all_1000",
                    "max_score": "Theoretical score ceiling from Scale's eval harness",
                },
                "entries": rows,
            },
            indent=2,
        )
    )


def write_rows(rows: list[dict]) -> dict[str, dict]:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    written: dict[str, dict] = {}
    for r in rows:
        slug = row_slug(r["model"])
        entry = {
            "slug": slug,
            "model": r["model"],
            "company": r["company"],
            "rank": r["rank"],
            "created_at": r["created_at"],
            "pass_at_1_all_1000": r["pass_at_1_all_1000"],
            "pass_at_1_public_500": r["pass_at_1_public_500"],
            "ci_upper_all_1000": r["ci_upper_all_1000"],
            "max_score": r["max_score"],
            "deprecated": r["deprecated"],
            "is_new": r["is_new"],
            "contamination_message": r["contamination_message"],
            # Scale does not publish per-instance trial data for any entry.
            # These fields are kept for parity with other leaderboards and
            # will be populated if/when per-task results are released.
            "num_tasks": None,
            "total_trials": None,
            "total_successes": None,
            "tasks": [],
        }
        (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))
        written[slug] = entry
    return written


def write_rows_index(rows: list[dict], written: dict[str, dict]) -> None:
    out_rows: list[dict] = []
    missing: list[dict] = []
    for r in rows:
        slug = row_slug(r["model"])
        pass_all = r["pass_at_1_all_1000"]
        summary = {
            "slug": slug,
            "model": r["model"],
            "company": r["company"],
            "rank": r["rank"],
            "created_at": r["created_at"],
            "pass_at_1_all_1000": pass_all,
            "pass_at_1_public_500": r["pass_at_1_public_500"],
            "ci_upper_all_1000": r["ci_upper_all_1000"],
            # Canonical 0–1 pass rate so cross-benchmark tools (like the
            # visualizer) can key on a single field. We use the full 1,000
            # score since that's what the headline leaderboard ranks on.
            "accuracy": (pass_all / 100.0) if pass_all is not None else None,
            "num_tasks": None,
            "total_trials": None,
            "recomputed_pass_rate": None,
        }
        # Every row is "missing detail" as long as Scale withholds per-instance
        # results. If that changes, move rows with populated tasks to `rows`.
        missing.append(summary)

    missing.sort(key=lambda r: -(r["pass_at_1_all_1000"] or 0))
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": len(out_rows),
                "num_missing_detail": len(missing),
                "note": (
                    "Scale AI has not published per-task, per-model pass/fail "
                    "results for MCP Atlas as of the snapshot date. Every row "
                    "lives in `missing_detail`. The `tasks.json` file lists the "
                    "500 public task IDs for future per-instance joins."
                ),
                "rows": out_rows,
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_tasks_and_matrix(tasks: list[dict]) -> None:
    (HERE / "tasks.json").write_text(
        json.dumps(
            {
                "source_url": HF_PARQUET_URL,
                "num_tasks": len(tasks),
                "note": (
                    "500 public tasks from the ScaleAI/MCP-Atlas parquet. The "
                    "full benchmark has 1,000 tasks; the other 500 are held out."
                ),
                "schema": {
                    "task_id": "24-character opaque task ID from the parquet TASK column",
                    "enabled_tools_count": "Number of MCP tools the agent may call for this task",
                    "prompt_preview": "First 240 characters of the natural-language prompt",
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
                    "Per-model per-task results are not published by Scale AI. "
                    "The `tasks` list is populated so downstream tooling has a "
                    "canonical key space; `matrix` is intentionally empty and "
                    "will be backfilled if/when per-instance data is released."
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
    print("MCP Atlas leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/3] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/3] scraping labs.scale.com leaderboard")
        rows = scrape_leaderboard()
        write_leaderboard(rows)
        print(f"  -> wrote leaderboard.json ({len(rows)} entries)")

    print("[2/3] writing rows/ + rows_index.json")
    written = write_rows(rows)
    write_rows_index(rows, written)
    print(f"  -> wrote {len(written)} per-row files")

    tasks_path = HERE / "tasks.json"
    if args.skip_tasks and tasks_path.exists():
        print("[3/3] skip tasks — reusing tasks.json")
        tasks = json.loads(tasks_path.read_text())["tasks"]
    else:
        print("[3/3] downloading HF parquet for task enumeration")
        tasks = fetch_task_list()
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
