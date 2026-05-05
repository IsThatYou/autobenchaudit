#!/usr/bin/env python3
"""Refresh the AIME 2024 + AIME 2025 leaderboard snapshot (60 problems).

Scope
-----
AIME 2024 I + II + AIME 2025 I + II = 60 canonical problems.

Sources used end-to-end:

  1. https://huggingface.co/datasets/MathArena/aime_2024_I,
     /aime_2024_II, /aime_2025
     Canonical problem universe: problem statement + integer gold answer.
     MathArena stores AIME 2025 as a single 30-row dataset where
     problem_idx 1-15 maps to AIME I and 16-30 maps to AIME II.

  2. https://huggingface.co/datasets/MathArena/aime_2025_outputs
     Per-instance evaluation outputs. 7,915 rows covering 67 models and
     30 problems with up to 4 samples per (model, problem). Columns
     used: problem_idx (str), model_name, model_config, idx_answer,
     gold_answer, parsed_answer, correct, input_tokens, output_tokens,
     cost. AIME 2024 has *no* _outputs dataset on MathArena, so the
     per-instance matrix is sparse: filled for AIME 2025, empty for
     AIME 2024.

  3. https://llm-stats.com/benchmarks/aime-2024
     https://llm-stats.com/benchmarks/aime-2025
     Next.js pages whose `models` array (inside `self.__next_f.push`
     chunks) carries {rank, model_name, organization_name, score,
     verified, self_reported, self_reported_source, announcement_date,
     input/output_cost_per_million, context_window, param_count,
     is_open_source, ...}. Scores are **self-reported**; llm-stats
     `verified_count` is 0 for both boards. We mirror these to cover
     AIME 2024 (where MathArena has no outputs) and to widen AIME 2025
     coverage beyond the 67 models MathArena runs.

Row taxonomy
------------
Every row represents one model evaluated on one year from one source:

  matharena/aime_2025/<model_slug>       per-instance (30 tasks, pass@1
                                         averaged over ≤4 samples/cell)
  llmstats/aime_2024/<model_slug>        aggregate only
  llmstats/aime_2025/<model_slug>        aggregate only

The MathArena AIME 2025 row is treated as the per-instance source of
truth — llm-stats AIME 2025 rows carry no per-task detail even if they
cover the same model.

Outputs (all under this directory):
  leaderboard.json          overview rows (sorted by accuracy within year)
  tasks.json                60 canonical problems (id, year, half, idx,
                            problem text, gold answer, problem_type)
  rows/<slug>.json          per-row detail with `tasks: [...]` array
                            (populated for matharena rows, empty for
                            llmstats rows)
  rows_index.json           flat sorted summary with recomputed_pass_rate
                            and `missing_detail` for aggregate-only rows
  per_task_matrix.json      {tasks: [...60 ids...],
                             matrix: {task_id: {row_slug: {...}}}}

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-tasks     # reuse existing tasks.json
  python refresh.py --skip-matharena # reuse cached aime_2025_outputs parquet
  python refresh.py --skip-llmstats  # reuse cached llm-stats HTML
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / ".cache"

# --- Task universe --------------------------------------------------------- #
HF_TASK_DATASETS = {
    "2024_I":  "MathArena/aime_2024_I",
    "2024_II": "MathArena/aime_2024_II",
    # MathArena ships AIME 2025 as a single 30-row dataset (no I/II split
    # on HF). We slice by problem_idx: 1-15 -> I, 16-30 -> II.
    "2025":    "MathArena/aime_2025",
}

# --- MathArena per-instance outputs (AIME 2025 only) ----------------------- #
MATHARENA_OUTPUTS_DATASET = "MathArena/aime_2025_outputs"

# --- llm-stats aggregate leaderboards -------------------------------------- #
LLMSTATS_URLS = {
    "2024": "https://llm-stats.com/benchmarks/aime-2024",
    "2025": "https://llm-stats.com/benchmarks/aime-2025",
}

USER_AGENT = "aime2425-leaderboard-refresh/1.0"


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4, timeout: int = 300) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def fetch_text(url: str, **kw) -> str:
    return fetch(url, **kw).decode("utf-8", errors="replace")


def fetch_json(url: str) -> object:
    return json.loads(fetch_text(url))


def cached_fetch(url: str, cache_key: str, force: bool = False) -> bytes:
    """Cache large binary artifacts (parquet files) under .cache/."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / cache_key
    if path.exists() and not force:
        return path.read_bytes()
    data = fetch(url)
    path.write_bytes(data)
    return data


# --------------------------------------------------------------------------- #
# Task universe
# --------------------------------------------------------------------------- #
def _parquet_url(dataset: str) -> str:
    meta_url = f"https://huggingface.co/api/datasets/{dataset}/parquet/default/train"
    urls = fetch_json(meta_url)
    if not isinstance(urls, list) or not urls:
        raise RuntimeError(f"Unexpected parquet index shape for {dataset}: {urls!r}")
    return urls[0]


def _read_parquet(raw: bytes):
    import pyarrow.parquet as pq  # noqa: WPS433 — lazy import

    return pq.read_table(io.BytesIO(raw)).to_pandas()


def task_id_for(year: str, half: str, idx: int) -> str:
    return f"aime_{year}_{half}_{idx}"


def build_tasks() -> list[dict]:
    """60 canonical tasks across AIME 2024/2025, I and II halves."""
    tasks: list[dict] = []

    for half in ("I", "II"):
        url = _parquet_url(HF_TASK_DATASETS[f"2024_{half}"])
        df = _read_parquet(cached_fetch(url, f"aime_2024_{half}.parquet"))
        for row in df.to_dict(orient="records"):
            idx = int(row["problem_idx"])
            tasks.append(
                {
                    "task_id": task_id_for("2024", half, idx),
                    "year": 2024,
                    "half": half,
                    "problem_idx": idx,
                    "problem": row["problem"].strip(),
                    "gold_answer": int(row["answer"]),
                    "problem_type": None,
                    "source_dataset": HF_TASK_DATASETS[f"2024_{half}"],
                }
            )

    # MathArena AIME 2025 is merged I+II. problem_idx 1-15 -> I, 16-30 -> II.
    url = _parquet_url(HF_TASK_DATASETS["2025"])
    df = _read_parquet(cached_fetch(url, "aime_2025.parquet"))
    for row in df.to_dict(orient="records"):
        merged_idx = int(row["problem_idx"])
        half = "I" if merged_idx <= 15 else "II"
        local_idx = merged_idx if half == "I" else merged_idx - 15
        problem_type = row.get("problem_type")
        if problem_type is not None and hasattr(problem_type, "tolist"):
            problem_type = problem_type.tolist()
        tasks.append(
            {
                "task_id": task_id_for("2025", half, local_idx),
                "year": 2025,
                "half": half,
                "problem_idx": local_idx,
                "merged_idx": merged_idx,  # matches MathArena outputs problem_idx
                "problem": row["problem"].strip(),
                "gold_answer": int(row["answer"]),
                "problem_type": problem_type,
                "source_dataset": HF_TASK_DATASETS["2025"],
            }
        )

    tasks.sort(key=lambda t: (t["year"], t["half"], t["problem_idx"]))
    return tasks


# --------------------------------------------------------------------------- #
# MathArena per-instance outputs (AIME 2025)
# --------------------------------------------------------------------------- #
def slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")


def fetch_matharena_outputs() -> "pandas.DataFrame":  # noqa: F821
    url = _parquet_url(MATHARENA_OUTPUTS_DATASET)
    raw = cached_fetch(url, "aime_2025_outputs.parquet")
    df = _read_parquet(raw)
    needed = [
        "problem_idx",
        "model_name",
        "model_config",
        "idx_answer",
        "correct",
        "gold_answer",
        "parsed_answer",
        "input_tokens",
        "output_tokens",
        "cost",
    ]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise RuntimeError(f"MathArena outputs missing columns: {missing}")
    df = df[needed].copy()
    # problem_idx arrives as string; coerce.
    df["problem_idx"] = df["problem_idx"].astype(int)
    return df


def matharena_rows(df, all_tasks: list[dict]) -> dict[str, dict]:
    """Build per-row aggregates + per-task stats for MathArena AIME 2025 rows.

    Multiple samples per (model, problem) — we treat each sample as an
    independent trial and report n_trials / n_success / pass_rate per
    (task, model). The row's `tasks` array contains all 60 canonical
    tasks for shape parity with llmstats rows; AIME 2024 entries are
    zero-filled (MathArena has no 2024 outputs). `accuracy` averages
    only over tasks with ≥1 trial (i.e. the 30 AIME 2025 tasks for
    complete uploads), matching MathArena's reporting convention.
    """
    rows: dict[str, dict] = {}

    # Deterministic iteration by model_config.
    for model_config, mc_df in df.groupby("model_config"):
        model_name = mc_df["model_name"].iloc[0]
        slug = f"matharena__aime_2025__{slugify(model_config)}"

        per_task: list[dict] = []
        total_trials = 0
        total_successes = 0
        covered = 0

        for task in all_tasks:
            if task["year"] != 2025:
                per_task.append(
                    {
                        "task_name": task["task_id"],
                        "n_trials": 0,
                        "n_success": 0,
                        "pass_rate": 0.0,
                    }
                )
                continue
            sub = mc_df[mc_df["problem_idx"] == task["merged_idx"]]
            n_trials = int(len(sub))
            n_success = int(sub["correct"].sum()) if n_trials else 0
            if n_trials:
                covered += 1
                total_trials += n_trials
                total_successes += n_success
            per_task.append(
                {
                    "task_name": task["task_id"],
                    "n_trials": n_trials,
                    "n_success": n_success,
                    "pass_rate": (n_success / n_trials) if n_trials else 0.0,
                }
            )

        # Macro-average over tasks that have ≥1 trial. MathArena's own
        # convention is "run N times per problem, average the score" —
        # the denominator is problems attempted, not the full 30. Rows
        # with full coverage (all 30 problems, ~4 samples each) — the
        # common case — are unaffected. Partial-coverage rows (e.g.
        # uploads stopped early) report a meaningful score instead of
        # being artificially diluted to zero.
        covered_rates = [t["pass_rate"] for t in per_task if t["n_trials"] > 0]
        accuracy = sum(covered_rates) / len(covered_rates) if covered_rates else None
        # Micro-average: fraction of correct samples across all trials.
        micro_accuracy = (
            (total_successes / total_trials) if total_trials else None
        )

        total_input = int(mc_df["input_tokens"].sum())
        total_output = int(mc_df["output_tokens"].sum())
        total_cost = float(mc_df["cost"].sum())

        rows[slug] = {
            "slug": slug,
            "source": "matharena",
            "benchmark": "aime_2025",
            "model": model_name,
            "model_config": model_config,
            "organization": model_config.split("/")[0] if "/" in model_config else None,
            "accuracy": accuracy,
            "accuracy_micro": micro_accuracy,
            "num_tasks": 30,  # MathArena covers AIME 2025 only (30 of 60 tasks)
            "tasks_with_data": covered,
            "total_trials": total_trials,
            "total_successes": total_successes,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost": total_cost,
            "self_reported": False,  # MathArena runs the evals in-house
            "self_reported_source": None,
            "announcement_date": None,
            "is_open_source": None,
            "param_count": None,
            "source_dataset": MATHARENA_OUTPUTS_DATASET,
            "tasks": per_task,
        }
    return rows


# --------------------------------------------------------------------------- #
# llm-stats aggregate rows
# --------------------------------------------------------------------------- #
def _join_next_f_chunks(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[\d+,\"(.+?)\"\]\)', html, re.DOTALL)
    return bytes("".join(chunks), "utf-8").decode("unicode_escape")


def _extract_models_array(payload: str) -> list[dict]:
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


def llmstats_rows(year: str, all_tasks: list[dict], skip: bool = False) -> dict[str, dict]:
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"llmstats_aime_{year}.html"
    if skip and cache_path.exists():
        html = cache_path.read_text(encoding="utf-8")
    else:
        html = fetch_text(LLMSTATS_URLS[year])
        cache_path.write_text(html, encoding="utf-8")

    payload = _join_next_f_chunks(html)
    models = _extract_models_array(payload)
    print(f"  llm-stats aime-{year}: {len(models)} models")

    # Aggregate rows don't carry per-task data, so pre-populate a zeroed
    # per_task array so shape matches matharena rows.
    empty_tasks = [
        {"task_name": t["task_id"], "n_trials": 0, "n_success": 0, "pass_rate": 0.0}
        for t in all_tasks
    ]
    benchmark_year_tasks = [t for t in all_tasks if t["year"] == int(year)]

    out: dict[str, dict] = {}
    for m in models:
        name = m.get("model_name") or ""
        slug = f"llmstats__aime_{year}__{slugify(name)}"
        score = m.get("score")  # 0-1 fraction
        out[slug] = {
            "slug": slug,
            "source": "llmstats",
            "benchmark": f"aime_{year}",
            "model": name,
            "model_config": None,
            "organization": m.get("organization_name"),
            "accuracy": score,
            "accuracy_micro": None,
            "num_tasks": len(benchmark_year_tasks),
            "tasks_with_data": 0,
            "total_trials": None,
            "total_successes": None,
            "total_input_tokens": None,
            "total_output_tokens": None,
            "total_cost": None,
            "self_reported": bool(m.get("self_reported")),
            "self_reported_source": m.get("self_reported_source"),
            "announcement_date": m.get("announcement_date"),
            "is_open_source": m.get("is_open_source"),
            "param_count": m.get("param_count"),
            "rank": m.get("rank"),
            "verified": bool(m.get("verified")),
            "input_cost_per_million": m.get("input_cost_per_million"),
            "output_cost_per_million": m.get("output_cost_per_million"),
            "context_window": m.get("context_window"),
            "source_url": LLMSTATS_URLS[year],
            "tasks": list(empty_tasks),  # shape parity; always zeroed
        }
    return out


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_tasks(tasks: list[dict]) -> None:
    (HERE / "tasks.json").write_text(
        json.dumps(
            {
                "benchmark": "aime2425",
                "num_tasks": len(tasks),
                "note": (
                    "60 canonical problems: AIME 2024 I (15) + II (15) + "
                    "AIME 2025 I (15) + II (15). Task IDs follow the "
                    "pattern `aime_<year>_<I|II>_<1..15>`. For AIME 2025 we "
                    "keep a `merged_idx` (1..30) field to match MathArena's "
                    "merged outputs dataset, where problem_idx 1-15 are "
                    "AIME I and 16-30 are AIME II."
                ),
                "schema": {
                    "task_id": "Canonical ID: aime_<year>_<half>_<idx>",
                    "year": "2024 or 2025",
                    "half": "I or II",
                    "problem_idx": "1-indexed position within the half (1..15)",
                    "merged_idx": "Only for AIME 2025 — 1..30 idx in MathArena merged dataset",
                    "problem": "LaTeX problem statement",
                    "gold_answer": "Integer in [0, 999]",
                    "problem_type": "Topic tag when provided by upstream (AIME 2025 only)",
                    "source_dataset": "Upstream MathArena HF dataset",
                },
                "tasks": tasks,
            },
            indent=2,
        )
    )


def write_rows(rows: dict[str, dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for old in rows_dir.glob("*.json"):
        old.unlink()
    for slug, r in rows.items():
        (rows_dir / f"{slug}.json").write_text(json.dumps(r, indent=2))


def write_leaderboard(rows: dict[str, dict], num_tasks: int) -> None:
    entries = list(rows.values())

    def sort_key(r: dict) -> tuple:
        # Order: year ascending, accuracy descending (so highest first per year).
        year = r["benchmark"].rsplit("_", 1)[-1]
        return (year, -(r["accuracy"] or 0.0), r["source"])

    entries.sort(key=sort_key)
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "benchmark": "aime2425",
                "scope": "AIME 2024 I+II + AIME 2025 I+II (60 problems)",
                "num_entries": len(entries),
                "num_tasks": num_tasks,
                "sources": {
                    "matharena": MATHARENA_OUTPUTS_DATASET,
                    "llmstats_2024": LLMSTATS_URLS["2024"],
                    "llmstats_2025": LLMSTATS_URLS["2025"],
                },
                "schema": {
                    "slug": "Row key (unique across sources)",
                    "source": "matharena | llmstats",
                    "benchmark": "aime_2024 | aime_2025",
                    "model": "Display model name",
                    "model_config": "MathArena model config path (matharena rows only)",
                    "organization": "Provider/org name",
                    "accuracy": "0-1 fraction on the row's benchmark year. For matharena rows: macro-average of per-task pass rates over tasks with ≥1 trial (matches MathArena's 'run 4x per problem, average' convention — sparse-coverage rows are not diluted to zero). For llm-stats rows: as reported by the provider.",
                    "accuracy_micro": "Micro-average (total_successes / total_trials). matharena rows only. For rows with full 30/30 coverage this matches `accuracy` exactly.",
                    "num_tasks": "Task count for that benchmark year (30)",
                    "tasks_with_data": "Tasks the row actually reports (matharena only)",
                    "total_trials": "Sum of trials across tasks (matharena only; ~4 per task per model)",
                    "total_successes": "Sum of correct samples (matharena only)",
                    "total_input_tokens": "MathArena reported input token usage",
                    "total_output_tokens": "MathArena reported output token usage",
                    "total_cost": "MathArena reported cost (USD)",
                    "self_reported": "True for llm-stats rows (scraped from provider blogs)",
                    "self_reported_source": "URL of the announcement (llm-stats only)",
                    "announcement_date": "YYYY-MM-DD (llm-stats only)",
                    "is_open_source": "Bool (llm-stats only)",
                    "param_count": "Total parameter count if disclosed (llm-stats only)",
                },
                "entries": entries,
            },
            indent=2,
        )
    )


def write_rows_index(rows: dict[str, dict]) -> None:
    has_detail: list[dict] = []
    missing: list[dict] = []
    for slug, r in rows.items():
        recomputed = None
        if r["source"] == "matharena" and r["total_trials"]:
            recomputed = r["total_successes"] / r["total_trials"]
        summary = {
            "slug": slug,
            "source": r["source"],
            "benchmark": r["benchmark"],
            "model": r["model"],
            "organization": r["organization"],
            "accuracy": r["accuracy"],
            "num_tasks": r["num_tasks"],
            "tasks_with_data": r.get("tasks_with_data", 0),
            "total_trials": r["total_trials"],
            "total_successes": r["total_successes"],
            "recomputed_pass_rate": recomputed,
            "self_reported": r.get("self_reported", False),
            "announcement_date": r.get("announcement_date"),
        }
        if r["source"] == "matharena" and r["tasks_with_data"]:
            has_detail.append(summary)
        else:
            missing.append(summary)

    # Sort full-coverage rows ahead of partial ones so sparse uploads
    # (e.g. MathArena test runs with only 1 problem attempted) don't
    # appear near the top despite correct-on-what-they-tried scores.
    def _detail_key(s: dict) -> tuple:
        covered = s.get("tasks_with_data") or 0
        full = covered >= (s.get("num_tasks") or 0) > 0
        return (not full, -(s.get("accuracy") or 0))

    has_detail.sort(key=_detail_key)
    missing.sort(key=lambda s: (s["benchmark"], -(s["accuracy"] or 0)))

    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": len(has_detail),
                "num_missing_detail": len(missing),
                "note": (
                    "AIME 2024 has no per-instance results published anywhere "
                    "(MathArena ships only problem datasets for 2024, no "
                    "_outputs dataset). AIME 2025 per-instance data comes "
                    "from MathArena/aime_2025_outputs (4 samples per "
                    "(model, problem)). llm-stats rows are self-reported "
                    "aggregates scraped from provider blogs — same model may "
                    "appear under both `matharena` and `llmstats` sources "
                    "for 2025 with different numbers."
                ),
                "rows": has_detail,
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_per_task_matrix(rows: dict[str, dict], tasks: list[dict]) -> None:
    matrix: dict[str, dict] = defaultdict(dict)
    for slug, r in rows.items():
        if r["source"] != "matharena":
            continue
        for t in r["tasks"]:
            if t["n_trials"] == 0:
                continue
            matrix[t["task_name"]][slug] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
            }
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "Matrix is populated only for tasks with per-instance "
                    "results. AIME 2024 task IDs are present in `tasks` but "
                    "carry no per-model cells (no upstream source publishes "
                    "them). AIME 2025 cells come from MathArena "
                    "aime_2025_outputs with n_trials == # samples (≤4)."
                ),
                "tasks": [t["task_id"] for t in tasks],
                "matrix": dict(matrix),
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
    ap.add_argument("--skip-tasks", action="store_true", help="Reuse existing tasks.json")
    ap.add_argument("--skip-matharena", action="store_true", help="Reuse cached MathArena parquet")
    ap.add_argument("--skip-llmstats", action="store_true", help="Reuse cached llm-stats HTML")
    args = ap.parse_args()

    print("=" * 72)
    print("AIME 2024 + AIME 2025 leaderboard refresh (60 problems)")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    tasks_path = HERE / "tasks.json"
    if args.skip_tasks and tasks_path.exists():
        print("[1/4] skip tasks — reusing tasks.json")
        tasks = json.loads(tasks_path.read_text())["tasks"]
    else:
        print("[1/4] fetching task universe from MathArena HF datasets")
        tasks = build_tasks()
        write_tasks(tasks)
        print(f"  -> wrote tasks.json ({len(tasks)} tasks)")

    print("[2/4] fetching MathArena/aime_2025_outputs parquet (per-instance)")
    df = fetch_matharena_outputs()
    print(f"  {len(df)} rows, {df.model_config.nunique()} models, "
          f"{df.problem_idx.nunique()} problems")
    ma_rows = matharena_rows(df, tasks)
    print(f"  -> {len(ma_rows)} matharena rows for AIME 2025")

    print("[3/4] scraping llm-stats AIME 2024 and 2025 leaderboards")
    ls_2024 = llmstats_rows("2024", tasks, skip=args.skip_llmstats)
    ls_2025 = llmstats_rows("2025", tasks, skip=args.skip_llmstats)

    all_rows: dict[str, dict] = {}
    all_rows.update(ma_rows)
    all_rows.update(ls_2024)
    all_rows.update(ls_2025)

    print("[4/4] writing leaderboard.json, rows/, rows_index.json, per_task_matrix.json")
    write_leaderboard(all_rows, len(tasks))
    write_rows(all_rows)
    write_rows_index(all_rows)
    write_per_task_matrix(all_rows, tasks)

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "tasks.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    rows_dir = HERE / "rows"
    if rows_dir.exists():
        n = len(list(rows_dir.glob("*.json")))
        print(f"  rows/  ({n} files)")
    n_2025 = sum(1 for t in tasks if t["year"] == 2025)
    print(f"  tasks covered: {len(tasks)} ({n_2025} with per-instance data)")


if __name__ == "__main__":
    main()
