# Terminal-Bench 2.0 leaderboard snapshot

Snapshot of the public Terminal-Bench 2.0 leaderboard plus per-task pass-rate
data for every submission. Intended for recomputing leaderboards on a subset
of tasks.

## Source

Both the overview and per-task metrics are scraped from tbench.ai directly:

- Overview: <https://www.tbench.ai/leaderboard/terminal-bench/2.0>
- Per-row detail:
  `https://www.tbench.ai/leaderboard/terminal-bench/2.0/<agent>/<version>/<model@provider,...>`

Each detail page is a Next.js server-rendered table of `{task_name, n_trials,
success_count, pass_rate}` for every task. All 123 public rows (including
maintainer baselines like Terminus 2 / Mini-SWE-Agent / OpenHands) are
available — no HF download needed.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 123 overview rows from the leaderboard table. |
| `rows/<slug>.json` | Per-row detail: row metadata + per-task stats (`task_name`, `n_trials`, `n_success`, `pass_rate`). |
| `rows_index.json` | One-line summary per row, sorted by accuracy. Includes `recomputed_pass_rate` (from per-task counts) — should match `accuracy` within rounding. |
| `per_task_matrix.json` | `{task: {row_slug: {pass_rate, n_trials, n_success}}}`. Use this to recompute leaderboards on a task subset. |
| `refresh.py` | End-to-end refresh pipeline. |

## Stats at time of snapshot

- 123 leaderboard rows, every row carries per-task data
- 89 tasks in Terminal-Bench 2.0
- 5 trials per task per submission (standard protocol)

## Refreshing

```sh
python refresh.py                # full refresh (~30s with 8 workers)
python refresh.py --skip-scrape  # reuse existing leaderboard.json
python refresh.py --skip-details # reuse rows/, just rebuild matrix
python refresh.py --workers 16   # more parallelism
```

No auth needed — the leaderboard pages are public.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"adaptive-rejection-sampler", "bn-fit-modify", ...}
by_row = {}
for task in subset:
    for slug, agg in m["matrix"][task].items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```
