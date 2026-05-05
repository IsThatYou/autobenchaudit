# MCP Atlas leaderboard snapshot

Snapshot of the public MCP Atlas leaderboard (Scale AI) plus the task
list from the 500-task public subset. Intended for recomputing rankings
on task subsets **if/when** Scale releases per-instance pass/fail data.

## Sources

- Overview: <https://labs.scale.com/leaderboard/mcp_atlas>
  A Next.js page. The leaderboard data ships in two places in the same
  HTML response:
  - An `entries` array inside `self.__next_f.push` chunks, carrying
    `{model, rank, score (Pass Rate % over all 1,000 tasks),
    confidenceInterval_upper, company, createdAt, deprecated, maxScore}`
  - A plain Sanity `tableRow` block with three cells per row:
    `[model_name, "Pass Rate % (All 1000)", "Pass Rate % (Public 500)"]`
  `refresh.py` pulls both and joins by model name, falling back to a
  score-based match when the two payloads disagree on reasoning-knob
  labels (e.g. entries says `reasoning = xhigh` while the table says
  `reasoning_effort = xhigh`).
- Task list: <https://huggingface.co/datasets/ScaleAI/MCP-Atlas>
  Single parquet (`MCP-Atlas.parquet`) with 500 rows — the public half of
  the 1,000-task benchmark. Fields: `TASK` (id), `ENABLED_TOOLS`,
  `PROMPT`, `GTFA_CLAIMS`, `TRAJECTORY`. We keep only `TASK`, the size of
  `ENABLED_TOOLS`, and a 240-char preview of `PROMPT`.

## No per-instance data (yet)

Unlike Toolathlon or SWE-bench Verified, **Scale does not publish
per-task, per-model pass/fail results for MCP Atlas**. The Hugging Face
release is the task inputs only; no trajectory files exist. Every row in
`rows_index.json` therefore lands in `missing_detail`, and
`per_task_matrix.json` ships with a populated `tasks` list but an empty
`matrix`. The shape is preserved so downstream tooling (e.g. the
visualizer) doesn't need a special case — it will just treat MCP Atlas
as "aggregate-only" until per-instance data becomes available.

## Stats at time of snapshot

- 18 leaderboard rows
- 500 public tasks (full benchmark is 1,000)
- Two advertised metrics per row:
  - `pass_at_1_all_1000` — headline score on the full 1,000-task set
    (used for ranking)
  - `pass_at_1_public_500` — same scoring on just the public HF subset
- Pass criterion: a task is "passed" if the judge (Gemini 2.5 Pro,
  temperature 0) assigns ≥75% claim coverage against `GTFA_CLAIMS`

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 18 rows with both pass-rate columns, CI upper bound, company, createdAt, and max score. |
| `rows/<slug>.json` | Per-row metadata (no `tasks` array — kept for shape parity with other leaderboards). |
| `rows_index.json` | One-line summary per row, sorted by `pass_at_1_all_1000`. All rows live under `missing_detail`. |
| `tasks.json` | 500 task IDs from the HF parquet + enabled-tools count + prompt preview. |
| `per_task_matrix.json` | `{tasks: [...500 ids...], matrix: {}}` — shape placeholder for future per-instance data. |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                  # full refresh
python refresh.py --skip-scrape    # reuse existing leaderboard.json
python refresh.py --skip-tasks     # reuse existing tasks.json (skip parquet download)
```

No auth required — both sources are public. The parquet is ~16 MB.

## Caveats

- The React `entries` array and the HTML `tableRow` block disagree on
  the exact label for 3 models (`Gemini 3.1 Pro Preview`,
  `GPT-5.4 (reasoning ...)`, `o3 pro`). `refresh.py` joins by
  `(All-1000 score rounded to 1dp, base-model prefix)` as a fallback.
  If Scale adds a third reasoning variant of the same base model at the
  same score the fallback could pick the wrong row — log a warning and
  re-check the join if that happens.
- `Gemini 3 Pro Preview` shows `70.8` in the JS payload but `70.7%` in
  the HTML table (rounding). The `entries` value wins.
- `maxScore` (~83.1%) is the empirical ceiling from Scale's harness;
  use it when normalizing scores to a "% of achievable" view.
