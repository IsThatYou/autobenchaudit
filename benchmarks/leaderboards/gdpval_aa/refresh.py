#!/usr/bin/env python3
"""Refresh the GDPval-AA leaderboard snapshot.

GDPval is OpenAI's 220-task benchmark of economically valuable knowledge
work, graded by blinded pairwise comparison against a human-expert baseline.
Two public leaderboards evaluate models on the same 220 tasks:

  - Artificial Analysis's GDPval-AA runs its own reference agent (Stirrup)
    with shell + web and posts ELO from blinded pairwise comparisons
    (336 models). Published per-model: `elo`, `n_matches`, 95% CI,
    `avg_turns`, token use. No per-instance or per-category breakdown.
  - OpenAI's own grader (evals.openai.com/gdpval/leaderboard) posts
    17 entries (16 models + human) with win-rate vs the human expert,
    broken down by sector (9) and occupation (44). No per-instance.

Neither source publishes per-instance pass/fail. The closest public
per-task proxy is OpenAI's per-occupation win rates (44 buckets of 5 tasks).

Sources used end-to-end:

  1. https://artificialanalysis.ai/evaluations/gdpval-aa
     Next.js app-router page. Model data is embedded in `__next_f` JSON
     chunks as `defaultData` — one entry per model with `safeGdpval`
     (ELO/CIs/matches) and `gdpval_token_use`. We keep every entry that
     has a `safeGdpval.elo` value.
  2. https://evals.openai.com/gdpval/leaderboard
     SPA bundled by Vite. The landing HTML points to
     `/assets/index-<hash>.js` which inlines `data/gdpval_leaderboard/*`
     as JS object literals. We extract:
       - `totals`: overall win-rate + win-or-tie-rate per model vs human
       - `by_sector`: per-model per-sector rates (9 sectors × 17 models)
       - `by_occupation`: per-model per-occupation rates (44 × 17)
  3. https://datasets-server.huggingface.co/rows?dataset=openai/gdpval
     Canonical 220-task universe (task_id, sector, occupation).

Outputs (all under this directory):
  leaderboard.json           # AA full 336-row leaderboard
  rows/<slug>.json           # AA per-model detail (ELO, CIs, token use)
  rows_index.json            # AA sorted summary (best ELO first)
  tasks.json                 # 220-task universe from HF
  openai_grader/
    overall.json             # OpenAI auto-grader totals (17 models)
    by_sector.json           # per-(model,sector) win rates
    by_occupation.json       # per-(model,occupation) win rates
  openai_grader_rows/<slug>.json
                             # one file per OpenAI grader model, joining
                             # overall + per-sector + per-occupation
  per_task_matrix.json       # {task_id: {...}} — AA has no per-instance
                             # data, so each task inherits the model's
                             # per-occupation OpenAI win rate (best
                             # available public proxy). Use with care.

Usage:
  python refresh.py                  # full refresh
  python refresh.py --skip-aa        # reuse existing leaderboard.json
  python refresh.py --skip-openai    # reuse existing openai_grader/*.json
  python refresh.py --skip-tasks     # reuse existing tasks.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

AA_PAGE_URL = "https://artificialanalysis.ai/evaluations/gdpval-aa"
OAI_PAGE_URL = "https://evals.openai.com/gdpval/leaderboard"
OAI_BASE = "https://evals.openai.com"
HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=openai%2Fgdpval&config=default&split=train"
    "&offset={offset}&length={length}"
)
HF_TOTAL_TASKS = 220


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "gdpval-aa-leaderboard-refresh/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last}")


def fetch_json(url: str) -> object:
    return json.loads(fetch(url))


# --------------------------------------------------------------------------- #
# JS / Next.js payload utilities
# --------------------------------------------------------------------------- #
def _find_balanced(js: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index (inclusive) of the matching closer for the literal opening at `start`."""
    depth = 0
    i = start
    in_str = False
    esc = False
    qc = ""
    while i < len(js):
        c = js[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == qc:
                in_str = False
        else:
            if c in "\"'`":
                in_str = True
                qc = c
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError("unbalanced literal")


def js_literal_to_json(s: str) -> str:
    """Loosely convert a JS object/array literal to JSON.

    Handles the bundle shape we care about: unquoted identifier keys and
    bare leading-decimal numbers (.5 → 0.5, -.5 → -0.5). Respects
    quoted strings so we don't corrupt values. Good enough for the
    small, regular literals the evals.openai.com bundle ships.
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            j = i + 1
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == c:
                    break
                j += 1
            # Replace single quotes with double quotes for JSON
            lit = s[i : j + 1]
            if c == "'":
                inner = lit[1:-1].replace('"', '\\"')
                lit = '"' + inner + '"'
            out.append(lit)
            i = j + 1
            continue
        # Identifier key: {foo:  or ,foo:  (possibly with whitespace)
        if c in "{," and i + 1 < n:
            out.append(c)
            j = i + 1
            # skip whitespace
            while j < n and s[j] in " \t\n\r":
                j += 1
            start_id = j
            while j < n and (s[j].isalnum() or s[j] in "_$"):
                j += 1
            end_id = j
            # skip whitespace
            while j < n and s[j] in " \t\n\r":
                j += 1
            if end_id > start_id and j < n and s[j] == ":":
                ident = s[start_id:end_id]
                out.append(f'"{ident}"')
                out.append(":")
                i = j + 1
                continue
            i += 1
            continue
        # Leading-decimal number: `:  .5`  or `[.5,` or `,.5`
        if c == "." and i + 1 < n and s[i + 1].isdigit():
            # Prev non-space char determines whether this is a number start
            k = len(out) - 1
            while k >= 0 and out[k] and out[k][-1] in " \t\n\r":
                k -= 1
            prev = out[k][-1] if k >= 0 and out[k] else ""
            if prev in ":,[":
                out.append("0.")
                i += 1
                continue
        # Leading-decimal negative: `-.5`
        if c == "-" and i + 1 < n and s[i + 1] == "." and i + 2 < n and s[i + 2].isdigit():
            k = len(out) - 1
            while k >= 0 and out[k] and out[k][-1] in " \t\n\r":
                k -= 1
            prev = out[k][-1] if k >= 0 and out[k] else ""
            if prev in ":,[":
                out.append("-0.")
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# Step 1: Artificial Analysis (AA) leaderboard
# --------------------------------------------------------------------------- #
def scrape_aa_leaderboard() -> list[dict]:
    """Extract the 336-row model leaderboard from the AA page."""
    html = fetch(AA_PAGE_URL)
    pushes = re.findall(r"self\.__next_f\.push\((\[[^\n]*?\])\)", html)
    # Find the chunk that holds `defaultData` of model-sized entries with `safeGdpval`
    for raw in pushes:
        if '"defaultData"' not in raw and "defaultData" not in raw:
            continue
        if "safeGdpval" not in raw:
            continue
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not (isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], str)):
            continue
        payload = arr[1]
        if ":" not in payload:
            continue
        body = payload[payload.index(":") + 1 :].rstrip("\n")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        # Walk: find the first list of dicts with `safeGdpval` entries
        stack: list[object] = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list) and cur and isinstance(cur[0], dict):
                sample = cur[0]
                if isinstance(sample.get("safeGdpval"), dict) and "elo" in sample["safeGdpval"]:
                    return cur
            if isinstance(cur, dict):
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    raise RuntimeError("could not locate AA `defaultData` in Next.js payload")


def _slugify(name: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower() or "model"
    slug = base
    i = 2
    while slug in used:
        slug = f"{base}_{i}"
        i += 1
    used.add(slug)
    return slug


def normalize_aa_entries(entries: list[dict]) -> list[dict]:
    used: set[str] = set()
    rows: list[dict] = []
    for e in entries:
        safe = e.get("safeGdpval") or {}
        elo = safe.get("elo")
        if not isinstance(elo, (int, float)):
            continue  # model ranked but no valid ELO — skip
        slug_base = e.get("slug") or e.get("id") or (e.get("name") or "model")
        slug = _slugify(str(slug_base), used)
        creator = e.get("model_creators") or {}
        rows.append(
            {
                "slug": slug,
                "model_id": e.get("id"),
                "model_slug": e.get("slug"),
                "name": e.get("name"),
                "gdpval_name": e.get("gdpvalName"),
                "short_name": e.get("short_name") or e.get("shortName"),
                "creator": {
                    "name": creator.get("name"),
                    "slug": creator.get("slug"),
                    "country": creator.get("country"),
                    "logo": creator.get("logo_url") or creator.get("logo"),
                },
                "release_date": e.get("release_date"),
                "is_open_weights": e.get("is_open_weights"),
                "reasoning_model": e.get("reasoning_model"),
                "deprecated": e.get("deprecated"),
                "safe_gdpval": {
                    "elo": safe.get("elo"),
                    "lower_95ci": safe.get("lower95ci"),
                    "upper_95ci": safe.get("upper95ci"),
                    "n_matches": safe.get("nMatches"),
                    "avg_turns": safe.get("avgTurns")
                    if isinstance(safe.get("avgTurns"), (int, float))
                    else None,
                },
                "gdpval_breakdown": e.get("gdpval_breakdown") or {},
                "gdpval_token_use": e.get("gdpval_token_use"),
                "intelligence_index": e.get("intelligence_index"),
                "agentic_index": e.get("agentic_index"),
                "price_1m_input_tokens": e.get("price_1m_input_tokens"),
                "price_1m_output_tokens": e.get("price_1m_output_tokens"),
            }
        )
    rows.sort(key=lambda r: -(r["safe_gdpval"]["elo"] or 0))
    return rows


def write_aa_outputs(rows: list[dict]) -> None:
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "source_url": AA_PAGE_URL,
                "benchmark": "gdpval",
                "variant": "aa",
                "grader": "artificial_analysis_stirrup",
                "num_entries": len(rows),
                "schema": {
                    "slug": "Row slug (derived from model_slug)",
                    "name": "Display name on AA page",
                    "gdpval_name": "Full GDPval row label (reasoning config)",
                    "creator": "Model creator (lab)",
                    "safe_gdpval": "ELO + 95% CI + n_matches + avg_turns "
                    "(the officially published cells)",
                    "gdpval_breakdown": "Raw breakdown dict from AA (same fields, "
                    "plus last_updated timestamp)",
                    "gdpval_token_use": "input/output/reasoning/answer tokens",
                },
                "entries": rows,
            },
            indent=2,
        )
    )
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for r in rows:
        (rows_dir / f"{r['slug']}.json").write_text(json.dumps(r, indent=2))
    # Sorted summary index
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(rows),
                "rows": [
                    {
                        "slug": r["slug"],
                        "name": r["name"],
                        "gdpval_name": r["gdpval_name"],
                        "creator": (r["creator"] or {}).get("name"),
                        "elo": r["safe_gdpval"]["elo"],
                        "lower_95ci": r["safe_gdpval"]["lower_95ci"],
                        "upper_95ci": r["safe_gdpval"]["upper_95ci"],
                        "n_matches": r["safe_gdpval"]["n_matches"],
                        "avg_turns": r["safe_gdpval"]["avg_turns"],
                        "last_updated": (r.get("gdpval_breakdown") or {}).get("last_updated"),
                    }
                    for r in rows
                ],
            },
            indent=2,
        )
    )


# --------------------------------------------------------------------------- #
# Step 2: OpenAI auto-grader leaderboard (evals.openai.com)
# --------------------------------------------------------------------------- #
def _find_bundle_url(landing_html: str) -> str:
    m = re.search(r'"(/assets/index-[A-Za-z0-9_-]+\.js)"', landing_html)
    if not m:
        raise RuntimeError("evals.openai.com bundle URL not found")
    return OAI_BASE + m.group(1)


def _extract_array_after(js: str, start: int) -> tuple[list[dict], int]:
    """Parse the JS array literal starting at `js[start]='['` → list of dicts."""
    if js[start] != "[":
        raise ValueError(f"expected '[' at {start}")
    end = _find_balanced(js, start, "[", "]")
    lit = js[start : end + 1]
    return json.loads(js_literal_to_json(lit)), end


def _iter_array_literals(js: str, must_have_keys: tuple[str, ...]):
    """Yield (list_of_dicts, abs_start, abs_end) for every top-level array whose
    first object element contains all `must_have_keys`.

    Cheap pre-filter: search for '[{' then verify the first object has the keys.
    """
    for m in re.finditer(r"\[\{", js):
        start = m.start()
        # Avoid re-parsing arrays we've already yielded.
        try:
            end = _find_balanced(js, start, "[", "]")
        except ValueError:
            continue
        snippet = js[start : min(end + 1, start + 400)]
        if not all(k + ":" in snippet for k in must_have_keys):
            continue
        try:
            data = json.loads(js_literal_to_json(js[start : end + 1]))
        except Exception:
            continue
        if not (isinstance(data, list) and data and isinstance(data[0], dict)):
            continue
        if not all(k in data[0] for k in must_have_keys):
            continue
        yield data, start, end


def _largest_by_content(js: str, keys: tuple[str, ...]) -> list[dict]:
    """Pick the largest array literal whose elements contain exactly `keys`.

    Used to disambiguate the per-model arrays from combined arrays
    (e.g., a `concat`-assembled big array that flattens all models).
    """
    best: list[dict] = []
    best_span = 0
    for data, s, e in _iter_array_literals(js, keys):
        # Filter to arrays where *every* element matches the key shape
        if not all(isinstance(x, dict) and all(k in x for k in keys) for x in data):
            continue
        span = e - s
        if span > best_span:
            best_span = span
            best = data
    return best


def scrape_openai_grader() -> dict:
    """Extract totals + by_sector + by_occupation tables from the SPA bundle."""
    landing = fetch(OAI_PAGE_URL)
    bundle_url = _find_bundle_url(landing)
    js = fetch(bundle_url)

    # Totals: [{model, win_rate, win_or_tie_rate}]  (exactly 3 keys on each entry)
    totals: list[dict] = []
    for data, _s, _e in _iter_array_literals(js, ("model", "win_rate", "win_or_tie_rate")):
        # Reject entries that also carry sector/occupation keys
        if any("sector" in x or "occupation" in x for x in data):
            continue
        if len(data) < len(totals):
            continue
        totals = data

    # By sector: [{model, sector, win_rate, win_or_tie_rate}]  — concat of per-model arrays
    by_sector_flat: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for data, _s, _e in _iter_array_literals(
        js, ("model", "sector", "win_rate", "win_or_tie_rate")
    ):
        if any("occupation" in x for x in data):
            continue
        for row in data:
            key = (row["model"], row["sector"])
            if key in seen:
                continue
            seen.add(key)
            by_sector_flat.append(row)

    # By occupation: [{model, sector, occupation, win_rate, win_or_tie_rate}]
    by_occ_flat: list[dict] = []
    seen2: set[tuple[str, str, str]] = set()
    for data, _s, _e in _iter_array_literals(
        js, ("model", "sector", "occupation", "win_rate", "win_or_tie_rate")
    ):
        for row in data:
            key = (row["model"], row["sector"], row["occupation"])
            if key in seen2:
                continue
            seen2.add(key)
            by_occ_flat.append(row)

    return {
        "source_bundle": bundle_url,
        "totals": totals,
        "by_sector": by_sector_flat,
        "by_occupation": by_occ_flat,
    }


def write_openai_outputs(raw: dict) -> None:
    out_dir = HERE / "openai_grader"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "overall.json").write_text(
        json.dumps(
            {
                "source_url": OAI_PAGE_URL,
                "source_bundle": raw["source_bundle"],
                "num_models": len(raw["totals"]),
                "schema": {
                    "model": "OpenAI grader model id (not AA slug)",
                    "win_rate": "Fraction of pairwise matches where model beat human expert",
                    "win_or_tie_rate": "Fraction of wins+ties",
                },
                "entries": sorted(
                    raw["totals"], key=lambda r: -(r.get("win_or_tie_rate") or 0)
                ),
            },
            indent=2,
        )
    )
    (out_dir / "by_sector.json").write_text(
        json.dumps(
            {
                "source_url": OAI_PAGE_URL,
                "source_bundle": raw["source_bundle"],
                "num_rows": len(raw["by_sector"]),
                "entries": raw["by_sector"],
            },
            indent=2,
        )
    )
    (out_dir / "by_occupation.json").write_text(
        json.dumps(
            {
                "source_url": OAI_PAGE_URL,
                "source_bundle": raw["source_bundle"],
                "num_rows": len(raw["by_occupation"]),
                "entries": raw["by_occupation"],
            },
            indent=2,
        )
    )

    # Per-model detail files
    rows_dir = HERE / "openai_grader_rows"
    rows_dir.mkdir(exist_ok=True)
    # Clear stale files
    for existing in rows_dir.glob("*.json"):
        existing.unlink()

    per_model_totals = {r["model"]: r for r in raw["totals"]}
    per_model_sector: dict[str, list[dict]] = defaultdict(list)
    for row in raw["by_sector"]:
        per_model_sector[row["model"]].append(
            {
                "sector": row["sector"],
                "win_rate": row["win_rate"],
                "win_or_tie_rate": row["win_or_tie_rate"],
            }
        )
    per_model_occ: dict[str, list[dict]] = defaultdict(list)
    for row in raw["by_occupation"]:
        per_model_occ[row["model"]].append(
            {
                "sector": row["sector"],
                "occupation": row["occupation"],
                "win_rate": row["win_rate"],
                "win_or_tie_rate": row["win_or_tie_rate"],
            }
        )

    models = sorted(
        set(per_model_totals) | set(per_model_sector) | set(per_model_occ)
    )
    for m in models:
        entry = {
            "model": m,
            "totals": per_model_totals.get(m),
            "by_sector": sorted(per_model_sector.get(m, []), key=lambda r: r["sector"]),
            "by_occupation": sorted(
                per_model_occ.get(m, []),
                key=lambda r: (r["sector"], r["occupation"]),
            ),
        }
        (rows_dir / f"{m}.json").write_text(json.dumps(entry, indent=2))


# --------------------------------------------------------------------------- #
# Step 3: task universe from HuggingFace
# --------------------------------------------------------------------------- #
def scrape_tasks() -> list[dict]:
    tasks: list[dict] = []
    offset = 0
    page = 100
    while offset < HF_TOTAL_TASKS:
        url = HF_ROWS_URL.format(offset=offset, length=page)
        data = fetch_json(url)
        rows = data.get("rows", []) if isinstance(data, dict) else []
        if not rows:
            break
        for r in rows:
            row = r.get("row", {})
            tid = row.get("task_id")
            if not tid:
                continue
            tasks.append(
                {
                    "task_id": tid,
                    "sector": row.get("sector"),
                    "occupation": row.get("occupation"),
                }
            )
        offset += len(rows)
    # De-dup preserving order
    seen: set[str] = set()
    out: list[dict] = []
    for t in tasks:
        if t["task_id"] in seen:
            continue
        seen.add(t["task_id"])
        out.append(t)
    return out


def write_tasks(tasks: list[dict]) -> None:
    (HERE / "tasks.json").write_text(
        json.dumps(
            {
                "source": "https://huggingface.co/datasets/openai/gdpval",
                "num_tasks": len(tasks),
                "num_sectors": len({t["sector"] for t in tasks}),
                "num_occupations": len({t["occupation"] for t in tasks}),
                "tasks": tasks,
            },
            indent=2,
        )
    )


# --------------------------------------------------------------------------- #
# Step 4: per_task_matrix.json (best-effort proxy)
# --------------------------------------------------------------------------- #
def build_per_task_matrix(tasks: list[dict], oai: dict, aa_rows: list[dict]) -> dict:
    """Stamp the per-occupation OpenAI win rates onto every task in that occupation.

    AA publishes no per-instance data — this gives at most 44 distinct values
    across the 220 tasks for OpenAI-grader models, and null for AA-only rows.
    """
    per_model_occ: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in oai.get("by_occupation", []):
        per_model_occ[row["model"]][row["occupation"]] = {
            "win_rate": row["win_rate"],
            "win_or_tie_rate": row["win_or_tie_rate"],
        }

    aa_by_slug = {r["slug"]: r for r in aa_rows}

    matrix: dict[str, dict] = {}
    for t in tasks:
        cell_openai = {}
        for m, by_occ in per_model_occ.items():
            if t["occupation"] in by_occ:
                cell_openai[m] = dict(by_occ[t["occupation"]])
        matrix[t["task_id"]] = {
            "sector": t["sector"],
            "occupation": t["occupation"],
            "openai_grader_per_occupation_proxy": cell_openai,
        }
    return {
        "tasks": [t["task_id"] for t in tasks],
        "num_tasks": len(tasks),
        "num_aa_rows": len(aa_rows),
        "note": (
            "AA publishes no per-instance pass/fail; aggregate ELO only. "
            "Each task_id carries OpenAI-grader per-occupation win rates "
            "(all tasks in the same occupation share a value). Use as a "
            "proxy — not ground truth."
        ),
        "matrix": matrix,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-aa", action="store_true", help="Reuse existing leaderboard.json")
    ap.add_argument("--skip-openai", action="store_true", help="Reuse existing openai_grader/*.json")
    ap.add_argument("--skip-tasks", action="store_true", help="Reuse existing tasks.json")
    args = ap.parse_args()

    print("=" * 72)
    print("GDPval-AA leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    # --- Step 1: AA ---
    lb_path = HERE / "leaderboard.json"
    if args.skip_aa and lb_path.exists():
        print("[1/4] skip AA scrape — reusing leaderboard.json")
        aa_rows = _load_json(lb_path)["entries"]
    else:
        print(f"[1/4] scraping AA leaderboard: {AA_PAGE_URL}")
        raw = scrape_aa_leaderboard()
        aa_rows = normalize_aa_entries(raw)
        print(f"  parsed {len(raw)} AA entries → {len(aa_rows)} rows with ELO")
        write_aa_outputs(aa_rows)

    # --- Step 2: OpenAI auto-grader ---
    oai_dir = HERE / "openai_grader"
    oai_cached = (
        (oai_dir / "overall.json").exists()
        and (oai_dir / "by_sector.json").exists()
        and (oai_dir / "by_occupation.json").exists()
    )
    if args.skip_openai and oai_cached:
        print("[2/4] skip OpenAI scrape — reusing openai_grader/*.json")
        oai = {
            "source_bundle": _load_json(oai_dir / "overall.json").get("source_bundle"),
            "totals": _load_json(oai_dir / "overall.json")["entries"],
            "by_sector": _load_json(oai_dir / "by_sector.json")["entries"],
            "by_occupation": _load_json(oai_dir / "by_occupation.json")["entries"],
        }
    else:
        print(f"[2/4] scraping OpenAI grader bundle: {OAI_PAGE_URL}")
        oai = scrape_openai_grader()
        print(
            f"  totals={len(oai['totals'])}  by_sector={len(oai['by_sector'])}  "
            f"by_occupation={len(oai['by_occupation'])}"
        )
        write_openai_outputs(oai)

    # --- Step 3: task universe ---
    tasks_path = HERE / "tasks.json"
    if args.skip_tasks and tasks_path.exists():
        print("[3/4] skip task universe — reusing tasks.json")
        tasks = _load_json(tasks_path)["tasks"]
    else:
        print("[3/4] fetching HF task universe")
        tasks = scrape_tasks()
        print(f"  got {len(tasks)} tasks")
        write_tasks(tasks)

    # --- Step 4: per_task_matrix (best-effort) ---
    print("[4/4] building per_task_matrix.json")
    matrix = build_per_task_matrix(tasks, oai, aa_rows)
    (HERE / "per_task_matrix.json").write_text(json.dumps(matrix, indent=2))

    print()
    print("done. outputs:")
    for f in (
        "leaderboard.json",
        "rows_index.json",
        "tasks.json",
        "per_task_matrix.json",
        "openai_grader/overall.json",
        "openai_grader/by_sector.json",
        "openai_grader/by_occupation.json",
    ):
        p = HERE / f
        if p.exists():
            print(f"  {f}  ({p.stat().st_size:,} bytes)")
    for sub in ("rows", "openai_grader_rows"):
        d = HERE / sub
        if d.exists():
            n = len(list(d.glob("*.json")))
            print(f"  {sub}/  ({n} files)")


if __name__ == "__main__":
    main()
