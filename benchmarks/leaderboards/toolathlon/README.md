# Toolathlon leaderboard snapshot

Snapshot of the public Toolathlon (Tool Decathlon) leaderboard plus per-task
pass/fail data for every submission that has published trajectories.
Intended for recomputing leaderboards on a subset of tasks.

## Sources

Data is pulled from two canonical Toolathlon resources:

- Overview: <https://toolathlon.xyz/docs/leaderboard>
  A Mintlify page rendering a plain HTML `<table class="performance-table">`
  with `Pass@1`, `Pass@3`, `Pass^3`, and `# Turns` per row (some entries
  carry a `± stderr`).
- Per-task detail: <https://huggingface.co/datasets/hkust-nlp/Toolathlon-Trajectories>
  One JSONL per `{model}_{run}.jsonl`, 108 lines each, carrying
  `task_name` and `task_status.evaluation` (boolean). Each model has three
  runs → three trials per (model, task). `task_status.running` values
  include `done` / `fail` / `timeout` / `max_turn_exceeded` — all count as
  trial attempts.

Only rows whose model has a matching HF slug get per-task data; newer
submissions (GPT-5.4, MiniMax-M2.7, Qwen3.x, Claude-4.6-*, etc.) are listed
in `rows_index.json` → `missing_detail`.

## Stats at time of snapshot

- 44 leaderboard rows; **20** carry per-task data
- 108 canonical tasks (all covered for every row with detail)
- 3 trials per task per submission (standard protocol); a handful of HF
  JSONLs have 1-2 missing tasks → trial totals of 320 instead of 324
- 22 HF model slugs; 2 (`gpt-5`, `minimax-m2`) have no matching
  leaderboard row — historic or superseded submissions

## Known upstream quirks

Most `recomputed_pass_rate` values agree with the advertised `pass_at_1`
within 0.3pp. Two rows diverge by >3pp:

- `GPT-5-high` (advertised 37.7, recomputed 29.0) and
- `GPT-5.1-high` (advertised 37.0, recomputed 33.3)

Both carry the `‡` footnote on the leaderboard, which usually marks a
re-evaluated or refreshed run. The HF trajectory snapshot is frozen and
may pre-date that refresh. Treat `pass_at_1` in `leaderboard.json` as the
currently-advertised score, and `tasks[].pass_rate` as the stats derived
from the HF trajectories actually shipped for that submission.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | Overview rows scraped from the Toolathlon leaderboard table. |
| `rows/<slug>.json` | Per-row detail: metadata + per-task stats (`task_name`, `n_trials`, `n_success`, `pass_rate`, `trial_running_statuses`). |
| `rows_index.json` | Summary per row, sorted by `pass_at_1`. `rows` = rows with per-task data; `missing_detail` = rows without. Includes `recomputed_pass_rate` to cross-check against `pass_at_1`. |
| `per_task_matrix.json` | `{task: {row_slug: {pass_rate, n_trials, n_success}}}`. Use this to recompute leaderboards on a task subset. |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                  # full refresh (downloads ~2 GB of JSONLs)
python refresh.py --skip-scrape    # reuse existing leaderboard.json
python refresh.py --skip-details   # reuse rows/*.json, just rebuild matrix
python refresh.py --workers 8      # more download parallelism
```

No auth needed — both sources are public.

## Model name → HF slug mapping

The leaderboard shows a display name (`Claude-4.5-Sonnet`) while the HF
dataset uses a canonical checkpoint-suffixed slug
(`claude-4.5-sonnet-0929`). `refresh.py` first tries the explicit
`MODEL_ALIASES` table, then falls back to a normalized-prefix match
(lowercase, non-alphanumeric stripped). Add aliases there when the
leaderboard gets new models with HF data.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"cvpr-research", "git-repo", "notion-find-job", ...}
by_row = {}
for task in subset:
    for slug, agg in m["matrix"][task].items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```
