#!/usr/bin/env python3
"""Refresh the OmniDocBench leaderboard snapshot.

OmniDocBench (arXiv:2412.07626, CVPR 2025) is a PDF-document-parsing
benchmark from OpenDataLab. It scores a model's Markdown extraction of
1,651 annotated pages (v1.6 full set; 1,355 page v1.5 subset). Four
metric families combine into a single `Overall`:

    Overall = ((1 - TextEditDistance) * 100 + TableTEDS + FormulaCDM) / 3

Leaderboard columns (same for both tracks):

    Overall ↑            — headline score, 0–100
    Text Edit ↓          — normalized edit distance, 0–1 (lower = better)
    Formula CDM ↑        — formula recognition, 0–100
    Table TEDS ↑         — table structure + text, 0–100
    Table TEDS-S ↑       — table structure only, 0–100
    Read Order Edit ↓    — reading-order edit distance, 0–1

Two public leaderboards cover OmniDocBench. We pull from both:

  1. Official GitHub README (OpenDataLab/OmniDocBench) — v1.6_full,
     28 entries. Evaluated on the full 1,651-page set. Mix of open-weight
     specialized VLMs, general-purpose VLMs, and pipeline tools.

  2. idp-leaderboard.org (Nanonets) — v1.5, 29 entries. Evaluated on
     the 1,355-page v1.5 subset. Leans toward frontier general VLMs
     (Claude/GPT/Gemini/Qwen families) that the official leaderboard
     does NOT re-evaluate on v1.6.

The two tracks aren't directly comparable (different page set, some
metric definitions evolved between v1.5 and v1.6). We keep them as
separate slugs (`__v1_6` vs `__v1_5` suffixes) so rankings stay within a
track.

Per-instance availability:

  Neither leaderboard publishes per-page predictions for any model. The
  official repo's `result/` directory contains per-page edit-distance
  values, but only for the 18-page `demo_data/` toy set, from an
  unlabeled example run — not from any leaderboard entry. Every row in
  this snapshot lives in `rows_index.json` → `missing_detail`, and
  `per_task_matrix.json` carries the 1,651-page universe with
  page-level metadata (document type, language, layout) but zero
  prediction columns.

Outputs (all under this directory):
  leaderboard.json         # merged entries from both tracks + schema
  rows/<slug>.json         # per-entry detail (empty `tasks`)
  rows_index.json          # sorted summary + `missing_detail`
  per_task_matrix.json     # 1,651-task universe, empty matrix
  cache/                   # raw downloaded HTML/JSON so re-runs skip HTTP

Usage:
  python refresh.py                    # full refresh (~2 min, 40MB download)
  python refresh.py --skip-scrape      # reuse cached README + IDP html
  python refresh.py --skip-annotations # reuse cached OmniDocBench.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

GITHUB_README_URL = (
    "https://raw.githubusercontent.com/opendatalab/OmniDocBench/main/README.md"
)
GITHUB_REPO_URL = "https://github.com/opendatalab/OmniDocBench"
IDP_LEADERBOARD_URL = "https://www.idp-leaderboard.org/benchmarks/omnidocbench"
HF_DATASET_URL = "https://huggingface.co/datasets/opendatalab/OmniDocBench"
ANNOTATIONS_URL = (
    "https://huggingface.co/datasets/opendatalab/OmniDocBench/"
    "resolve/main/OmniDocBench.json"
)
PAPER_URL = "https://arxiv.org/abs/2412.07626"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def fetch(url: str, retries: int = 4) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "omnidocbench-leaderboard-refresh/0.1"}
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last_err}")


def fetch_text(url: str, cache_name: str, refresh: bool) -> str:
    CACHE.mkdir(exist_ok=True)
    p = CACHE / cache_name
    if not refresh and p.exists():
        return p.read_text(encoding="utf-8")
    body = fetch(url).decode("utf-8", errors="replace")
    p.write_text(body, encoding="utf-8")
    return body


def fetch_bytes(url: str, cache_name: str, refresh: bool) -> bytes:
    CACHE.mkdir(exist_ok=True)
    p = CACHE / cache_name
    if not refresh and p.exists():
        return p.read_bytes()
    body = fetch(url)
    p.write_bytes(body)
    return body


# --------------------------------------------------------------------------- #
# GitHub README leaderboard (v1.6_full, 28 entries)
# --------------------------------------------------------------------------- #
# The leaderboard is an HTML table embedded in README.md, between
# `caption>Comprehensive evaluation of document parsing on OmniDocBench`
# and the next `</table>`. Rows have 9 <td>s:
#   Methods | Model Type | Size | Overall | TextEdit | FormulaCDM | TableTEDS | TableTEDS-S | ReadOrderEdit
# Scores may be wrapped in <strong> / <ins> for best / second-best.
_CAPTION_RE = re.compile(
    r"Comprehensive evaluation of document parsing on OmniDocBench \(v1\.6_full\)"
)
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)


def _strip_html(s: str) -> str:
    # Remove <strong>/<ins>/<a>/<br> and similar, collapse whitespace.
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _as_float(s: str) -> float | None:
    s = s.strip()
    if not s or s in {"-", "—", "–", "N/A", "n/a"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def scrape_github_readme(readme_md: str) -> list[dict]:
    m = _CAPTION_RE.search(readme_md)
    if not m:
        raise RuntimeError("v1.6_full caption not found in README.md")
    tail = readme_md[m.start():]
    # slice off the end of this table
    end = tail.find("</table>")
    if end == -1:
        raise RuntimeError("unterminated <table> in README")
    table = tail[: end + len("</table>")]

    rows: list[dict] = []
    for tr in _TR_RE.findall(table):
        tds = _TD_RE.findall(tr)
        if len(tds) < 9:
            continue
        cells = [_strip_html(t) for t in tds]
        # Skip header duplicates (rarely present)
        if cells[0].lower().startswith("model"):
            continue
        name, model_type, size = cells[0], cells[1], cells[2]
        if not name or not model_type:
            continue
        overall = _as_float(cells[3])
        text_edit = _as_float(cells[4])
        formula_cdm = _as_float(cells[5])
        table_teds = _as_float(cells[6])
        table_teds_s = _as_float(cells[7])
        read_order = _as_float(cells[8])
        # Skip malformed rows (no Overall score).
        if overall is None:
            continue
        rows.append(
            {
                "track": "v1.6_full",
                "name": name,
                "model_type": model_type,  # Specialized VLMs | General VLMs | Pipeline Tools
                "size": size if size and size != "-" else None,
                "overall": overall,
                "text_edit": text_edit,
                "formula_cdm": formula_cdm,
                "table_teds": table_teds,
                "table_teds_s": table_teds_s,
                "reading_order_edit": read_order,
                "source": "OpenDataLab/OmniDocBench README",
                "source_url": GITHUB_REPO_URL,
                "num_pages": 1651,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# IDP leaderboard (v1.5, 29 entries)
# --------------------------------------------------------------------------- #
# idp-leaderboard.org serves a Next.js React Server Component payload; the
# models array is embedded as escaped JSON inside the HTML. We locate the
# first `{"model_name":"Gemini-3-Flash"...` occurrence, scan back to the
# enclosing `[`, then walk bracket depth (tracking escaped-quote strings)
# to find the matching `]`.
_IDP_MARKER = 'Gemini-3-Flash\\",\\"slug'


def _extract_idp_models_json(html_str: str) -> str:
    idx = html_str.find(_IDP_MARKER)
    if idx < 0:
        raise RuntimeError("IDP models array marker not found")
    start = html_str.rfind("[", 0, idx)
    if start < 0:
        raise RuntimeError("IDP models array opening bracket not found")
    depth = 0
    in_str = False
    i = start
    while i < len(html_str):
        c = html_str[i]
        if c == "\\" and i + 1 < len(html_str) and html_str[i + 1] == '"':
            in_str = not in_str
            i += 2
            continue
        if not in_str:
            if c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    return html_str[start : i + 1]
        i += 1
    raise RuntimeError("IDP models array unterminated")


def _unescape(s: str) -> str:
    return (
        s.replace("\\\\", "\x00")  # preserve literal backslashes
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\/", "/")
        .replace("\x00", "\\")
    )


def scrape_idp_leaderboard(idp_html: str) -> list[dict]:
    chunk = _extract_idp_models_json(idp_html)
    data = json.loads(_unescape(chunk))
    rows: list[dict] = []
    for m in data:
        s = m.get("scores", {}).get("omnidocbench") or {}
        overall = s.get("overall")
        if overall is None:
            continue
        rows.append(
            {
                "track": "v1.5",
                "name": m.get("model_name"),
                "model_type": m.get("type"),  # "closed" / "open" etc.
                "size": m.get("size"),
                "company": m.get("company"),
                "release_date": m.get("release_date"),
                "context_window": m.get("context_window"),
                "cost_per_1k": m.get("cost_per_1k"),
                "overall": overall,
                "text_edit": s.get("text_edit"),
                "formula_cdm": s.get("formula_cdm"),
                "table_teds": s.get("table_teds"),
                "table_teds_s": s.get("table_teds_s"),
                "reading_order_edit": s.get("reading_order_edit"),
                "source": "idp-leaderboard.org (Nanonets)",
                "source_url": IDP_LEADERBOARD_URL,
                "num_pages": 1355,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Task universe (OmniDocBench.json — 1,651 pages with attributes)
# --------------------------------------------------------------------------- #
def build_task_universe(annotations_bytes: bytes) -> tuple[list[dict], dict]:
    data = json.loads(annotations_bytes.decode("utf-8"))
    tasks: list[dict] = []
    ds_counter: Counter[str] = Counter()
    lang_counter: Counter[str] = Counter()
    layout_counter: Counter[str] = Counter()
    subset_counter: Counter[str] = Counter()
    special_counter: Counter[str] = Counter()
    for r in data:
        pi = r.get("page_info") or {}
        attr = pi.get("page_attribute") or {}
        ds = attr.get("data_source")
        lang = attr.get("language")
        layout = attr.get("layout")
        subset = attr.get("subset")
        special = attr.get("special_issue") or []
        ds_counter[ds or "unknown"] += 1
        lang_counter[lang or "unknown"] += 1
        layout_counter[layout or "unknown"] += 1
        subset_counter[subset or "unknown"] += 1
        for s in special:
            if s:
                special_counter[s] += 1
        tasks.append(
            {
                "task_id": pi.get("image_path"),
                "page_no": pi.get("page_no"),
                "height": pi.get("height"),
                "width": pi.get("width"),
                "data_source": ds,
                "language": lang,
                "layout": layout,
                "subset": subset,
                "special_issue": list(special),
            }
        )
    stats = {
        "num_pages": len(tasks),
        "data_source_counts": dict(ds_counter),
        "language_counts": dict(lang_counter),
        "layout_counts": dict(layout_counter),
        "subset_counts": dict(subset_counter),
        "special_issue_top10": dict(special_counter.most_common(10)),
    }
    return tasks, stats


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def slug_from_name(name: str, track: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    suffix = "__v1_6" if track == "v1.6_full" else "__v1_5"
    return f"{(s or 'row')}{suffix}"


SCHEMA = {
    "track": "'v1.6_full' (1,651 pages, official README) or 'v1.5' (1,355 pages, IDP)",
    "name": "Model name as shown on the source leaderboard",
    "model_type": "Specialized VLMs | General VLMs | Pipeline Tools (v1.6) or 'closed'/'open' (v1.5)",
    "size": "Parameter count (e.g. '1.2B', '235B') or null if unreported / closed API",
    "overall": "Headline score: ((1 - TextEdit) * 100 + TableTEDS + FormulaCDM) / 3, 0–100, higher better",
    "text_edit": "Text edit distance, 0–1, LOWER is better",
    "formula_cdm": "Formula CDM score, 0–100, higher better",
    "table_teds": "Table TEDS (structure + text), 0–100, higher better",
    "table_teds_s": "Table TEDS-S (structure only), 0–100, higher better",
    "reading_order_edit": "Reading order edit distance, 0–1, LOWER is better",
    "source": "Which leaderboard this row came from",
    "source_url": "URL of the source leaderboard",
    "num_pages": "Number of pages evaluated on this track (1651 for v1.6_full, 1355 for v1.5)",
    "company": "Provider name (v1.5 track only)",
    "release_date": "Model release date (v1.5 track only)",
    "context_window": "Token context window (v1.5 closed models only)",
    "cost_per_1k": "Input/output cost per 1k tokens (v1.5 closed models only)",
}


def write_leaderboard(
    entries: list[dict], task_stats: dict, refresh_meta: dict
) -> None:
    ordered = sorted(
        entries,
        key=lambda r: (r["track"], -(r.get("overall") or -1)),
    )
    (HERE / "leaderboard.json").write_text(
        json.dumps(
            {
                "benchmark": "omnidocbench",
                "paper": PAPER_URL,
                "project_page": GITHUB_REPO_URL,
                "dataset": HF_DATASET_URL,
                "sources": [
                    {
                        "track": "v1.6_full",
                        "url": GITHUB_REPO_URL,
                        "num_pages": 1651,
                        "note": (
                            "Official README leaderboard. Evaluated on "
                            "the full v1.6 set (v1.5 + 296 hard pages: "
                            "100 equation_hard + 99 layout_hard + 97 "
                            "table_hard)."
                        ),
                    },
                    {
                        "track": "v1.5",
                        "url": IDP_LEADERBOARD_URL,
                        "num_pages": 1355,
                        "note": (
                            "Third-party leaderboard (Nanonets). Evaluated "
                            "on the 1,355-page v1.5 subset. Focus on "
                            "frontier closed-weight VLMs + Qwen / DeepSeek."
                        ),
                    },
                ],
                "scoring": (
                    "Overall = ((1 - TextEditDistance) * 100 + "
                    "TableTEDS + FormulaCDM) / 3"
                ),
                "columns": [
                    "overall ↑",
                    "text_edit ↓",
                    "formula_cdm ↑",
                    "table_teds ↑",
                    "table_teds_s ↑",
                    "reading_order_edit ↓",
                ],
                "track_comparability_note": (
                    "v1.6_full (1,651 pages) and v1.5 (1,355 pages) are "
                    "NOT directly comparable — different page set, and the "
                    "Overall metric denominator changed between versions. "
                    "Rank within a track, not across."
                ),
                "task_universe": task_stats,
                "refresh": refresh_meta,
                "num_entries": len(entries),
                "schema": SCHEMA,
                "entries": ordered,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def write_rows(entries: list[dict]) -> None:
    rows_dir = HERE / "rows"
    rows_dir.mkdir(exist_ok=True)
    for old in rows_dir.glob("*.json"):
        old.unlink()
    seen: dict[str, int] = {}
    for r in entries:
        slug = slug_from_name(r["name"], r["track"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}__{seen[slug]}"
        else:
            seen[slug] = 1
        (rows_dir / f"{slug}.json").write_text(
            json.dumps(
                {
                    "slug": slug,
                    **r,
                    "num_tasks": None,
                    "total_trials": None,
                    "total_successes": None,
                    "tasks": [],
                },
                indent=2,
                ensure_ascii=False,
            )
        )


def write_rows_index(entries: list[dict]) -> None:
    seen: dict[str, int] = {}
    missing: list[dict] = []
    for r in entries:
        slug = slug_from_name(r["name"], r["track"])
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}__{seen[slug]}"
        else:
            seen[slug] = 1
        overall = r.get("overall")
        missing.append(
            {
                "slug": slug,
                "name": r["name"],
                "track": r["track"],
                "model_type": r.get("model_type"),
                "size": r.get("size"),
                "overall": overall,
                "accuracy": (overall / 100.0) if overall is not None else None,
                "text_edit": r.get("text_edit"),
                "formula_cdm": r.get("formula_cdm"),
                "table_teds": r.get("table_teds"),
                "table_teds_s": r.get("table_teds_s"),
                "reading_order_edit": r.get("reading_order_edit"),
                "num_tasks": None,
                "total_trials": None,
                "recomputed_pass_rate": None,
            }
        )
    missing.sort(
        key=lambda r: (
            # Sort by track so v1.6_full comes first, then by overall desc.
            0 if r["track"] == "v1.6_full" else 1,
            -(r["overall"] or 0),
        )
    )
    (HERE / "rows_index.json").write_text(
        json.dumps(
            {
                "num_rows": len(entries),
                "num_with_detail": 0,
                "num_missing_detail": len(entries),
                "note": (
                    "OmniDocBench publishes no per-page predictions for "
                    "any leaderboard entry. Every row is aggregate-only "
                    "and lands in `missing_detail` here. The official "
                    "repo's result/ directory contains per-page metric "
                    "values, but only for an 18-page demo_data toy set, "
                    "from an unlabeled example run — not a leaderboard "
                    "entry. To get per-page scores you must run the "
                    "evaluation yourself via OpenDataLab/OmniDocBench."
                ),
                "rows": [],
                "missing_detail": missing,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def write_matrix(tasks: list[dict]) -> None:
    # Matrix is empty — no model publishes per-page predictions. We still
    # emit the 1,651-task universe with metadata so consumers can see the
    # slicing dimensions (data_source × language × layout × subset).
    (HERE / "per_task_matrix.json").write_text(
        json.dumps(
            {
                "note": (
                    "`matrix` is empty — no OmniDocBench leaderboard entry "
                    "ships per-page predictions. `tasks` lists the full "
                    "v1.6 universe (1,651 pages) with metadata so subsets "
                    "can be defined even though no per-run scoring column "
                    "exists yet. `task_levels` indexes the same data by "
                    "task_id for O(1) lookup. Populate `matrix[task_id]"
                    "[run_slug]` once any model publishes per-page dumps."
                ),
                "runs": [],
                "num_tasks": len(tasks),
                "tasks": tasks,
                "task_levels": {
                    t["task_id"]: {
                        "data_source": t["data_source"],
                        "language": t["language"],
                        "layout": t["layout"],
                        "subset": t["subset"],
                        "special_issue": t["special_issue"],
                    }
                    for t in tasks
                    if t["task_id"]
                },
                "matrix": {},
            },
            indent=2,
            ensure_ascii=False,
        )
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Reuse cached README.md + IDP HTML from cache/",
    )
    ap.add_argument(
        "--skip-annotations",
        action="store_true",
        help="Reuse cached OmniDocBench.json (~40MB)",
    )
    args = ap.parse_args()

    print("=" * 72)
    print("OmniDocBench leaderboard refresh")
    print(f"  output dir: {HERE}")
    print("=" * 72)

    print("[1/4] fetching OpenDataLab/OmniDocBench README.md")
    readme_md = fetch_text(
        GITHUB_README_URL, "README.md", refresh=not args.skip_scrape
    )
    v16_rows = scrape_github_readme(readme_md)
    print(f"  v1.6_full: {len(v16_rows)} entries")

    print("[2/4] fetching idp-leaderboard.org/benchmarks/omnidocbench")
    idp_html = fetch_text(
        IDP_LEADERBOARD_URL, "idp_leaderboard.html", refresh=not args.skip_scrape
    )
    v15_rows = scrape_idp_leaderboard(idp_html)
    print(f"  v1.5: {len(v15_rows)} entries")

    print("[3/4] fetching OmniDocBench.json annotations (40MB)")
    annotations = fetch_bytes(
        ANNOTATIONS_URL,
        "OmniDocBench.json",
        refresh=not args.skip_annotations,
    )
    tasks, task_stats = build_task_universe(annotations)
    print(f"  {task_stats['num_pages']} pages; "
          f"{len(task_stats['data_source_counts'])} doc types, "
          f"{len(task_stats['language_counts'])} languages")

    all_entries = v16_rows + v15_rows
    refresh_meta = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "readme_url": GITHUB_README_URL,
        "idp_url": IDP_LEADERBOARD_URL,
        "annotations_url": ANNOTATIONS_URL,
    }

    print(f"[4/4] writing leaderboard.json + rows/ ({len(all_entries)} entries)")
    write_leaderboard(all_entries, task_stats, refresh_meta)
    write_rows(all_entries)
    write_rows_index(all_entries)
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
