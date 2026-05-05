#!/usr/bin/env python3
"""Refresh the GPQA Diamond leaderboard snapshot.

Scope
-----
GPQA Diamond: the 198-question subset of GPQA (graduate-level physics /
chemistry / biology Q&A, Rein et al. 2024, arXiv:2311.12022) that
three expert validators agreed on.

Sources used end-to-end
-----------------------
1. https://artificialanalysis.ai/evaluations/gpqa-diamond
   Next.js SSR page. Two arrays live inside `self.__next_f.push`
   chunks:
     - `"models":[{id, slug, name, shortName, isReasoning, deprecated,
                   creator: {id, name, color, logo}}, ...]`
       — metadata catalogue (462 rows).
     - `"defaultData":[{id, gpqa, lab_claimed_gpqa,
                        intelligence_index, knowledge_cutoff_date,
                        license_name, is_open_weights, ...}, ...]`
       — the actual eval numbers. `gpqa` is AA's in-house measured
       GPQA Diamond score (0-1), `lab_claimed_gpqa` is the
       provider-reported number (often null).
   We join the two by `id` and keep the AA-measured score as the
   headline accuracy — it's the one number that's been run under a
   single, consistent harness across all 462 models.

2. https://huggingface.co/datasets/hendrydong/gpqa_diamond
   Ungated mirror of the 198 Diamond questions (columns: `problem`,
   `solution`, `domain`). The canonical `Idavidrein/gpqa` dataset is
   gated behind a contact-sharing agreement and its `Record ID` is not
   surfaced in ungated mirrors, so we derive a stable `task_id` from
   sha256(problem)[:12].

No per-instance publications
----------------------------
Unlike SWE-bench Verified, GPQA Diamond has no canonical per-model /
per-question results dump. HELM runs GPQA but only on the 448-question
`gpqa_main` subset, with instance text encrypted to resist
contamination. Open LLM Leaderboard v2 dumps per-sample GPQA Diamond
outputs but the `details_*` datasets are gated. Epoch AI publishes
Inspect logs with `Record ID` but access is CAPTCHA-gated. We mirror
the HLE pattern: every leaderboard row lands under `missing_detail`,
and `per_task_matrix.json` is populated with the 198 task IDs but
empty cells (shape placeholder) so downstream tooling treats GPQA
Diamond uniformly.

Outputs (all under this directory):
  leaderboard.json         # aggregate rows scraped from AA
  tasks.json               # 198 canonical Diamond questions + stable IDs
  rows/<slug>.json         # per-row metadata; `tasks: []` (no per-instance data)
  rows_index.json          # one-line summary sorted by accuracy; all under `missing_detail`
  per_task_matrix.json     # {tasks: [...198 ids...], matrix: {id: {}}}

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse cached AA HTML
  python refresh.py --skip-tasks     # reuse cached HF parquet
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / ".cache"

AA_URL = "https://artificialanalysis.ai/evaluations/gpqa-diamond"
HF_TASK_DATASET = "hendrydong/gpqa_diamond"
HF_TASK_SPLIT = "test"

USER_AGENT = "gpqa-diamond-leaderboard-refresh/1.0"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4, timeout: int = 180) -> bytes:
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
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / cache_key
    if path.exists() and not force:
        return path.read_bytes()
    data = fetch(url)
    path.write_bytes(data)
    return data


# --------------------------------------------------------------------------- #
# Parsing helpers for Next.js self.__next_f.push chunks
# --------------------------------------------------------------------------- #
def _join_next_f_chunks(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[\d+,\"(.+?)\"\]\)', html, re.DOTALL)
    return bytes("".join(chunks), "utf-8").decode("unicode_escape")


def _extract_array(payload: str, anchor: str) -> list[dict]:
    """Pull a JSON array out of the payload at the anchor string
    (e.g. `"models":[{`). Balances brackets while honoring strings.
    """
    idx = payload.find(anchor)
    if idx == -1:
        raise RuntimeError(f"Could not locate {anchor!r} in AA payload")
    # Anchor looks like `"models":[{` — skip past `"models":` to land on `[`.
    start = idx + anchor.index("[")
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


# --------------------------------------------------------------------------- #
# Step 1: scrape Artificial Analysis
# --------------------------------------------------------------------------- #
def scrape_aa(skip_scrape: bool) -> tuple[list[dict], list[dict]]:
    """Return (models_catalogue, default_data) arrays.

    `models_catalogue` carries display metadata (slug, name, creator).
    `default_data` carries the scores (`gpqa`, `lab_claimed_gpqa`, etc).
    Join by `id`.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / "aa_gpqa_diamond.html"
    if skip_scrape and cache.exists():
        html = cache.read_text(encoding="utf-8")
    else:
        html = fetch_text(AA_URL)
        cache.write_text(html, encoding="utf-8")

    payload = _join_next_f_chunks(html)
    models = _extract_array(payload, '"models":[{')
    data = _extract_array(payload, '"defaultData":[{')
    print(f"  AA models catalogue: {len(models)}  |  defaultData: {len(data)}")
    return models, data


# --------------------------------------------------------------------------- #
# Step 2: 198 canonical Diamond questions (HF)
# --------------------------------------------------------------------------- #
def _parquet_url(dataset: str, split: str) -> str:
    meta = fetch_json(
        f"https://huggingface.co/api/datasets/{dataset}/parquet/default/{split}"
    )
    if not isinstance(meta, list) or not meta:
        raise RuntimeError(f"Unexpected parquet index shape for {dataset}: {meta!r}")
    return meta[0]


def _read_parquet(raw: bytes):
    import pyarrow.parquet as pq  # lazy import

    return pq.read_table(io.BytesIO(raw)).to_pandas()


def build_tasks(skip_tasks: bool) -> list[dict]:
    """Fetch the 198 GPQA Diamond questions and assign stable task IDs.

    `Idavidrein/gpqa` is gated, so we use `hendrydong/gpqa_diamond` as
    an ungated mirror. It carries `problem`, `solution`, `domain` but
    no `Record ID`, so the stable ID is sha256(problem)[:12].
    """
    url = _parquet_url(HF_TASK_DATASET, HF_TASK_SPLIT)
    cache_key = "hendrydong_gpqa_diamond.parquet"
    if skip_tasks and (CACHE_DIR / cache_key).exists():
        raw = (CACHE_DIR / cache_key).read_bytes()
    else:
        raw = cached_fetch(url, cache_key, force=not skip_tasks)
    df = _read_parquet(raw)

    needed = {"problem", "solution", "domain"}
    missing = needed - set(df.columns)
    if missing:
        raise RuntimeError(f"HF dataset missing columns: {missing}")

    tasks: list[dict] = []
    for idx, row in enumerate(df.to_dict(orient="records")):
        problem = (row["problem"] or "").strip()
        qid = hashlib.sha256(problem.encode("utf-8")).hexdigest()[:12]
        tasks.append(
            {
                "task_id": f"gpqa_diamond_{qid}",
                "question_hash": qid,
                "domain": row.get("domain"),
                "problem_length": len(problem),
                "hf_row_idx": idx,  # positional index in hendrydong/gpqa_diamond
                # Intentionally NOT persisting the full problem text or gold
                # answer — the upstream dataset is password-protected
                # specifically to discourage contamination. Consumers who
                # need problem text / answers can pull the HF dataset
                # directly and join on `hf_row_idx` or `question_hash`.
            }
        )
    return tasks


# --------------------------------------------------------------------------- #
# Step 3: build per-row dicts
# --------------------------------------------------------------------------- #
def slugify(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", s or "").strip("_")
    return out or "row"


def build_rows(
    models: list[dict], data: list[dict], tasks: list[dict]
) -> dict[str, dict]:
    """Join AA catalogue + defaultData into per-model row dicts."""
    cat = {m["id"]: m for m in models}

    # Pre-zeroed per-task array for shape parity.
    empty_tasks = [
        {"task_name": t["task_id"], "n_trials": 0, "n_success": 0, "pass_rate": 0.0}
        for t in tasks
    ]

    rows: dict[str, dict] = {}
    for entry in data:
        mid = entry.get("id")
        score = entry.get("gpqa")
        if mid is None or score is None:
            continue

        meta = cat.get(mid) or {}
        slug_source = meta.get("slug") or entry.get("model_family_slug") or mid
        slug = slugify(slug_source)
        # Disambiguate slug collisions (shouldn't happen, but be safe).
        if slug in rows:
            slug = f"{slug}__{mid[:8]}"

        creator = meta.get("creator") or {}
        rows[slug] = {
            "slug": slug,
            "source": "artificialanalysis",
            "benchmark": "gpqa_diamond",
            "id": mid,
            "aa_slug": meta.get("slug"),
            "model": meta.get("name") or meta.get("shortName") or entry.get("model_family_slug"),
            "short_name": meta.get("shortName"),
            "creator": creator.get("name"),
            "creator_id": creator.get("id"),
            "deprecated": bool(meta.get("deprecated") or entry.get("deprecated")),
            "deprecated_to": entry.get("deprecated_to"),
            "is_reasoning": bool(meta.get("isReasoning")),
            "is_open_weights": bool(entry.get("is_open_weights")),
            "license_name": entry.get("license_name"),
            "license_url": entry.get("license_url"),
            "knowledge_cutoff_date": entry.get("knowledge_cutoff_date"),
            # Headline score — AA's in-house measurement, 0-1.
            "accuracy": score,
            # Vendor-reported number (often None). Keep alongside for
            # consumers that want to compare self-reported to measured.
            "lab_claimed_accuracy": entry.get("lab_claimed_gpqa"),
            # Misc cross-benchmark context AA surfaces on the same row.
            "intelligence_index": entry.get("intelligence_index"),
            "estimated_intelligence_index": entry.get("estimated_intelligence_index"),
            "context_window_tokens": entry.get("context_window_tokens"),
            "active_params_billions": entry.get("inference_parameters_active_billions"),
            "frontier_model": bool(entry.get("frontier_model")),
            "commercial_allowed": entry.get("commercial_allowed"),
            "source_url": AA_URL,
            # Per-instance data not published (see module docstring).
            "num_tasks": len(tasks),
            "total_trials": None,
            "total_successes": None,
            "tasks": list(empty_tasks),
        }
    return rows


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_tasks(tasks: list[dict]) -> None:
    (HERE / "tasks.json").write_text(
        json.dumps(
            {
                "benchmark": "gpqa-diamond",
                "source_dataset": f"hf://datasets/{HF_TASK_DATASET}:{HF_TASK_SPLIT}",
                "num_tasks": len(tasks),
                "note": (
                    "198 Diamond questions mirrored via hendrydong/gpqa_diamond "
                    "(the canonical Idavidrein/gpqa dataset is gated). Stable "
                    "task IDs are sha256(problem)[:12] — the HF mirror does "
                    "not preserve the canonical Record ID. Question text is "
                    "intentionally not stored here; consumers needing the text "
                    "should pull the HF dataset directly."
                ),
                "schema": {
                    "task_id": "Stable ID: gpqa_diamond_<sha256(problem)[:12]>",
                    "question_hash": "sha256(problem)[:12] (without the prefix)",
                    "domain": "High-level domain (Physics / Chemistry / Biology)",
                    "problem_length": "Character count of the problem statement",
                    "hf_row_idx": "Positional index in the HF dataset (0-197)",
                },
                "tasks": tasks,
            },
            indent=2,
        )
    )


def write_rows(rows: dict[str, dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    # Clear stale rows so rename-churn in the leaderboard doesn't leave
    # orphaned files behind (same as the HLE refresh).
    for old in rows_dir.glob("*.json"):
        old.unlink()
    for slug, r in rows.items():
        (rows_dir / f"{slug}.json").write_text(json.dumps(r, indent=2))


def write_leaderboard(rows: dict[str, dict], num_tasks: int) -> None:
    # Leaderboard overview omits the per-task array — that lives in
    # rows/<slug>.json. Matches the SWE-bench Verified layout.
    entries = sorted(
        ({k: v for k, v in r.items() if k != "tasks"} for r in rows.values()),
        key=lambda r: (-(r["accuracy"] or 0.0), r["slug"]),
    )
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "benchmark": "gpqa-diamond",
                "scope": "GPQA Diamond — 198 expert-validated questions",
                "source_url": AA_URL,
                "num_entries": len(entries),
                "num_tasks": num_tasks,
                "schema": {
                    "slug": "Row key (unique; filesystem-safe form of AA slug)",
                    "source": "artificialanalysis",
                    "benchmark": "gpqa_diamond",
                    "id": "Artificial Analysis model UUID",
                    "aa_slug": "AA model slug (may differ from our filesystem slug)",
                    "model": "Display model name",
                    "short_name": "Shortened display name (AA)",
                    "creator": "Lab / organization name",
                    "deprecated": "AA marks the row as deprecated",
                    "is_reasoning": "Reasoning mode enabled in AA's run",
                    "is_open_weights": "Open-weights model",
                    "accuracy": "0-1. AA's measured GPQA Diamond accuracy (same harness across all rows).",
                    "lab_claimed_accuracy": "Vendor-reported GPQA Diamond score (often null).",
                    "intelligence_index": "AA composite intelligence index (~reasoning aggregate)",
                    "estimated_intelligence_index": "Estimated version when the measured index is missing",
                    "context_window_tokens": "Disclosed context window",
                    "active_params_billions": "Active-parameter count (MoE active B; dense total B) where disclosed",
                    "frontier_model": "AA flags the row as a frontier-tier model",
                    "license_name": "License string (open-weights rows)",
                    "knowledge_cutoff_date": "YYYY-MM-DD (provider-reported)",
                },
                "entries": entries,
            },
            indent=2,
        )
    )


def write_rows_index(rows: dict[str, dict]) -> None:
    """All rows go under `missing_detail` (HLE pattern) — no per-instance data."""
    missing: list[dict] = []
    for slug, r in rows.items():
        acc = r.get("accuracy")
        missing.append(
            {
                "slug": slug,
                "model": r["model"],
                "creator": r["creator"],
                "accuracy": acc,
                "accuracy_pct": (acc * 100.0) if acc is not None else None,
                "lab_claimed_accuracy": r.get("lab_claimed_accuracy"),
                "is_reasoning": r.get("is_reasoning"),
                "is_open_weights": r.get("is_open_weights"),
                "deprecated": r.get("deprecated"),
                "frontier_model": r.get("frontier_model"),
                "num_tasks": r.get("num_tasks"),
                "total_trials": None,
                "recomputed_pass_rate": None,
            }
        )
    missing.sort(key=lambda r: -(r["accuracy"] or 0.0))

    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": 0,
                "num_missing_detail": len(missing),
                "note": (
                    "GPQA Diamond publishes aggregate scores only. The 198 "
                    "questions sit behind a contact-sharing agreement and no "
                    "public source dumps per-model, per-question predictions "
                    "for frontier models. HELM runs GPQA but on `gpqa_main` "
                    "(448 questions, encrypted text); Open LLM Leaderboard v2 "
                    "has per-sample Diamond outputs but is gated. Every row "
                    "lives in `missing_detail`; `per_task_matrix.json` "
                    "carries the 198 task IDs with empty cells for shape "
                    "parity with other leaderboards."
                ),
                "rows": [],
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_matrix_placeholder(tasks: list[dict]) -> None:
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "No per-model per-question results are published for "
                    "GPQA Diamond. Task IDs are listed for shape parity; "
                    "`matrix` cells are empty. If a consumer later ingests "
                    "per-instance data (e.g., Open LLM Leaderboard details, "
                    "Epoch AI Inspect logs), it can populate cells by "
                    "looking up tasks via sha256(problem)[:12]."
                ),
                "tasks": [t["task_id"] for t in tasks],
                "matrix": {t["task_id"]: {} for t in tasks},
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
    ap.add_argument("--skip-scrape", action="store_true", help="Reuse cached AA HTML")
    ap.add_argument("--skip-tasks", action="store_true", help="Reuse cached HF parquet")
    args = ap.parse_args()

    print("=" * 72)
    print("GPQA Diamond leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    print("[1/4] scraping Artificial Analysis")
    models, data = scrape_aa(args.skip_scrape)

    print("[2/4] building task universe from HuggingFace")
    tasks = build_tasks(args.skip_tasks)
    print(f"  tasks: {len(tasks)}")
    write_tasks(tasks)

    print("[3/4] building per-row dicts")
    rows = build_rows(models, data, tasks)
    print(f"  rows: {len(rows)}")
    write_rows(rows)

    print("[4/4] writing leaderboard.json + rows_index.json + per_task_matrix.json")
    write_leaderboard(rows, num_tasks=len(tasks))
    write_rows_index(rows)
    write_matrix_placeholder(tasks)

    print()
    print("done. outputs:")
    for f in (
        "leaderboard.json",
        "tasks.json",
        "rows_index.json",
        "per_task_matrix.json",
    ):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list((HERE / "rows").glob("*.json")))
    print(f"  rows/  ({n} files)")


if __name__ == "__main__":
    main()
