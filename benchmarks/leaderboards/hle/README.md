# Humanity's Last Exam (HLE) leaderboard snapshot

Snapshot of the HLE leaderboard maintained at `labs.scale.com`. HLE is
a 2,500-question closed-answer benchmark built jointly by the Center
for AI Safety and Scale AI (arXiv:2501.14249).

## Source

- Overview: <https://labs.scale.com/leaderboard/humanitys_last_exam>
  A Next.js page. The leaderboard ships as a JS `entries` array inside
  `self.__next_f.push` chunks, with one object per submission:
  `{model, rank, score, confidenceInterval_upper, contaminationMessage,
  company, createdAt, calibrationError, maxScore}`.
  `refresh.py` extracts and decodes that array.

## No per-instance data (from Scale)

HLE does **not** publish per-model, per-question predictions:

- The 2,500 questions live behind a gated HuggingFace dataset
  (`cais/hle`) that requires accepting a contact-sharing form.
- Scale does not re-export submission predictions. A private subset of
  the questions is also held out to limit training-data leakage.
- Almost every post-release submission carries a
  `contamination_message` warning because the public half of the
  dataset is reachable by model builders.

Every row therefore lands in `rows_index.json` → `missing_detail`, and
`per_task_matrix.json` is an empty shape placeholder so downstream
tooling can treat HLE uniformly with other leaderboards.

## Third-party per-question data (new)

`third_party_per_task/` collects per-question judged outputs from two
independent evaluation dumps that happen to use the canonical
`cais/hle` question IDs:

- [`ZenMux-1/zenmux-benchmark`](https://github.com/ZenMux-1/zenmux-benchmark)
  — 60 (model × provider) rows over a 2,158-question text-only slice
  (2025-09-22).
- [`supaihq/hle`](https://github.com/supaihq/hle) — 18 frontier-model
  rows over a 1,369-question subset (2025-11).

These are **not** Scale submissions and their accuracies do not match
the numbers on `labs.scale.com`. Use them to ask
"which questions does model X get right" rather than to re-rank the
leaderboard. See [`third_party_per_task/README.md`](third_party_per_task/README.md)
for full methodology, caveats, and a subset-recompute recipe.
`third_party_per_task/leaderboard_alignment.json` maps third-party rows
to the 49 Scale leaderboard rows where names align (37 of 78 third-party
rows have a Scale analog; the rest are models Scale never ranked, such
as Claude 3.5 Haiku, GPT-4o-mini, Grok, Qwen3, GLM).

## Stats at time of snapshot

- 49 leaderboard rows
- Single metric: accuracy % over 2,500 questions (headline ranking)
- Secondary metric: `calibration_error` % (lower = better)
- Theoretical ceiling (`max_score`): ~49.85%
- Judge model: `o3-mini` (per agi.safe.ai documentation)

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 49 rows with accuracy, CI upper, calibration error, company, `createdAt`, contamination notes. |
| `rows/<slug>.json` | Per-row metadata. `tasks: []` — no per-instance data. |
| `rows_index.json` | One-line summary per row, sorted by accuracy. All rows under `missing_detail`. |
| `per_task_matrix.json` | `{tasks: [], matrix: {}}` — shape placeholder. |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                  # full refresh
python refresh.py --skip-scrape    # reuse existing leaderboard.json
```

No auth required for the leaderboard. `refresh.py` deletes stale
`rows/*.json` before writing so rename-churn in the leaderboard doesn't
leave orphaned files behind.

## Caveats

- Several rows share the same `rank` because Scale uses a statistical
  ranking (rank = 1 + # models whose lower CI beats this row's upper
  CI). Sort by `accuracy` for a strict ordering.
- The `contamination_message` field is populated for nearly every row
  — HLE is a public dataset, so Scale flags any post-release
  submission as potentially contaminated. Treat this as a caveat, not
  a verdict.
- A handful of rows come with extra notes in that field (e.g. "9%
  (216 prompts) failed due to a post-training bug and were counted as
  failures" for `o1 Pro`). Read it before comparing close scores.
- `max_score` (~49.85%) is the empirical ceiling from Scale's harness;
  use it when normalizing scores to a "% of achievable" view.
