#!/usr/bin/env python3
"""Refresh the MMMU-Pro leaderboard snapshot.

MMMU-Pro (arXiv:2409.02813) is a multimodal multi-discipline benchmark —
1,730 college-level questions across 30 fine-grained subjects in 6
domains. It comes in three test configs:

  * `standard (4 options)`   — 4-way MCQ (filtered to remove text-only
                               solvable questions vs. MMMU)
  * `standard (10 options)`  — same questions expanded to 10 options
                               (harder; reported as the `original` column
                               on the leaderboard)
  * `vision`                 — question + choices rendered into a single
                               screenshot; model must OCR

The headline leaderboard column (`overall`) is the average of `vision` and
`original` (standard-10-options, CoT). See evaluate.py in the MMMU repo.

Sources used end-to-end:

  1. https://raw.githubusercontent.com/MMMU-Benchmark/MMMU-Benchmark.github.io/main/leaderboard_data.json
     Canonical machine-readable leaderboard. 210 total entries across
     MMMU-val / MMMU-test / MMMU-Pro; we keep the 73 with a `pro` block.

  2. https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/main/mmmu-pro/output/*.jsonl
     Per-question predictions from the benchmark authors. **Published
     for GPT-4o only**, as 4 files:
       gpt-4o_standard(10 options)_direct.jsonl   # acc 40.1%
       gpt-4o_standard(10 options)_cot.jsonl      # acc 55.0% (= leaderboard `original`)
       gpt-4o_vision_direct.jsonl                 # acc 42.4%
       gpt-4o_vision_cot.jsonl                    # acc 50.1% (= leaderboard `vision`)
     Each file = 1,730 rows with `{id, answer, pred_indexs, if_right, subject, topic_difficulty, img_type, ...}`.

  3. https://huggingface.co/datasets/VLMEval/OpenVLMRecords (mmeval/ tree)
     Official VLMEvalKit record dump that backs the OpenVLM Leaderboard.
     ~42 MMMU_Pro xlsx files covering 7 open-weight models × {10c, V}
     variants (plus COT variants which we skip — they store raw
     reasoning traces that need a judge-model letter extraction).
     Non-COT xlsx files have `prediction` as a single letter A–J that
     we compare to `answer` for deterministic exact-match scoring.
     Requires `openpyxl` to parse.

No other source publishes per-instance MMMU-Pro predictions we could
find. Every non-instrumented leaderboard row (56 of 73) lands in
`rows_index.json` → `missing_detail`.

Outputs (all under this directory):
  leaderboard.json            # all 73 rows with pro scores + metadata
  rows/<slug>.json            # per-row metadata; GPT-4o has per-task stats
  rows_index.json             # one-line summary, sorted by overall
  per_task_matrix.json        # 4 GPT-4o run-columns × 1,730 tasks

Usage:
  python refresh.py                # full refresh
  python refresh.py --skip-scrape  # reuse leaderboard.json
  python refresh.py --skip-predict # reuse cached GPT-4o JSONLs
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = (
    "https://raw.githubusercontent.com/MMMU-Benchmark/"
    "MMMU-Benchmark.github.io/main/leaderboard_data.json"
)
PROJECT_PAGE = "https://mmmu-benchmark.github.io/"

PRED_BASE = (
    "https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/main/mmmu-pro/output"
)
# (config, mode, filename) — filename must be URL-encoded when fetching.
GPT4O_PREDICTION_FILES: list[tuple[str, str, str]] = [
    ("standard (10 options)", "cot", "gpt-4o_standard(10 options)_cot.jsonl"),
    ("standard (10 options)", "direct", "gpt-4o_standard(10 options)_direct.jsonl"),
    ("vision", "cot", "gpt-4o_vision_cot.jsonl"),
    ("vision", "direct", "gpt-4o_vision_direct.jsonl"),
]

# VLMEvalKit record dump — 7 models × {standard-10-options, vision} xlsx
# files covering the full 1,730-question test set. We skip the `_COT.xlsx`
# variants (prediction column stores CoT reasoning traces that VLMEvalKit
# scores with a judge LLM; we don't replicate that). We also skip the
# `_exact_matching_result.xlsx` files — they carry redundant `hit`/`log`
# columns that duplicate what we can recompute from the main dumps.
VLMEVAL_DATASET = "VLMEval/OpenVLMRecords"
VLMEVAL_BASE = f"https://huggingface.co/datasets/{VLMEVAL_DATASET}/resolve/main/mmeval"
# (display_model, config, subdir, filename)
VLMEVAL_FILES: list[tuple[str, str, str, str]] = [
    ("InternVL2-8B",               "standard (10 options)", "InternVL2-8B",              "InternVL2-8B_MMMU_Pro_10c.xlsx"),
    ("InternVL2-8B",               "vision",                "InternVL2-8B",              "InternVL2-8B_MMMU_Pro_V.xlsx"),
    ("InternVL2_5-8B",             "standard (10 options)", "InternVL2_5-8B",            "InternVL2_5-8B_MMMU_Pro_10c.xlsx"),
    ("InternVL2_5-8B",             "vision",                "InternVL2_5-8B",            "InternVL2_5-8B_MMMU_Pro_V.xlsx"),
    ("Qwen2-VL-2B-Instruct",       "standard (10 options)", "Qwen2-VL-2B-Instruct",      "Qwen2-VL-2B-Instruct_MMMU_Pro_10c.xlsx"),
    ("Qwen2-VL-2B-Instruct",       "vision",                "Qwen2-VL-2B-Instruct",      "Qwen2-VL-2B-Instruct_MMMU_Pro_V.xlsx"),
    ("Qwen2-VL-7B-Instruct",       "standard (10 options)", "Qwen2-VL-7B-Instruct",      "Qwen2-VL-7B-Instruct_MMMU_Pro_10c.xlsx"),
    ("Qwen2.5-VL-3B",              "standard (10 options)", "Qwen2.5-VL-3B",             "Qwen2.5-VL-3B_MMMU_Pro_10c.xlsx"),
    ("Qwen2.5-VL-3B",              "vision",                "Qwen2.5-VL-3B",             "Qwen2.5-VL-3B_MMMU_Pro_V.xlsx"),
    ("Qwen2.5-VL-7B",              "standard (10 options)", "Qwen2.5-VL-7B",             "Qwen2.5-VL-7B_MMMU_Pro_10c.xlsx"),
    ("Qwen2.5-VL-7B",              "vision",                "Qwen2.5-VL-7B",             "Qwen2.5-VL-7B_MMMU_Pro_V.xlsx"),
    ("llava_onevision_qwen2_7b_si", "standard (10 options)", "llava_onevision_qwen2_7b_si", "llava_onevision_qwen2_7b_si_MMMU_Pro_10c.xlsx"),
]

# Fine subject -> 6-domain mapping, copied from mmmu-pro/evaluate.py
# (DOMAIN_CAT2SUB_CAT). Kept in sync manually — this taxonomy is stable
# and hasn't changed since MMMU launched in Jan 2024.
DOMAIN_CAT2SUB_CAT = {
    "Art and Design": ["Art", "Art_Theory", "Design", "Music"],
    "Business": ["Accounting", "Economics", "Finance", "Manage", "Marketing"],
    "Science": ["Biology", "Chemistry", "Geography", "Math", "Physics"],
    "Health and Medicine": [
        "Basic_Medical_Science",
        "Clinical_Medicine",
        "Diagnostics_and_Laboratory_Medicine",
        "Pharmacy",
        "Public_Health",
    ],
    "Humanities and Social Science": [
        "History",
        "Literature",
        "Sociology",
        "Psychology",
    ],
    "Tech and Engineering": [
        "Agriculture",
        "Architecture_and_Engineering",
        "Computer_Science",
        "Electronics",
        "Energy_and_Power",
        "Materials",
        "Mechanical_Engineering",
    ],
}
SUB_CAT2DOMAIN = {
    sub: dom for dom, subs in DOMAIN_CAT2SUB_CAT.items() for sub in subs
}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "mmmu-pro-leaderboard-refresh/0.1"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def fetch_jsonl(url: str) -> list[dict]:
    body = fetch(url).decode("utf-8", errors="replace")
    return [json.loads(l) for l in body.splitlines() if l.strip()]


# --------------------------------------------------------------------------- #
# Leaderboard
# --------------------------------------------------------------------------- #
def _as_float(v: object) -> float | None:
    if v in (None, "-", ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def scrape_leaderboard() -> list[dict]:
    """Fetch leaderboard_data.json and keep rows with a `pro` block."""
    raw = json.loads(fetch(LEADERBOARD_URL).decode("utf-8"))
    data = raw.get("leaderboardData", raw)
    rows: list[dict] = []
    for e in data:
        pro = e.get("pro") or {}
        if not pro:
            continue
        info = e.get("info") or {}
        validation = e.get("validation") or {}
        test = e.get("test") or {}
        rows.append(
            {
                "name": info.get("name"),
                "size": info.get("size"),
                "date": info.get("date"),
                "type": info.get("type"),  # proprietary | open_source | human_expert | random_frequent
                "link": info.get("link"),
                # MMMU-Pro headline. `original` column = standard(10 options) CoT;
                # `vision` column = vision CoT; `overall` = their average.
                "pro_overall": _as_float(pro.get("overall")),
                "pro_vision": _as_float(pro.get("vision")),
                "pro_standard": _as_float(pro.get("original")),
                "pro_source": pro.get("source"),  # e.g. "author" for self-reported
                # Secondary: MMMU-val + MMMU-test, kept so consumers don't
                # have to rehydrate leaderboard_data.json separately.
                "mmmu_val_overall": _as_float(validation.get("overall")),
                "mmmu_val_by_domain": {
                    "art_design": _as_float(validation.get("artDesign")),
                    "business": _as_float(validation.get("business")),
                    "science": _as_float(validation.get("science")),
                    "health_medicine": _as_float(validation.get("healthMedicine")),
                    "humanities_social_sci": _as_float(
                        validation.get("humanSocialSci")
                    ),
                    "tech_engineering": _as_float(validation.get("techEng")),
                },
                "mmmu_test_overall": _as_float(test.get("overall")),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# GPT-4o prediction fetch + per-task aggregation
# --------------------------------------------------------------------------- #
def fetch_gpt4o_predictions() -> dict[tuple[str, str], list[dict]]:
    """Return {(config, mode): [rows]} for the 4 published GPT-4o dumps.

    Cached locally under predictions/ so re-runs don't re-download ~10 MB.
    """
    cache_dir = HERE / "predictions"
    cache_dir.mkdir(exist_ok=True)
    out: dict[tuple[str, str], list[dict]] = {}
    for config, mode, fname in GPT4O_PREDICTION_FILES:
        cache = cache_dir / fname
        if cache.exists():
            text = cache.read_text(encoding="utf-8")
            rows = [json.loads(l) for l in text.splitlines() if l.strip()]
        else:
            url = f"{PRED_BASE}/{urllib.parse.quote(fname, safe='()._-')}"
            print(f"  fetching {fname}")
            body = fetch(url).decode("utf-8", errors="replace")
            cache.write_text(body, encoding="utf-8")
            rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        out[(config, mode)] = rows
    return out


def _config_short(config: str) -> str:
    return "standard10" if "10" in config else "standard4" if "4" in config else "vision"


def _run_slug(config: str, mode: str) -> str:
    return f"gpt-4o__{_config_short(config)}_{mode}"


def _vlmeval_slug(model: str, config: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")
    return f"{safe}__{_config_short(config)}"


# Letter-extraction fallback for prediction strings that aren't already a
# bare letter. Many VLMEvalKit dumps have `prediction` in one of:
#   "B"                              → B
#   "A. Political instability ..."   → A
#   "Answer: C. Gavin Hamilton"      → C
#   "H. Time waits for no man"       → H
# VLMEvalKit's own pipeline uses a judge LLM for ambiguous cases; we use
# a regex-only approximation so scoring stays deterministic + offline.
# Unrecognized / non-MCQ responses score 0, same as VLMEvalKit's default.
_CHOICE_RE = re.compile(
    r"^\s*(?:answer\s*[:\-]?\s*|the\s+answer\s+is\s*[:\-]?\s*)?([A-J])\b",
    re.IGNORECASE,
)
_CHOICE_TAIL_RE = re.compile(r"\b([A-J])\b")


def extract_choice_letter(pred_raw: object, valid: str = "ABCDEFGHIJ") -> str | None:
    if pred_raw is None:
        return None
    s = str(pred_raw).strip()
    if not s:
        return None
    if len(s) == 1 and s in valid:
        return s
    m = _CHOICE_RE.match(s)
    if m:
        letter = m.group(1).upper()
        if letter in valid:
            return letter
    # Fallback: first standalone A-J letter anywhere in the string. Rarely
    # needed, and can misfire on e.g. "option A is wrong, so B"; but for
    # this dataset most such strings start with the chosen letter.
    m = _CHOICE_TAIL_RE.search(s)
    return m.group(1) if m else None


def fetch_vlmeval_predictions() -> list[dict]:
    """Download + parse VLMEvalKit xlsx dumps for MMMU-Pro.

    Returns a list of runs shaped like GPT-4o runs (same keys) so they
    slot straight into the per-task matrix and rows_index.
    """
    try:
        import openpyxl  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "openpyxl is required to parse VLMEvalKit xlsx dumps. "
            "Install with: pip install openpyxl"
        ) from e

    cache_dir = HERE / "predictions"
    cache_dir.mkdir(exist_ok=True)

    out: list[dict] = []
    for model, config, subdir, fname in VLMEVAL_FILES:
        cache = cache_dir / fname
        if not cache.exists():
            url = f"{VLMEVAL_BASE}/{subdir}/{urllib.parse.quote(fname, safe='()._-')}"
            print(f"  fetching {fname}")
            cache.write_bytes(fetch(url))
        wb = openpyxl.load_workbook(cache, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h) if h is not None else "" for h in next(rows_iter)]
        idx = {h: i for i, h in enumerate(headers)}
        required = {"id", "answer", "prediction"}
        missing = required - set(headers)
        if missing:
            raise RuntimeError(f"{fname}: missing columns {missing} (got {headers})")

        tasks: list[dict] = []
        n_success = 0
        by_domain: dict[str, list[int]] = defaultdict(list)
        by_difficulty: dict[str, list[int]] = defaultdict(list)
        for row in rows_iter:
            if row is None or all(v is None for v in row):
                continue
            tid = row[idx["id"]]
            gold = (row[idx["answer"]] or "").strip() if isinstance(row[idx["answer"]], str) else row[idx["answer"]]
            pred_raw = row[idx["prediction"]]
            pred = extract_choice_letter(pred_raw)
            hit = 1 if (gold and pred == gold) else 0
            n_success += hit

            subject = row[idx["category"]] if "category" in idx else None
            domain = SUB_CAT2DOMAIN.get(subject) if subject else None
            difficulty = row[idx["topic_difficulty"]] if "topic_difficulty" in idx else None
            by_domain[domain or "unknown"].append(hit)
            by_difficulty[difficulty or "unknown"].append(hit)
            tasks.append(
                {
                    "task_name": tid,
                    "subject": subject,
                    "domain": domain,
                    "topic_difficulty": difficulty,
                    "n_trials": 1,
                    "n_success": hit,
                    "pass_rate": float(hit),
                    "pred": pred,
                    "pred_raw": str(pred_raw)[:120] if pred_raw is not None else None,
                    "answer": gold,
                }
            )

        out.append(
            {
                "slug": _vlmeval_slug(model, config),
                "model": model,
                "config": config,
                "mode": "direct",  # non-COT
                "source": f"VLMEvalKit / {VLMEVAL_DATASET}",
                "source_url": f"{VLMEVAL_BASE}/{subdir}/{urllib.parse.quote(fname, safe='()._-')}",
                "num_tasks": len(tasks),
                "total_trials": len(tasks),
                "total_successes": n_success,
                "pass_rate": (n_success / len(tasks)) if tasks else None,
                "pass_rate_pct": (n_success / len(tasks)) * 100 if tasks else None,
                "by_domain_pct": {
                    d: (sum(v) / len(v)) * 100 for d, v in by_domain.items() if v
                },
                "by_difficulty_pct": {
                    d: (sum(v) / len(v)) * 100 for d, v in by_difficulty.items() if v
                },
                "tasks": tasks,
            }
        )
    return out


def task_universe_from_predictions(
    preds: dict[tuple[str, str], list[dict]]
) -> list[dict]:
    """Use one config's dump as the canonical task universe.

    All 4 GPT-4o files share the same 1,730 `id`s (same underlying questions).
    We take labels off the standard(10 options) cot dump since it has the
    most complete metadata in practice.
    """
    base = preds.get(("standard (10 options)", "cot"))
    if not base:
        base = next(iter(preds.values()), [])
    tasks: list[dict] = []
    seen: set[str] = set()
    for r in base:
        tid = r.get("id")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        subject = r.get("subject") or ""
        tasks.append(
            {
                "task_id": tid,
                "subject": subject,
                "domain": SUB_CAT2DOMAIN.get(subject),
                "topic_difficulty": r.get("topic_difficulty"),
                "img_type": r.get("img_type"),
                "answer": r.get("answer"),
            }
        )
    return tasks


def build_gpt4o_run_details(
    preds: dict[tuple[str, str], list[dict]]
) -> list[dict]:
    """One synthetic 'row' per GPT-4o run (config × mode).

    These aren't leaderboard entries — the leaderboard has only one
    GPT-4o row with aggregate `pro_overall/vision/standard`. But for
    per-task matrix purposes it's easiest to emit each prediction dump
    as its own column so subset recomputation can pick config/mode.
    VLMEvalKit runs are emitted the same way via
    `fetch_vlmeval_predictions` and share the same row shape.
    """
    out: list[dict] = []
    for (config, mode), rows in preds.items():
        tasks: list[dict] = []
        n_success = 0
        by_domain: dict[str, list[int]] = defaultdict(list)
        by_difficulty: dict[str, list[int]] = defaultdict(list)
        for r in rows:
            ok = 1 if r.get("if_right") else 0
            n_success += ok
            subject = r.get("subject") or ""
            domain = SUB_CAT2DOMAIN.get(subject)
            by_domain[domain or "unknown"].append(ok)
            diff = r.get("topic_difficulty") or "unknown"
            by_difficulty[diff].append(ok)
            tasks.append(
                {
                    "task_name": r.get("id"),
                    "subject": subject,
                    "domain": domain,
                    "topic_difficulty": r.get("topic_difficulty"),
                    "n_trials": 1,
                    "n_success": ok,
                    "pass_rate": float(ok),
                    "pred": r.get("pred_indexs"),
                    "answer": r.get("answer"),
                }
            )
        by_domain_pct = {
            d: (sum(v) / len(v)) * 100 for d, v in by_domain.items() if v
        }
        by_difficulty_pct = {
            d: (sum(v) / len(v)) * 100 for d, v in by_difficulty.items() if v
        }
        out.append(
            {
                "slug": _run_slug(config, mode),
                "model": "GPT-4o (0513)",
                "config": config,
                "mode": mode,
                "source_url": (
                    f"{PRED_BASE}/{urllib.parse.quote(next(f for c, m, f in GPT4O_PREDICTION_FILES if c == config and m == mode), safe='()._-')}"
                ),
                "num_tasks": len(tasks),
                "total_trials": len(tasks),
                "total_successes": n_success,
                "pass_rate": (n_success / len(tasks)) if tasks else None,
                "pass_rate_pct": (n_success / len(tasks)) * 100 if tasks else None,
                "by_domain_pct": by_domain_pct,
                "by_difficulty_pct": by_difficulty_pct,
                "tasks": tasks,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def row_slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return s or "row"


SCHEMA = {
    "name": "Model name as shown on the leaderboard",
    "size": "Self-reported parameter count ('-' if unknown)",
    "date": "Submission / release date (YYYY-MM-DD)",
    "type": "proprietary | open_source | human_expert | random_frequent",
    "link": "Provider / paper / HF link (may be null)",
    "pro_overall": "MMMU-Pro headline accuracy % (average of pro_vision + pro_standard)",
    "pro_vision": "MMMU-Pro vision-config (CoT) accuracy %",
    "pro_standard": "MMMU-Pro standard-10-options (CoT) accuracy % (upstream key: `original`)",
    "pro_source": "Provenance of the pro score ('author' = self-reported)",
    "mmmu_val_overall": "MMMU-val overall accuracy % (secondary)",
    "mmmu_val_by_domain": "MMMU-val per-domain accuracies % (6 domains)",
    "mmmu_test_overall": "MMMU-test overall accuracy % (secondary)",
}


def write_leaderboard(rows: list[dict], detail_runs: list[dict], num_tasks: int) -> None:
    entries = sorted(rows, key=lambda r: -(r.get("pro_overall") or -1))
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "source_url": LEADERBOARD_URL,
                "project_page": PROJECT_PAGE,
                "benchmark": "mmmu-pro",
                "num_entries": len(entries),
                "num_tasks": num_tasks,
                "scoring": "accuracy % (MCQ, pass@1)",
                "configs": [
                    "standard (4 options)",
                    "standard (10 options) — leaderboard `original` column",
                    "vision — question rendered into screenshot",
                ],
                "leaderboard_note": (
                    "The `overall` column = average of `vision` and "
                    "`original` (= standard-10-options) scores, CoT. "
                    "Newer entries (roughly mid-2024 onward) report "
                    "`overall` only — `vision` / `original` breakdowns "
                    "are null for those."
                ),
                "detail_prediction_runs": [
                    {
                        "slug": r["slug"],
                        "model": r.get("model"),
                        "source": r.get("source", "MMMU authors"),
                        "config": r["config"],
                        "mode": r["mode"],
                        "num_tasks": r["num_tasks"],
                        "total_successes": r["total_successes"],
                        "pass_rate_pct": r["pass_rate_pct"],
                        "source_url": r.get("source_url"),
                    }
                    for r in detail_runs
                ],
                "schema": SCHEMA,
                "entries": entries,
            },
            indent=2,
        )
    )


def write_rows(rows: list[dict], gpt4o_runs: list[dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for old in rows_dir.glob("*.json"):
        old.unlink()

    seen: dict[str, int] = {}
    for r in rows:
        slug = row_slug(r["name"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}__{seen[slug]}"
        else:
            seen[slug] = 1
        entry = {
            "slug": slug,
            **r,
            "num_tasks": None,
            "total_trials": None,
            "total_successes": None,
            "tasks": [],
        }
        (rows_dir / f"{slug}.json").write_text(json.dumps(entry, indent=2))

    # Per-run GPT-4o detail rows. Not leaderboard entries — they're the
    # prediction-dump columns that populate per_task_matrix.json.
    for run in gpt4o_runs:
        (rows_dir / f"{run['slug']}.json").write_text(
            json.dumps(run, indent=2)
        )


def write_rows_index(rows: list[dict], gpt4o_runs: list[dict]) -> None:
    seen: dict[str, int] = {}
    missing: list[dict] = []
    for r in rows:
        slug = row_slug(r["name"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}__{seen[slug]}"
        else:
            seen[slug] = 1
        overall = r.get("pro_overall")
        missing.append(
            {
                "slug": slug,
                "name": r["name"],
                "type": r["type"],
                "size": r["size"],
                "date": r["date"],
                "pro_overall_pct": overall,
                "accuracy": (overall / 100.0) if overall is not None else None,
                "pro_vision_pct": r.get("pro_vision"),
                "pro_standard_pct": r.get("pro_standard"),
                "num_tasks": None,
                "total_trials": None,
                "recomputed_pass_rate": None,
            }
        )
    missing.sort(key=lambda r: -(r["pro_overall_pct"] or 0))

    detail_rows = [
        {
            "slug": run["slug"],
            "model": run["model"],
            "config": run["config"],
            "mode": run["mode"],
            "num_tasks": run["num_tasks"],
            "total_trials": run["total_trials"],
            "total_successes": run["total_successes"],
            "pass_rate": run["pass_rate"],
            "pass_rate_pct": run["pass_rate_pct"],
        }
        for run in sorted(gpt4o_runs, key=lambda r: -r["pass_rate_pct"])
    ]
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "num_with_detail": len(detail_rows),
                "num_missing_detail": len(missing),
                "note": (
                    "MMMU-Pro publishes per-instance predictions only for "
                    "GPT-4o, as 4 JSONL dumps (2 configs × {cot, direct}). "
                    "Those runs appear in `rows` below — they are NOT "
                    "separate leaderboard entries; the leaderboard carries "
                    "one aggregate GPT-4o row. Every other model lives in "
                    "`missing_detail` with aggregate scores only."
                ),
                "rows": detail_rows,
                "missing_detail": missing,
            },
            indent=2,
        )
    )


def write_matrix(tasks: list[dict], gpt4o_runs: list[dict]) -> None:
    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    for run in gpt4o_runs:
        for t in run["tasks"]:
            matrix[t["task_name"]][run["slug"]] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
                "pred": t["pred"],
            }
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "`matrix` has 4 columns (GPT-4o × 2 configs × 2 prompt "
                    "modes). No other model publishes per-question results. "
                    "`tasks` lists the 1,730-item universe with subject / "
                    "domain / topic_difficulty labels; task ids are shared "
                    "across configs, so a row like `test_History_1` "
                    "appears once in the universe but may have up to 4 "
                    "columns in the matrix (one per GPT-4o run)."
                ),
                "runs": [
                    {
                        "slug": run["slug"],
                        "config": run["config"],
                        "mode": run["mode"],
                        "pass_rate_pct": run["pass_rate_pct"],
                    }
                    for run in gpt4o_runs
                ],
                "tasks": tasks,
                "task_levels": {
                    t["task_id"]: {
                        "subject": t["subject"],
                        "domain": t["domain"],
                        "topic_difficulty": t["topic_difficulty"],
                    }
                    for t in tasks
                },
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
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument(
        "--skip-predict",
        action="store_true",
        help="Reuse predictions/*.jsonl from disk (if present)",
    )
    ap.add_argument(
        "--skip-vlmeval",
        action="store_true",
        help="Skip the VLMEvalKit xlsx ingestion (GPT-4o only)",
    )
    args = ap.parse_args()

    print("=" * 72)
    print("MMMU-Pro leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/4] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/4] fetching leaderboard_data.json")
        rows = scrape_leaderboard()
        print(f"  {len(rows)} rows with `pro` block")

    print("[2/5] fetching GPT-4o per-question predictions (4 JSONL files)")
    preds = fetch_gpt4o_predictions()
    for (config, mode), rs in preds.items():
        correct = sum(1 for r in rs if r.get("if_right"))
        print(f"  {config} / {mode}: {correct}/{len(rs)} correct")

    tasks = task_universe_from_predictions(preds)
    gpt4o_runs = build_gpt4o_run_details(preds)

    if args.skip_vlmeval:
        print("[3/5] skip VLMEvalKit — no additional detail rows")
        vlmeval_runs: list[dict] = []
    else:
        print(f"[3/5] fetching VLMEvalKit predictions ({len(VLMEVAL_FILES)} xlsx files)")
        vlmeval_runs = fetch_vlmeval_predictions()
        for r in vlmeval_runs:
            print(f"  {r['model']} / {r['config']}: "
                  f"{r['total_successes']}/{r['num_tasks']} "
                  f"= {r['pass_rate_pct']:.2f}%")

    all_runs = gpt4o_runs + vlmeval_runs

    print(f"[4/5] writing leaderboard.json + rows/ ({len(rows)} + {len(all_runs)} detail)")
    write_leaderboard(rows, all_runs, num_tasks=len(tasks))
    write_rows(rows, all_runs)

    print("[5/5] writing rows_index.json + per_task_matrix.json")
    write_rows_index(rows, all_runs)
    write_matrix(tasks, all_runs)

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list((HERE / "rows").glob("*.json")))
    print(f"  rows/  ({n} files)")
    print(f"  tasks: {len(tasks)}")


if __name__ == "__main__":
    main()
