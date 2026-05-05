#!/usr/bin/env python3
"""Refresh the Toolathlon leaderboard snapshot.

Two sources used end-to-end:

  1. `https://toolathlon.xyz/docs/leaderboard`
     A Mintlify page whose leaderboard is rendered as a plain HTML
     `<table class="performance-table">` with every row carrying aggregate
     `Pass@1`, `Pass@3`, `Pass^3`, and `# Turns` (with optional `± stderr`).
  2. `https://huggingface.co/datasets/hkust-nlp/Toolathlon-Trajectories`
     Maintainer-uploaded trajectories: one JSONL per `{model}_{run}` with
     108 lines, each containing `task_name` and `task_status.evaluation`
     (boolean pass/fail). Three runs per model → three trials per task.

Only rows whose model slug has trajectories on HF carry per-task data; other
rows end up in `rows_index.json` → `missing_detail`.

Outputs (all under this directory):
  leaderboard.json           # 44 overview rows
  rows/<slug>.json           # per-row: metadata + per-task stats (n_trials, n_success, pass_rate)
  rows_index.json            # one-line summary per row, sorted by Pass@1
  per_task_matrix.json       # {task: {row_slug: {pass_rate, n_trials, n_success}}}

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-scrape    # reuse existing leaderboard.json
  python refresh.py --skip-details   # reuse existing rows/*.json (skip HF downloads)
  python refresh.py --workers 8      # adjust HF download parallelism
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEADERBOARD_URL = "https://toolathlon.xyz/docs/leaderboard"
HF_TREE_API = (
    "https://huggingface.co/api/datasets/hkust-nlp/Toolathlon-Trajectories/tree/main"
)
HF_RESOLVE = (
    "https://huggingface.co/datasets/hkust-nlp/Toolathlon-Trajectories/resolve/main"
)

# Override table: leaderboard model display name -> HF model slug.
# The HF dataset uses canonical checkpoint-suffixed slugs (e.g. "claude-4.5-sonnet-0929")
# while the leaderboard shows a display name without the date ("Claude-4.5-Sonnet").
# Anything not covered here falls back to the normalized-prefix match below.
MODEL_ALIASES: dict[str, str] = {
    "Claude-4-Sonnet": "claude-4-sonnet-0514",
    "Claude-4.5-haiku": "claude-4.5-haiku-1001",
    "Claude-4.5-Opus": "claude-4.5-opus",
    "Claude-4.5-Sonnet": "claude-4.5-sonnet-0929",
    "DeepSeek-V3.2-Exp": "deepseek-v3.2-exp",
    "DeepSeek-V3.2-Thinking": "deepseek-3.2-thinking",
    "Gemini-2.5-Flash": "gemini-2.5-flash",
    "Gemini-2.5-Pro": "gemini-2.5-pro",
    "Gemini-3-Pro": "gemini-3-pro-preview",
    "GLM-4.6": "glm-4.6",
    "GPT-5-high": "gpt-5-high",
    "GPT-5-mini": "gpt-5-mini",
    "GPT-5.1-high": "gpt-5.1",
    "Grok-4": "grok-4",
    "Grok-4-Fast": "grok-4-fast",
    "Grok-Code-Fast-1": "grok-code-fast-1",
    "Kimi-K2-0905": "kimi-k2-0905",
    "o3": "o3",
    "o4-mini": "o4-mini",
    "Qwen-3-Coder": "qwen-3-coder",
}


def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "toolathlon-leaderboard-refresh/0.1"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Step 1: scrape toolathlon.xyz leaderboard
# --------------------------------------------------------------------------- #
def _clean(txt: str) -> str:
    txt = re.sub(r"<svg\b.*?</svg>", "", txt, flags=re.DOTALL)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _split_score(text: str) -> tuple[float | None, float | None]:
    """Split `"49.4 ± 0.4"` / `"54.6"` / `"—"` into (score, stderr)."""
    t = text.replace("—", "").strip()
    if not t:
        return None, None
    m = re.match(r"([\d.]+)(?:\s*[†‡*]+)?(?:\s*±\s*([\d.]+))?", t)
    if not m:
        return None, None
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def scrape_leaderboard() -> list[dict]:
    page = fetch(LEADERBOARD_URL).decode("utf-8", errors="replace")
    m = re.search(
        r'class="performance-table".*?<tbody>(.*?)</tbody>', page, re.DOTALL
    )
    if not m:
        raise RuntimeError("Could not locate <table class=performance-table>")
    body = m.group(1)

    rows: list[dict] = []
    for tr_attrs, rh in re.findall(r"<tr\b([^>]*)>(.*?)</tr>", body, re.DOTALL):
        rank_m = re.search(r'class="(rank-\S+)"', tr_attrs)
        cells = re.findall(r"<td\b([^>]*)>(.*?)</td>", rh, re.DOTALL)
        row: dict = {"rank_class": rank_m.group(1) if rank_m else None}
        for attrs, content in cells:
            label_m = re.search(r'data-label="([^"]+)"', attrs)
            label = label_m.group(1) if label_m else "col"
            href_m = re.search(r'<a\s[^>]*href="([^"]+)"', content)
            cell = {
                "text": _clean(content).replace("✓", "").strip(),
                "href": href_m.group(1) if href_m else None,
                "verified": ("verified-badge" in content) or ("✓" in content),
            }
            if label in {"Pass@1", "Pass@3", "Pass^3", "# Turns"}:
                cell["score"], cell["stderr"] = _split_score(cell["text"])
            row[label] = cell

        # Normalize into a flat entry.
        model_text = row.get("Model", {}).get("text", "")
        # Strip trailing dagger markers like "‡", "†", "*"
        clean_model = re.sub(r"\s*[†‡*]+\s*$", "", model_text).strip()
        has_dagger = clean_model != model_text
        entry = {
            "rank_class": row["rank_class"],
            "model": clean_model,
            "model_url": row.get("Model", {}).get("href"),
            "model_verified": row.get("Model", {}).get("verified", False),
            "model_has_footnote": has_dagger,
            "model_type": row.get("Model Type", {}).get("text"),
            "agent": row.get("Agent", {}).get("text"),
            "date": row.get("Date", {}).get("text"),
            "pass_at_1": row.get("Pass@1", {}).get("score"),
            "pass_at_1_stderr": row.get("Pass@1", {}).get("stderr"),
            "pass_at_3": row.get("Pass@3", {}).get("score"),
            "pass_pow_3": row.get("Pass^3", {}).get("score"),
            "avg_turns": row.get("# Turns", {}).get("score"),
        }
        rows.append(entry)
    return rows


# --------------------------------------------------------------------------- #
# Step 2: Hugging Face trajectories → per-task stats
# --------------------------------------------------------------------------- #
def list_hf_files() -> list[str]:
    tree = json.loads(fetch(HF_TREE_API).decode("utf-8"))
    return sorted(e["path"] for e in tree if e["path"].endswith(".jsonl"))


def hf_model_slugs(files: list[str]) -> dict[str, list[str]]:
    """Group HF filenames by model slug. Each model has 3 runs (`_1`, `_2`, `_3`)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for name in files:
        m = re.match(r"(.+)_(\d+)\.jsonl$", name)
        if m:
            groups[m.group(1)].append(name)
    return {k: sorted(v) for k, v in groups.items()}


def _norm(s: str) -> str:
    """Lowercase, drop everything but [a-z0-9]."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match_rows_to_hf(rows: list[dict], hf_slugs: set[str]) -> dict[int, str]:
    """Return {leaderboard_row_index: hf_slug} for rows with HF data."""
    # Cache normalized HF slugs. Longer first so prefix matching prefers specific.
    norm_to_slug = {_norm(s): s for s in hf_slugs}
    sorted_norms = sorted(norm_to_slug.keys(), key=len, reverse=True)

    mapping: dict[int, str] = {}
    for i, row in enumerate(rows):
        name = row["model"]
        if name in MODEL_ALIASES:
            slug = MODEL_ALIASES[name]
            if slug in hf_slugs:
                mapping[i] = slug
                continue
        n = _norm(name)
        # Try: leaderboard_norm is prefix of HF_norm, OR HF_norm == leaderboard_norm
        for hn in sorted_norms:
            if hn == n or hn.startswith(n):
                mapping[i] = norm_to_slug[hn]
                break
    return mapping


def stream_tasks(url: str) -> list[dict]:
    """Download an HF JSONL trajectory file and yield compact per-task records."""
    raw = fetch(url)
    out: list[dict] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = obj.get("task_status") or {}
        # task_status is stored as a JSON-encoded string in the dataset
        if isinstance(status, str):
            try:
                status = json.loads(status)
            except json.JSONDecodeError:
                status = {}
        out.append(
            {
                "task_name": obj.get("task_name"),
                "evaluation": bool(status.get("evaluation")),
                "running": status.get("running"),
                "preprocess": status.get("preprocess"),
            }
        )
    return out


def row_slug(model: str, agent: str | None) -> str:
    """Filesystem-safe slug for a leaderboard row.

    Includes agent when it's non-default (avoids collisions between e.g.
    `Claude-4.6-Opus` under `Default` vs `Claude Agent SDK`).
    """
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_")
    if agent and agent != "Default":
        suffix = re.sub(r"[^A-Za-z0-9._-]+", "_", agent).strip("_")
        return f"{base}__{suffix}"
    return base


def fetch_and_aggregate(
    row: dict, hf_slug: str, runs: list[str]
) -> dict:
    """Download all runs for an HF model and fold into per-task aggregates."""
    per_task: dict[str, list[dict]] = defaultdict(list)
    for run_file in runs:
        url = f"{HF_RESOLVE}/{run_file}"
        for t in stream_tasks(url):
            if not t["task_name"]:
                continue
            per_task[t["task_name"]].append(t)

    tasks_out: list[dict] = []
    for task_name in sorted(per_task):
        trials = per_task[task_name]
        n_trials = len(trials)
        n_success = sum(1 for t in trials if t["evaluation"])
        tasks_out.append(
            {
                "task_name": task_name,
                "n_trials": n_trials,
                "n_success": n_success,
                "pass_rate": n_success / n_trials if n_trials else 0.0,
                "trial_running_statuses": [t["running"] for t in trials],
            }
        )

    return {
        "slug": row_slug(row["model"], row["agent"]),
        "model": row["model"],
        "model_type": row["model_type"],
        "agent": row["agent"],
        "date": row["date"],
        "pass_at_1": row["pass_at_1"],
        "pass_at_1_stderr": row["pass_at_1_stderr"],
        "pass_at_3": row["pass_at_3"],
        "pass_pow_3": row["pass_pow_3"],
        "avg_turns": row["avg_turns"],
        "verified": row["model_verified"],
        "hf_slug": hf_slug,
        "hf_runs": runs,
        "num_tasks": len(tasks_out),
        "total_trials": sum(t["n_trials"] for t in tasks_out),
        "total_successes": sum(t["n_success"] for t in tasks_out),
        "tasks": tasks_out,
    }


def fetch_all_details(
    rows: list[dict],
    mapping: dict[int, str],
    hf_runs: dict[str, list[str]],
    workers: int,
) -> dict[str, dict]:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)

    jobs: list[tuple[int, dict, str, list[str]]] = []
    for idx, slug in mapping.items():
        jobs.append((idx, rows[idx], slug, hf_runs[slug]))

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(fetch_and_aggregate, row, slug, runs): (idx, row, slug)
            for idx, row, slug, runs in jobs
        }
        for i, fut in enumerate(as_completed(futures), 1):
            idx, row, slug = futures[fut]
            try:
                entry = fut.result()
            except Exception as e:
                print(
                    f"  [{i}/{len(jobs)}] FAIL {row['model']} ({slug}): {e}",
                    file=sys.stderr,
                )
                continue
            (rows_dir / f"{entry['slug']}.json").write_text(
                json.dumps(entry, indent=2)
            )
            results[entry["slug"]] = entry
            print(
                f"  [{i}/{len(jobs)}] {entry['slug']}: "
                f"{entry['num_tasks']} tasks, "
                f"{entry['total_successes']}/{entry['total_trials']} trials, "
                f"recomputed={entry['total_successes']/entry['total_trials']:.3f}"
            )
    return results


# --------------------------------------------------------------------------- #
# Step 3: per-task matrix + rows index
# --------------------------------------------------------------------------- #
def build_matrix(rows_data: dict[str, dict]) -> dict:
    matrix: dict[str, dict[str, dict]] = defaultdict(dict)
    all_tasks: set[str] = set()
    for slug, row in rows_data.items():
        for t in row["tasks"]:
            all_tasks.add(t["task_name"])
            matrix[t["task_name"]][slug] = {
                "pass_rate": t["pass_rate"],
                "n_trials": t["n_trials"],
                "n_success": t["n_success"],
            }
    return {"tasks": sorted(all_tasks), "matrix": dict(matrix)}


def build_rows_index(
    rows: list[dict], mapping: dict[int, str], rows_data: dict[str, dict]
) -> dict:
    out_rows: list[dict] = []
    missing: list[dict] = []
    for idx, row in enumerate(rows):
        slug_guess = row_slug(row["model"], row["agent"])
        hf_slug = mapping.get(idx)
        entry = rows_data.get(slug_guess) if hf_slug else None

        pass_at_1 = row["pass_at_1"]
        summary = {
            "slug": slug_guess,
            "model": row["model"],
            "agent": row["agent"],
            "model_type": row["model_type"],
            "date": row["date"],
            "pass_at_1": pass_at_1,
            "pass_at_3": row["pass_at_3"],
            "pass_pow_3": row["pass_pow_3"],
            "avg_turns": row["avg_turns"],
            "verified": row["model_verified"],
            "hf_slug": hf_slug,
            # Canonical 0–1 pass rate so cross-benchmark consumers (the
            # visualizer, in particular) can key on a single field name.
            "accuracy": (pass_at_1 / 100.0) if pass_at_1 is not None else None,
        }
        if entry:
            recomputed = (
                entry["total_successes"] / entry["total_trials"]
                if entry["total_trials"]
                else None
            )
            summary["num_tasks"] = entry["num_tasks"]
            summary["total_trials"] = entry["total_trials"]
            summary["recomputed_pass_rate"] = recomputed
            out_rows.append(summary)
        else:
            missing.append(summary)
    out_rows.sort(key=lambda r: -(r["pass_at_1"] or 0))
    missing.sort(key=lambda r: -(r["pass_at_1"] or 0))
    return {
        "num_rows": len(rows),
        "num_with_detail": len(out_rows),
        "num_missing_detail": len(missing),
        "rows": out_rows,
        "missing_detail": missing,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-details", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    print("=" * 72)
    print("Toolathlon leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    leaderboard_path = HERE / "leaderboard.json"
    if args.skip_scrape and leaderboard_path.exists():
        print("[1/3] skip scrape — reusing leaderboard.json")
        rows = json.loads(leaderboard_path.read_text())["entries"]
    else:
        print("[1/3] scraping toolathlon.xyz leaderboard")
        rows = scrape_leaderboard()
        leaderboard_path.write_text(
            json.dumps(
                {
                    "source_url": LEADERBOARD_URL,
                    "benchmark": "toolathlon",
                    "num_entries": len(rows),
                    "schema": {
                        "model": "Model display name (daggers like † ‡ stripped)",
                        "model_url": "Link attached to the model name, if any",
                        "model_verified": "True if the row carries the ✓ verified badge",
                        "model_has_footnote": "True if the name carried a † / ‡ footnote marker",
                        "model_type": "Proprietary / Open-Source",
                        "agent": "Agent framework name (e.g. Default, Claude Agent SDK)",
                        "date": "Submission / evaluation date (YYYY-MM-DD)",
                        "pass_at_1": "Pass@1 (percent, 0-100)",
                        "pass_at_1_stderr": "Stderr reported after ±, if any",
                        "pass_at_3": "Pass@3 (percent, 0-100)",
                        "pass_pow_3": "Pass^3 — stricter 'all 3 trials pass' metric",
                        "avg_turns": "Mean interaction turns per task",
                        "rank_class": "Row css class (rank-1/2/3/other)",
                    },
                    "entries": rows,
                },
                indent=2,
            )
        )
        print(f"  -> wrote leaderboard.json ({len(rows)} entries)")

    print("[2/3] listing HF trajectories dataset")
    files = list_hf_files()
    hf_runs = hf_model_slugs(files)
    print(f"  {len(files)} JSONL files → {len(hf_runs)} model slugs")
    mapping = match_rows_to_hf(rows, set(hf_runs))
    matched = sum(1 for _ in mapping)
    print(f"  matched {matched}/{len(rows)} leaderboard rows to HF data")
    for idx, slug in sorted(mapping.items()):
        print(f"    {rows[idx]['model']:40s} -> {slug}")
    unmatched_hf = set(hf_runs) - set(mapping.values())
    if unmatched_hf:
        print(f"  HF slugs without a leaderboard row: {sorted(unmatched_hf)}")

    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    if args.skip_details:
        print("[2.5/3] skip HF fetch — reading existing rows/*.json")
        rows_data: dict[str, dict] = {}
        for f in rows_dir.glob("*.json"):
            d = json.loads(f.read_text())
            rows_data[d["slug"]] = d
    else:
        print(
            f"[2.5/3] fetching {len(mapping)} HF models "
            f"({args.workers} workers, 3 runs each)"
        )
        rows_data = fetch_all_details(rows, mapping, hf_runs, args.workers)

    print("[3/3] building rows_index.json + per_task_matrix.json")
    (HERE / "rows_index.json").write_text(
        json.dumps(build_rows_index(rows, mapping, rows_data), indent=2)
    )
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(build_matrix(rows_data), indent=2)
    )

    print()
    print("done. outputs:")
    for f in ("leaderboard.json", "rows_index.json", "per_task_matrix.json"):
        p = HERE / f
        if p.exists():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    n = len(list(rows_dir.glob("*.json")))
    print(f"  rows/  ({n} files)")


if __name__ == "__main__":
    main()
