# AIME 2024 + AIME 2025 leaderboard snapshot

Snapshot of a combined leaderboard across the full AIME 2024 and AIME
2025 contests — **60 canonical problems** (AIME 2024 I + II and AIME
2025 I + II, 15 problems each) — with per-task, per-model results
where publicly available.

## Why mirror (and not "scrape a single official page")

No single site hosts an official AIME 2024+2025 leaderboard with
per-instance data. We stitch three sources:

1. **Problem universe** — MathArena HuggingFace problem datasets
   (`MathArena/aime_2024_I`, `MathArena/aime_2024_II`,
   `MathArena/aime_2025`). These align 1:1 with MathArena's per-sample
   outputs for AIME 2025, so downstream joins are trivial.
2. **Per-instance AIME 2025 results** — `MathArena/aime_2025_outputs`
   on HuggingFace (parquet, 7,915 rows). Columns: `problem_idx`,
   `model_name`, `model_config`, `idx_answer`, `correct`,
   `gold_answer`, `parsed_answer`, `input_tokens`, `output_tokens`,
   `cost`. Usually 4 samples per (model, problem); 67 models.
3. **Aggregate rows** — `llm-stats.com/benchmarks/aime-2024` and
   `/aime-2025`. Scraped from the Next.js `self.__next_f.push` chunks.
   Scores here are **self-reported** — aggregated from provider blog
   posts/release announcements; `verified_count` is 0 for both boards.

## No per-instance data for AIME 2024

MathArena publishes `aime_2024_I` and `aime_2024_II` problem datasets
but **no** `aime_2024_outputs` dataset. The matharena.ai dashboard
does not surface AIME 2024 either. No other source publishes
per-model, per-problem predictions for AIME 2024 that we could find.
So for AIME 2024 we carry only aggregate rows (from llm-stats),
marked under `missing_detail` in `rows_index.json`.

The 30 AIME 2024 task IDs are still present in `tasks.json` and
`per_task_matrix.json` (with empty cells) so the shape stays uniform
and the moment someone publishes per-instance data it can drop in.

## Row taxonomy

Every row is one (source, year, model) triple:

- `matharena__aime_2025__<model_config_slug>` — per-instance (30 tasks,
  pass@1 averaged over up to 4 samples per cell). **Source of truth**
  for AIME 2025 per-task data.
- `llmstats__aime_2024__<model_slug>` — aggregate only, self-reported.
- `llmstats__aime_2025__<model_slug>` — aggregate only, self-reported
  (same model often appears under both `matharena` and `llmstats` for
  2025 with slightly different numbers).

## Stats at time of snapshot

- **227 rows** total: 67 from MathArena + 53 from llm-stats (2024) +
  107 from llm-stats (2025). The 67 MathArena rows are the only ones
  with per-task data.
- **60 tasks**: 30 covered by per-instance data (all AIME 2025),
  30 with empty cells (all AIME 2024).
- **Sampling**: MathArena runs each model ~4 times per problem
  (67 × 30 × 4 ≈ 8,040; parquet has 7,915 rows — a handful of cells
  have <4 samples; one upload has only 1 sample on 1 problem).

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | All 227 rows with metadata + aggregate accuracy. Sorted by (year, accuracy DESC). |
| `tasks.json` | 60 canonical problems with LaTeX statement + integer gold answer + year/half/idx. |
| `rows/<slug>.json` | Per-row detail with a full 60-entry `tasks: [...]` array (AIME 2024 cells zero-filled on matharena rows). |
| `rows_index.json` | One-line summary per row. Full-coverage rows appear under `rows`; aggregate-only and partial-upload rows under `missing_detail`. |
| `per_task_matrix.json` | `{tasks: [...60 ids...], matrix: {task_id: {row_slug: {pass_rate, n_trials, n_success}}}}`. Only AIME 2025 cells are populated. |
| `refresh.py` | End-to-end refresh pipeline. |

## Accuracy formulas

For MathArena rows the leaderboard reports two numbers:

- **`accuracy`** — macro-average of per-task pass rates, averaged over
  tasks with ≥1 trial. This matches MathArena's "run N times per
  problem, average" convention. Partial uploads (e.g. one row attempts
  only 1 problem) are not artificially diluted to zero — coverage is
  disclosed separately via `tasks_with_data`.
- **`accuracy_micro`** — micro-average: `total_successes / total_trials`.
  For full 30/30 coverage with uniform sample counts this matches
  `accuracy` exactly; differs slightly if some cells have 3 samples
  and others have 4.

llm-stats rows carry whatever score the provider reported; they have
no per-trial breakdown, so `accuracy_micro` is null.

Row sorting in `rows_index.json`:

- Full-coverage matharena rows first (sorted by `accuracy` DESC).
- Partial-coverage matharena rows pushed to the end of the `rows`
  list so sparse uploads don't rank near the top.
- All llm-stats rows and matharena rows without per-task data go to
  `missing_detail`, grouped by benchmark year then sorted by accuracy.

## Refreshing

```sh
python refresh.py                   # full refresh
python refresh.py --skip-tasks      # reuse existing tasks.json
python refresh.py --skip-matharena  # reuse cached MathArena parquet
python refresh.py --skip-llmstats   # reuse cached llm-stats HTML
```

No auth required. Large artifacts (`aime_2025_outputs.parquet`,
~135MB; HTML pages) are cached under `.cache/` and reused when the
corresponding `--skip-*` flag is passed.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"aime_2025_I_1", "aime_2025_II_7", ...}  # AIME 2025 only
by_row = {}
for task in subset:
    for slug, agg in m["matrix"].get(task, {}).items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```

AIME 2024 subsets will come back empty until someone publishes
per-instance data for that year.

## Caveats

- **Self-reported scores.** llm-stats `verified_count` is 0 for both
  boards. Providers use different judges, sampling settings, and retry
  policies — cross-check `self_reported_source` before comparing close
  scores.
- **Same model, two rows.** A model that MathArena evaluated directly
  and that a provider also blogged about will appear twice (once per
  source). They can disagree because of sampling and parsing
  differences; MathArena's number is the head-to-head comparable one.
- **MathArena model names can carry a reasoning-effort tag.**
  `GPT-5.2 (xhigh)` vs `GPT-5.2 (high)` are separate `model_config`
  rows reflecting different inference settings, not different models.
- **AIME 2025 problem_idx mapping.** MathArena merges AIME 2025 I + II
  into a single 30-row dataset where `problem_idx` 1-15 = AIME I and
  16-30 = AIME II. Our task IDs unmerge them (`aime_2025_I_1`,
  `aime_2025_II_1`, …) and each 2025 task in `tasks.json` carries a
  `merged_idx` so you can rejoin MathArena outputs directly.
- **Sparse upload.** One MathArena row (`Grok 4 Fast (Reasoning)
  (Selfcheck Agent)`) has results on only 1 problem. It's kept for
  fidelity with upstream but pushed to the bottom of the ranked list.
