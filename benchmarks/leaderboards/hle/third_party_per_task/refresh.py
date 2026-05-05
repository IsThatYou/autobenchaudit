#!/usr/bin/env python3
"""Refresh the HLE third-party per-task snapshot.

Scale does not publish per-question predictions for HLE. This snapshot
collects per-question `judge_response.correct` from two third-party
evaluation dumps that happen to share `cais/hle` question IDs, so the
cells merge into one `per_task_matrix`:

  1. ZenMux-1/zenmux-benchmark  (GitHub)
     60 (model, provider) rows, ~2,158 text-only questions each, judged
     by gpt-5 in Sept 2025. Text-only filter drops multimodal questions.

  2. supaihq/hle                (GitHub)
     One `judged_hle_pro.json` with 1,369 questions × ~19 frontier models
     (Nov 2025). Supaihq's run uses custom instructions + web search +
     confidence-retry, so absolute accuracies run ~5-10 points higher
     than stock eval — per-question pass/fail is still authoritative,
     rankings broadly hold.

Both sources produce the `run_judge_results.py` JSON shape:
  judge_response: {extracted_final_answer, reasoning, correct: "yes"|"no",
                   confidence: int}
keyed by the canonical `cais/hle` question IDs.

These are NOT Scale submissions. The accuracies here will differ from
the numbers on labs.scale.com/leaderboard because the prompts, temps,
judge configs, and (for supaihq) tool use are different. The value is
the per-question pattern — which questions a model gets right — for
subset-ranking exercises.

Outputs (under third_party_per_task/):
  rows/<slug>.json          # per (source, vendor, model, provider): metadata + per-question cells
  rows_index.json           # one-line per row, sorted by accuracy desc
  per_task_matrix.json      # {tasks: [...], matrix: {task_id: {slug: cell}}}
  leaderboard_alignment.json  # best-effort map to ../rows/*.json slugs

Usage:
  python refresh.py                # full refresh (~2-5 min, ~800MB download)
  python refresh.py --skip-fetch   # reuse prior ./_cache/ payloads
  python refresh.py --workers 6    # tune ingest parallelism
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "_cache"

ZENMUX_REPO = "ZenMux-1/zenmux-benchmark"
ZENMUX_BRANCH = "main"
ZENMUX_JUDGED_GLOB = "judged_hle_"

SUPAI_REPO = "supaihq/hle"
SUPAI_BRANCH = "main"
SUPAI_FILE = "judged_hle_pro.json"

UA = {"User-Agent": "hle-third-party-per-task-refresh/0.1"}


# --------------------------------------------------------------------------- #
# fetch helpers
# --------------------------------------------------------------------------- #
def _fetch(url: str, retries: int = 4, timeout: int = 300) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def _github_tree(repo: str, branch: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    data = json.loads(_fetch(url))
    if data.get("truncated"):
        print(f"WARNING: tree for {repo}@{branch} is truncated", file=sys.stderr)
    return data["tree"]


def _raw_url(repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def _cached_fetch(url: str, key: str) -> bytes:
    """Download to `_cache/<key>` and return bytes; reuse if present."""
    CACHE_DIR.mkdir(exist_ok=True)
    cached = CACHE_DIR / key
    if cached.exists() and cached.stat().st_size > 0:
        return cached.read_bytes()
    raw = _fetch(url)
    cached.write_bytes(raw)
    return raw


# --------------------------------------------------------------------------- #
# ZenMux ingest
# --------------------------------------------------------------------------- #
_ZENMUX_NAME_RE = re.compile(
    r"judged_hle_(?P<vendor>[^_]+)_(?P<model>.+)_(?P<provider>[^_]+)_\d{8}_\d{6}\.json$"
)


def parse_zenmux_filename(name: str) -> dict[str, str] | None:
    m = _ZENMUX_NAME_RE.search(name)
    if not m:
        return None
    return {"vendor": m["vendor"], "model": m["model"], "provider": m["provider"]}


def extract_zenmux_row(raw_bytes: bytes, filename: str) -> dict:
    """Parse one `judged_hle_<vendor>_<model>_<provider>_<ts>.json`.

    Returns `{"slug", "source", "vendor", "model", "provider", "model_identifier",
    "run_timestamp", "text_only", "num_questions", "num_correct",
    "accuracy", "avg_confidence", "tasks": [{task_id, correct, confidence, model_answer}]}`.
    """
    data = json.loads(raw_bytes)
    meta = data["judging_metadata"]
    preds = data["judged_predictions"]
    eval_meta = meta["evaluation_metadata"]
    parts = parse_zenmux_filename(filename) or {}
    endpoint = eval_meta.get("endpoint") or {}

    tasks: list[dict] = []
    n_correct = 0
    conf_sum = 0
    conf_n = 0
    for qid, pred in preds.items():
        jr = pred.get("judge_response") or {}
        is_correct = jr.get("correct") == "yes"
        if is_correct:
            n_correct += 1
        confidence = jr.get("confidence")
        if isinstance(confidence, (int, float)):
            conf_sum += confidence
            conf_n += 1
        # Keep `model_answer` short so row files stay browsable. Full
        # response + reasoning live upstream in ZenMux's repo.
        ans = jr.get("model_answer") or ""
        if len(ans) > 240:
            ans = ans[:237] + "..."
        tasks.append(
            {
                "task_id": qid,
                "correct": 1 if is_correct else 0,
                "confidence": confidence,
                "model_answer": ans,
            }
        )
    tasks.sort(key=lambda t: t["task_id"])
    n = len(tasks)

    slug = _zenmux_slug(parts.get("vendor", ""), parts.get("model", ""), parts.get("provider", ""))
    return {
        "slug": slug,
        "source": "zenmux",
        "source_file": filename,
        "model_identifier": eval_meta.get("model_identifier"),
        "vendor": parts.get("vendor"),
        "model": parts.get("model"),
        "provider": parts.get("provider"),
        "endpoint_provider": endpoint.get("provider"),
        "endpoint_context_length": endpoint.get("context_length"),
        "run_timestamp": eval_meta.get("timestamp"),
        "judge_timestamp": meta.get("timestamp"),
        "judge_model": meta.get("judge_model"),
        "text_only": eval_meta.get("dataset_config", {}).get("text_only"),
        "num_questions": n,
        "num_correct": n_correct,
        "accuracy": (n_correct / n) if n else None,
        "avg_confidence": (conf_sum / conf_n) if conf_n else None,
        "tasks": tasks,
    }


def _zenmux_slug(vendor: str, model: str, provider: str) -> str:
    s = f"zenmux__{vendor}__{model}__{provider}"
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s)
    return s.strip("-") or "zenmux__unknown"


def list_zenmux_files() -> list[dict]:
    """Return `[{path, size}]` for all judged HLE files in ZenMux."""
    tree = _github_tree(ZENMUX_REPO, ZENMUX_BRANCH)
    out = []
    for t in tree:
        p = t.get("path", "")
        if ZENMUX_JUDGED_GLOB in p and p.endswith(".json"):
            out.append({"path": p, "size": t.get("size", 0)})
    out.sort(key=lambda x: x["path"])
    return out


# --------------------------------------------------------------------------- #
# supaihq ingest
# --------------------------------------------------------------------------- #
_SUPAI_EXCLUDE_MODELS = {"main"}  # "main" = Sup AI's meta-ensemble, not a single model


def extract_supai_rows(raw_bytes: bytes) -> list[dict]:
    """Supaihq ships one file with per-question judgments for many models.

    Schema: `{question_id: {model, response: {sub_model: str}, judge_response:
    {sub_model: {correct, confidence, model_answer, ...}}}}`. We emit one row
    per sub-model (dropping "main" because it's Sup AI's ensembled answer,
    which is not an individual-model result).
    """
    data = json.loads(raw_bytes)
    # model -> {qid -> cell}
    per_model: dict[str, dict[str, dict]] = {}
    for qid, q in data.items():
        jr_map = q.get("judge_response") or {}
        for m, jr in jr_map.items():
            if m in _SUPAI_EXCLUDE_MODELS:
                continue
            if not isinstance(jr, dict):
                continue
            is_correct = jr.get("correct") == "yes"
            confidence = jr.get("confidence")
            ans = jr.get("model_answer") or ""
            if len(ans) > 240:
                ans = ans[:237] + "..."
            per_model.setdefault(m, {})[qid] = {
                "task_id": qid,
                "correct": 1 if is_correct else 0,
                "confidence": confidence,
                "model_answer": ans,
            }

    rows: list[dict] = []
    for m, cells in per_model.items():
        n = len(cells)
        n_correct = sum(c["correct"] for c in cells.values())
        conf = [c["confidence"] for c in cells.values() if isinstance(c["confidence"], (int, float))]
        avg_conf = (sum(conf) / len(conf)) if conf else None
        tasks = sorted(cells.values(), key=lambda c: c["task_id"])

        vendor = m.split("/", 1)[0] if "/" in m else m
        model_short = m.split("/", 1)[1] if "/" in m else m
        slug = _supai_slug(m)
        rows.append(
            {
                "slug": slug,
                "source": "supai",
                "source_file": SUPAI_FILE,
                "model_identifier": m,
                "vendor": vendor,
                "model": model_short,
                "provider": None,
                "num_questions": n,
                "num_correct": n_correct,
                "accuracy": (n_correct / n) if n else None,
                "avg_confidence": avg_conf,
                "tasks": tasks,
            }
        )
    rows.sort(key=lambda r: -(r["accuracy"] or 0))
    return rows


def _supai_slug(identifier: str) -> str:
    s = f"supai__{identifier}"
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s)
    return s.strip("-") or "supai__unknown"


# --------------------------------------------------------------------------- #
# leaderboard alignment
# --------------------------------------------------------------------------- #
_NORM_DROP_TOKENS = (
    "thinking", "preview", "experimental", "instant", "non-thinking",
    "text-only", "xhigh", "medium", "high", "low",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def _norm(s: str | None) -> str:
    """Normalize a model name for approximate matching.

    The leaderboard uses free-form strings ("Claude Opus 4 (Thinking)",
    "claude-opus-4-5-20251101-thinking", "GPT-4.1", ...). Third-party
    slugs use kebab-case vendor/model ("claude-opus-4.1", "gpt-5"). We
    strip dates, reasoning-knob tokens, and all non-alnum separators so
    both render as the same bare-metal identifier.
    """
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\b20\d{2}[-_/]?\d{2}[-_/]?\d{2}\b", "", s)   # YYYY-MM-DD
    s = re.sub(r"\b20\d{2}\b", "", s)                          # bare year
    for tok in _NORM_DROP_TOKENS:
        s = re.sub(rf"\b{re.escape(tok)}\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def align_with_leaderboard(third_party_rows: list[dict]) -> dict:
    """Best-effort map each third-party slug to Scale leaderboard slugs.

    Matching is exact-only on normalized names, because substring match
    produces false positives across model tiers (gpt-4.1-mini → GPT-4.1,
    gemini-2.5-flash-lite → Gemini 2.5 Flash, etc.).

    Result kinds:
      - 'single'     one leaderboard row matches after normalization
      - 'multi'      multiple rows match (Scale often lists the same base
                     model with different reasoning efforts or dated
                     variants; third-party runs don't carry that axis)
      - 'none'       no leaderboard row matches

    `leaderboard_slugs` lists every match so the caller can disambiguate
    by date / reasoning effort.
    """
    lb_path = HERE.parent / "leaderboard.json"
    if not lb_path.exists():
        return {"leaderboard_missing": True, "mappings": []}
    lb = json.loads(lb_path.read_text())
    lb_entries = lb["entries"]
    # slug the leaderboard the same way ../refresh.py does
    def _lb_slug(model: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_") or "row"

    lb_normed = [
        {"slug": _lb_slug(e["model"]), "model": e["model"], "norm": _norm(e["model"])}
        for e in lb_entries
    ]

    mappings: list[dict] = []
    for r in third_party_rows:
        # Use the short model name (not model_identifier, which embeds the
        # vendor/provider) so normalization can match Scale's free-form
        # strings.
        candidate = _norm(r.get("model"))
        matches = [x for x in lb_normed if x["norm"] == candidate] if candidate else []
        if not matches:
            kind = "none"
        elif len(matches) == 1:
            kind = "single"
        else:
            kind = "multi"
        mappings.append(
            {
                "third_party_slug": r["slug"],
                "third_party_model": r.get("model"),
                "match_kind": kind,
                "leaderboard_slugs": [x["slug"] for x in matches],
                "leaderboard_models": [x["model"] for x in matches],
            }
        )
    return {
        "leaderboard_missing": False,
        "num_third_party_rows": len(third_party_rows),
        "num_single": sum(1 for m in mappings if m["match_kind"] == "single"),
        "num_multi": sum(1 for m in mappings if m["match_kind"] == "multi"),
        "num_none": sum(1 for m in mappings if m["match_kind"] == "none"),
        "note": (
            "Names are normalized (lower-case, dates stripped, reasoning-"
            "knob tokens stripped, all separators dropped) and compared "
            "for equality. 'multi' means Scale lists the same base model "
            "under several reasoning efforts or dates; pick one by "
            "comparing created_at or reasoning-effort suffix. Pure "
            "substring matches are not reported because they confuse model "
            "tiers (mini/nano/lite/chat)."
        ),
        "mappings": mappings,
    }


# --------------------------------------------------------------------------- #
# writers
# --------------------------------------------------------------------------- #
def write_row_file(row: dict, rows_dir: Path) -> None:
    (rows_dir / f"{row['slug']}.json").write_text(json.dumps(row, indent=2))


def write_rows_index(rows: list[dict]) -> None:
    summaries = []
    for r in rows:
        summaries.append(
            {
                "slug": r["slug"],
                "source": r["source"],
                "vendor": r["vendor"],
                "model": r["model"],
                "provider": r["provider"],
                "model_identifier": r.get("model_identifier"),
                "num_questions": r["num_questions"],
                "num_correct": r["num_correct"],
                "accuracy": r["accuracy"],
                "accuracy_pct": round(r["accuracy"] * 100, 2) if r["accuracy"] is not None else None,
                "avg_confidence": r["avg_confidence"],
            }
        )
    summaries.sort(key=lambda r: -(r["accuracy"] or 0))
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(summaries),
                "sources": sorted({r["source"] for r in rows}),
                "note": (
                    "Third-party per-question HLE judgments. NOT Scale "
                    "submissions. Accuracies differ from labs.scale.com "
                    "because prompts, temperatures, judge configs, and (for "
                    "supaihq) tool use differ. Use for per-question pattern "
                    "analysis, not for leaderboard ranking."
                ),
                "rows": summaries,
            },
            indent=2,
        )
    )


def build_per_task_matrix(rows: list[dict]) -> dict:
    all_tasks: set[str] = set()
    matrix: dict[str, dict[str, dict]] = {}
    for r in rows:
        slug = r["slug"]
        src = r["source"]
        for t in r["tasks"]:
            tid = t["task_id"]
            all_tasks.add(tid)
            cell = {
                "pass_rate": 1.0 if t["correct"] else 0.0,
                "n_trials": 1,
                "n_success": 1 if t["correct"] else 0,
                "confidence": t["confidence"],
                "source": src,
            }
            matrix.setdefault(tid, {})[slug] = cell
    tasks_sorted = sorted(all_tasks)
    return {
        "note": (
            "Per-question judgments merged from ZenMux and supaihq. Cells "
            "are pass@1 (n_trials=1). `source` records which dump the cell "
            "came from. Not every (task, row) pair is filled because ZenMux "
            "runs text-only (~2,158 questions) and supaihq runs a 1,369-question "
            "subset; use `matrix[task_id].keys()` to see which rows judged "
            "which task."
        ),
        "num_tasks": len(tasks_sorted),
        "num_rows": len({s for cells in matrix.values() for s in cells}),
        "tasks": tasks_sorted,
        "matrix": matrix,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-fetch", action="store_true", help="reuse `_cache/` contents")
    ap.add_argument("--workers", type=int, default=4, help="parallel fetches")
    args = ap.parse_args()

    print("=" * 72)
    print("HLE third-party per-task refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for old in rows_dir.glob("*.json"):
        old.unlink()

    rows: list[dict] = []

    # -- ZenMux ----------------------------------------------------------
    print("[1/4] ZenMux: enumerating judged files")
    zm_files = list_zenmux_files()
    zm_total = sum(f["size"] for f in zm_files)
    print(f"  {len(zm_files)} files, ~{zm_total / 1e6:.0f} MB total")

    def _ingest(f: dict) -> dict:
        url = _raw_url(ZENMUX_REPO, ZENMUX_BRANCH, f["path"])
        key = f"zenmux__{Path(f['path']).name}"
        raw = _cached_fetch(url, key) if not args.skip_fetch else (CACHE_DIR / key).read_bytes()
        return extract_zenmux_row(raw, Path(f["path"]).name)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_ingest, f): f for f in zm_files}
        for fut in cf.as_completed(futures):
            f = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                print(f"  ! {f['path']}: {e}", file=sys.stderr)
                continue
            rows.append(row)
            write_row_file(row, rows_dir)
            done += 1
            acc = (row["accuracy"] or 0) * 100
            print(
                f"  [{done:>2}/{len(zm_files)}] {row['slug']:<70} "
                f"{row['num_correct']:>4}/{row['num_questions']:<4} = {acc:5.2f}%"
            )

    # -- supaihq ---------------------------------------------------------
    print("[2/4] supaihq: fetching judged_hle_pro.json")
    supai_url = _raw_url(SUPAI_REPO, SUPAI_BRANCH, SUPAI_FILE)
    supai_key = f"supai__{SUPAI_FILE}"
    try:
        supai_bytes = (
            _cached_fetch(supai_url, supai_key)
            if not args.skip_fetch
            else (CACHE_DIR / supai_key).read_bytes()
        )
        supai_rows = extract_supai_rows(supai_bytes)
    except Exception as e:
        print(f"  ! supaihq fetch/parse failed: {e}", file=sys.stderr)
        supai_rows = []
    for row in supai_rows:
        rows.append(row)
        write_row_file(row, rows_dir)
        acc = (row["accuracy"] or 0) * 100
        print(
            f"  {row['slug']:<70} "
            f"{row['num_correct']:>4}/{row['num_questions']:<4} = {acc:5.2f}%"
        )

    # -- rows_index + matrix --------------------------------------------
    print("[3/4] writing rows_index.json + per_task_matrix.json")
    write_rows_index(rows)
    matrix = build_per_task_matrix(rows)
    (HERE / "per_task_matrix.json").write_text(json.dumps(matrix, indent=2))

    # -- alignment -------------------------------------------------------
    print("[4/4] aligning with ../leaderboard.json")
    alignment = align_with_leaderboard(rows)
    (HERE / "leaderboard_alignment.json").write_text(json.dumps(alignment, indent=2))

    print()
    print("done. outputs:")
    for f in ("rows_index.json", "per_task_matrix.json", "leaderboard_alignment.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list(rows_dir.glob("*.json")))
    print(f"  rows/  ({n} files)")
    if not alignment.get("leaderboard_missing"):
        n_tp = alignment["num_third_party_rows"]
        print(
            f"  alignment: {alignment['num_single']} single + "
            f"{alignment['num_multi']} multi + {alignment['num_none']} none "
            f"of {n_tp} rows"
        )


if __name__ == "__main__":
    main()
