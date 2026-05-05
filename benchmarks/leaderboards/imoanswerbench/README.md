# IMO-AnswerBench leaderboard snapshot

Snapshot of a mirrored leaderboard for IMO-AnswerBench — the
short-answer half of the IMO-Bench suite introduced in "Towards Robust
Mathematical Reasoning" (Luong et al., EMNLP 2025,
[arXiv:2511.01846](https://arxiv.org/abs/2511.01846)).

## Why mirror (and not "scrape the official page")

The canonical site ([imobench.github.io](https://imobench.github.io/))
only hosts **IMO-ProofBench** leaderboards. No aggregate AnswerBench
leaderboard is maintained upstream; model providers publish AnswerBench
scores in their release blogs. We therefore mirror two sources and
seed a paper-reference row so the benchmark's own headline baseline is
visible:

1. <https://llm-stats.com/benchmarks/imo-answerbench>
   Next.js page. A `models` array inside `self.__next_f.push` chunks
   carries `{rank, model_name, organization_name, score, verified,
   self_reported, self_reported_source, announcement_date,
   input_cost_per_million, context_window, param_count,
   is_open_source, ...}`. llm-stats collects self-reported numbers from
   provider blog posts — `verified_count` is currently 0 for every
   entry.
2. <https://raw.githubusercontent.com/google-deepmind/superhuman/main/imobench/answerbench_v2.csv>
   The 400 canonical problems (superseded the original
   `answerbench.csv` on 2026-02-12). Columns: `Problem ID`, `Problem`,
   `Short Answer`, `Category`, `Subcategory`, `Source`. We keep task
   IDs + category/subcategory/source + a truncated ground-truth
   preview for downstream per-instance joins.
3. Paper abstract (arXiv:2511.01846). One hard-coded
   `paper_reference=True` row for **Gemini Deep Think (IMO Gold)** at
   80.0%, since llm-stats tracks open-source models only.

## No per-instance data

No per-model, per-question predictions have been released anywhere for
IMO-AnswerBench. Every row lives in `rows_index.json` →
`missing_detail`. `per_task_matrix.json` is populated with the 400
task IDs but ships an empty `matrix` — shape-compatible with other
leaderboards so downstream tools don't need a special case.

## Stats at time of snapshot

- 12 leaderboard rows (11 from llm-stats + 1 paper-reference row)
- 400 problems in `tasks.json`
- Single metric: accuracy as a 0–1 fraction (ranking metric)
- Category counts in v2: Algebra 99, Combinatorics 100, Geometry 100,
  Number theory 100, and 1 legacy "Functional Equation" row that
  survived the v2 relabel

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 12 rows with score + verification flags + self-reported source URL + announcement date + cost/context/param metadata. |
| `rows/<slug>.json` | Per-row metadata. `tasks: []` — no per-instance data. |
| `rows_index.json` | Flat summary sorted by accuracy. All rows under `missing_detail`. |
| `tasks.json` | 400 problems from `answerbench_v2.csv` with category/subcategory/source + short-answer preview. |
| `per_task_matrix.json` | `{tasks: [...400 ids...], matrix: {}}` — shape placeholder. |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                  # full refresh
python refresh.py --skip-scrape    # reuse existing leaderboard.json
python refresh.py --skip-tasks     # reuse existing tasks.json
```

No auth required. `refresh.py` clears `rows/*.json` before writing so
rename-churn on llm-stats doesn't leave orphaned files.

## Caveats

- **All scores are self-reported.** llm-stats.com `verified_count` is
  0. Treat the ranking as a directional signal, not a head-to-head
  evaluation — providers may use different judges, sampling settings,
  or retry policies. Cross-check with the `self_reported_source` URL
  before comparing close scores.
- **answerbench_v2 vs answerbench.** Some published scores were
  computed against the older `answerbench.csv` (now deprecated). The
  v2 update fixed ambiguous problem statements and incorrect answers
  in a handful of rows, so comparing old vs new scores isn't strictly
  apples-to-apples — but the large majority of problems are unchanged.
- **Gemini Deep Think (IMO Gold).** Paper-reference row, not tracked
  upstream. Remove it from `PAPER_REFERENCE_ROWS` in `refresh.py` once
  llm-stats (or another aggregator) starts carrying Gemini numbers.
- **Difficulty tiers aren't in the CSV.** The paper reports per-tier
  counts (pre-IMO / IMO-Easy / IMO-Medium / IMO-Hard) but those tags
  aren't encoded in `answerbench_v2.csv`, so `tasks.json` doesn't
  expose them either.
