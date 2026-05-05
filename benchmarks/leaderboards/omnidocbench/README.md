# OmniDocBench leaderboard snapshot

Snapshot of the OmniDocBench leaderboards. OmniDocBench
(arXiv:2412.07626, CVPR 2025) is a PDF-document-parsing benchmark from
OpenDataLab — 1,651 annotated pages (v1.6 full set; 1,355 page v1.5
subset) across 10 document types (academic papers, textbooks, exam
papers, newspapers, slides, handwritten notes, historical documents,
magazines, reports, books) and 3 languages (English, Simplified
Chinese, mixed).

Models output the Markdown of each page; the evaluator scores four
metric families and blends them into a single `Overall`:

    Overall = ((1 - TextEditDistance) * 100 + TableTEDS + FormulaCDM) / 3

## Sources

Two public leaderboards cover OmniDocBench. Both are aggregate-only —
neither publishes per-page predictions for any entry.

| Source | Track | Pages | Models covered | What it emphasizes |
| --- | --- | ---: | ---: | --- |
| [OpenDataLab/OmniDocBench README](https://github.com/opendatalab/OmniDocBench) | `v1.6_full` | 1,651 | 28 | Specialized VLMs + open-weight general VLMs |
| [idp-leaderboard.org](https://www.idp-leaderboard.org/benchmarks/omnidocbench) (Nanonets) | `v1.5` | 1,355 | 29 | Frontier closed VLMs (Claude / GPT / Gemini / Qwen) |

Concrete URLs:

- **README (v1.6_full table)**: <https://raw.githubusercontent.com/opendatalab/OmniDocBench/main/README.md>
- **IDP leaderboard (v1.5)**: <https://www.idp-leaderboard.org/benchmarks/omnidocbench>
- **Paper**: <https://arxiv.org/abs/2412.07626>
- **Dataset (1,651 annotated pages)**: <https://huggingface.co/datasets/opendatalab/OmniDocBench>
- **Eval code**: <https://github.com/opendatalab/OmniDocBench>

## Metric columns

| Column | Direction | Range | What it measures |
| --- | --- | --- | --- |
| `overall` | ↑ | 0–100 | Weighted blend (see formula above) |
| `text_edit` | ↓ | 0–1 | Normalized edit distance on text blocks |
| `formula_cdm` | ↑ | 0–100 | Formula recognition via [CDM](https://github.com/opendatalab/UniMER-1M) |
| `table_teds` | ↑ | 0–100 | Table TEDS (structure + cell text) |
| `table_teds_s` | ↑ | 0–100 | Table TEDS-S (structure only) |
| `reading_order_edit` | ↓ | 0–1 | Reading-order edit distance |

## Track comparability caveat

`v1.6_full` and `v1.5` scores are NOT directly comparable:

- Different page set: v1.6 added 296 hard pages (100 `equation_hard` +
  99 `layout_hard` + 97 `table_hard`) on top of v1.5's 1,355.
- The `Overall` denominator changed in v1.5 (see the v1.5 update note
  in OmniDocBench's README — now divides by 3 rather than the
  previous weighted mix).
- Rank **within** a track, not across. Models that appear in both
  (e.g. `GLM-OCR`, `GPT-5.2`, `Gemini 3 Pro`, `Gemini 3 Flash`) have a
  separate slug per track, suffixed `__v1_6` or `__v1_5`.

## Per-instance data — none available

Unlike MMMU-Pro (4 GPT-4o dumps + 12 VLMEvalKit xlsx), **no
OmniDocBench leaderboard entry publishes per-page predictions**. Every
row in this snapshot lives in `rows_index.json` → `missing_detail`,
and `per_task_matrix.json` carries the 1,651-page universe with metadata
but zero prediction columns.

Fineprint on what exists and why it isn't useful:

- **`OpenDataLab/OmniDocBench/result/`** contains per-page edit-distance
  JSONs but only for the 18-page `demo_data/` toy set, from an
  unlabeled example run — not a leaderboard entry.
- **Ground-truth annotations** (`OmniDocBench.json`) carry per-page
  metadata (data_source, language, layout, subset, special_issue
  tags), which we mirror into `per_task_matrix.json` → `tasks` +
  `task_levels`. Once a model publishes per-page dumps, populate
  `matrix[task_id][run_slug]` and the slicing infrastructure is
  already there.

To recover per-page scores yourself, clone the evaluation repo and run
`pdf_validation.py` with your model's Markdown outputs — the
`result/end2end_quick_match_*_per_page_edit.json` files it emits match
the per-task shape used by the other leaderboards in this repo.

## Task universe (1,651 pages)

| Dimension | Breakdown |
| --- | --- |
| Document type | 276 book · 253 PPT2PDF · 215 academic_literature · 193 exam_paper · 159 colorful_textbook · 151 newspaper · 149 magazine · 132 research_report · 118 note · 5 historical_document |
| Language | 765 simplified_chinese · 755 english · 116 en_ch_mixed · 13 traditional_chinese · 2 other |
| Layout | 887 single_column · 372 other_layout · 184 double_column · 155 1andmore_column · 53 three_column |
| Subset | 1,355 `v1.5` · 100 `equation_hard` · 99 `layout_hard` · 97 `table_hard` (v1.6 additions) |
| Special issue (top) | 332 table_horizontal · 266 colorful_backgroud · 160 table_full_line · 128 table_fewer_line · 111 table_span · 73 watermark · 55 table_with_formula · 44 table_omission_line · 30 fuzzy_scan |

Pages can carry multiple special-issue tags; 515 pages are tagged `None`.

## Top 10 on each track

### v1.6_full (official, 1,651 pages)

| Rank | Model | Type | Size | Overall ↑ | Text Edit ↓ | Formula CDM ↑ | Table TEDS ↑ | Read Order ↓ |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | MinerU2.5-Pro | Specialized VLM | 1.2B | **95.75** | 0.036 | **97.45** | **93.42** | 0.120 |
| 2 | GLM-OCR | Specialized VLM | 0.9B | 95.22 | 0.044 | 97.18 | 92.83 | 0.133 |
| 3 | PaddleOCR-VL-1.5 | Specialized VLM | 0.9B | 94.93 | 0.038 | 96.89 | 91.67 | 0.130 |
| 4 | PaddleOCR-VL | Specialized VLM | 0.9B | 94.18 | 0.040 | 95.91 | 90.65 | 0.135 |
| 5 | Youtu-Parsing | Specialized VLM | 2.5B | 93.74 | 0.044 | 93.63 | 92.02 | **0.116** |
| 6 | Ovis2.6-30B-A3B | General VLM | 30B | 93.70 | **0.035** | 95.17 | 89.44 | 0.135 |
| 7 | Logics-Parsing-v2 | Specialized VLM | 4B | 93.33 | 0.041 | 95.65 | 88.42 | 0.137 |
| 8 | FireRed-OCR | Specialized VLM | 2B | 93.26 | 0.037 | 95.44 | 88.04 | 0.131 |
| 9 | MinerU-2.5 | Specialized VLM | 1.2B | 93.04 | 0.045 | 95.77 | 87.88 | 0.130 |
| 10 | Gemini 3 Pro | General VLM | — | 92.91 | 0.064 | 95.99 | 89.15 | 0.165 |

### v1.5 (IDP / Nanonets, 1,355 pages)

| Rank | Model | Company | Overall ↑ | Text Edit ↓ | Formula CDM ↑ | Table TEDS ↑ | Read Order ↓ |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Gemini-3-Flash | Google | 90.06 | 0.077 | 90.22 | 87.65 | 0.081 |
| 2 | Nanonets OCR-3 | Nanonets | 90.00 | 0.068 | 87.65 | 88.88 | 0.100 |
| 3 | Nanonets OCR2+ | Nanonets | 89.48 | 0.056 | 90.34 | 79.10 | 0.090 |
| 4 | Gemini-3-Pro | Google | 88.81 | 0.078 | 87.26 | 87.00 | 0.084 |
| 5 | GPT-5.2 | OpenAI | 87.97 | 0.111 | 90.07 | 84.94 | 0.098 |
| 6 | Claude Sonnet 4.6 | Anthropic | 86.94 | 0.165 | 90.24 | 87.09 | 0.149 |
| 7 | Claude Opus 4.6 | Anthropic | 85.92 | 0.151 | 88.46 | 84.38 | 0.136 |
| 8 | Datalab Marker | Datalab | 85.51 | 0.109 | 88.28 | 79.13 | 0.106 |
| 9 | Gemini 3.1 Pro | Google | 85.34 | 0.082 | 83.32 | 80.85 | 0.073 |
| 10 | GPT-5.4 | OpenAI | 85.25 | 0.089 | 83.36 | 81.26 | 0.077 |

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 57 entries (28 v1.6_full + 29 v1.5) sorted by track then score, with both sources' schemas merged. |
| `rows/<slug>.json` | 57 per-entry files, slug suffixed `__v1_6` or `__v1_5`. `tasks` is always empty. |
| `rows_index.json` | All 57 entries live in `missing_detail` (no per-page predictions exist upstream). |
| `per_task_matrix.json` | 1,651-task universe with `data_source` / `language` / `layout` / `subset` / `special_issue` metadata. Empty `matrix` / `runs` until someone publishes per-page dumps. |
| `cache/*` | Raw source artifacts (README.md, idp_leaderboard.html, OmniDocBench.json) so re-runs can skip HTTP. |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                     # full refresh (~2 min, 40MB download)
python refresh.py --skip-scrape       # reuse cached README + IDP html
python refresh.py --skip-annotations  # reuse cached OmniDocBench.json
```

Pure stdlib — no external deps. `cache/` stores the 40MB annotations
JSON plus two HTML/markdown files so repeat runs take <1s.
`refresh.py` clears stale `rows/*.json` before writing.

## Slicing the task universe

Even without per-page predictions, you can carve the universe into
subsets today; when per-page dumps eventually appear you'll just plug
them into `matrix`.

```python
import json
m = json.load(open("per_task_matrix.json"))
# E.g. all Chinese academic pages with a horizontal table
subset = {
    t["task_id"]
    for t in m["tasks"]
    if t["data_source"] == "academic_literature"
    and t["language"] == "simplified_chinese"
    and "table_horizontal" in (t["special_issue"] or [])
}
print(len(subset), "pages in subset")
```

## Caveats

- **No per-instance data.** Every entry is aggregate-only. If you need
  per-page audits, you must re-run the evaluation locally.
- **`v1.6_full` ≠ `v1.5`.** Different page set (1,651 vs 1,355) and a
  tweaked Overall formula. Don't compare across tracks.
- **Self-reported scores.** The official README table is populated by
  model authors submitting PRs; the IDP leaderboard re-runs frontier
  closed models itself but isn't the canonical host. Expect ±1pt
  inconsistencies if you cross-reference the same model elsewhere.
- **Model-name collisions.** e.g. `GLM-OCR` on both tracks reports
  different numbers (95.22 on v1.6_full vs 69.23 on v1.5) because the
  v1.5 run used different weights / inference harness. Disambiguated
  via track suffix in slugs.
- **IDP HTML parsing is brittle.** We extract the models array from
  the Next.js RSC payload by locating a fixed model marker. If
  Nanonets redesigns the page, `scrape_idp_leaderboard` will need
  updating; track drift via the `_IDP_MARKER` constant.
