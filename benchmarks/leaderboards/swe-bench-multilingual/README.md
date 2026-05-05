# SWE-bench Multilingual leaderboard snapshot

Snapshot of the public SWE-bench Multilingual leaderboard plus per-instance
pass/fail data for every submission. Intended for recomputing leaderboards
on a subset of tasks (e.g., by language).

## Sources

Data is pulled from the canonical SWE-bench repositories:

- Overview: `swe-bench/swe-bench.github.io` `data/leaderboards.json`
  (Jekyll data file that backs https://www.swebench.com/multilingual.html).
  We keep the `Multilingual` slice.
- Per-submission detail:
  `SWE-bench/experiments/evaluation/multilingual/<folder>/per_instance_details.json`
  — `{instance_id: {resolved, cost, api_calls}}`. At this snapshot, every
  Multilingual entry is a mini-SWE-agent maintainer baseline and uses this
  schema (no `results/results.json` variant).
- Task universe: `SWE-bench/SWE-bench_Multilingual` on Hugging Face
  (canonical 300 instance IDs across 9 programming languages).

SWE-bench Multilingual is pass@1 (single trial per instance), so
`n_trials == 1` for every (row, task) cell.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 14 overview rows from the Multilingual leaderboard (13 unique folders — the upstream data file lists one submission twice). |
| `rows/<folder>.json` | Per-row detail: metadata + per-task stats (`task_name`, `n_trials`, `n_success`, `pass_rate`). |
| `rows_index.json` | One-line summary per row, sorted by accuracy. Includes `recomputed_pass_rate` (from per-task counts) — should match `accuracy` within rounding. `missing_detail` lists rows with no per-instance file (empty at this snapshot). |
| `per_task_matrix.json` | `{task: {row_slug: {pass_rate, n_trials, n_success}}}`. Use this to recompute leaderboards on a task subset. |
| `refresh.py` | End-to-end refresh pipeline. |

## Stats at time of snapshot

- 13 unique leaderboard submissions (all mini-SWE-agent baselines)
- 300 canonical tasks (all covered)
- 1 trial per task per submission (pass@1)

## Refreshing

```sh
python refresh.py                # full refresh
python refresh.py --skip-scrape  # reuse existing leaderboard.json
python refresh.py --skip-details # reuse rows/, just rebuild matrix
python refresh.py --workers 16   # more parallelism
```

No auth needed — all sources are public raw files on GitHub and
datasets-server.huggingface.co.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"instance-id-1", "instance-id-2", ...}  # e.g., one language
by_row = {}
for task in subset:
    for slug, agg in m["matrix"][task].items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```

Instance IDs encode the repo (and therefore the language) in their prefix
— e.g., `django__django-12345` (Python), `gin-gonic__gin-*` (Go). For a
full `instance_id → language` mapping, use the `SWE-bench_Multilingual`
dataset on Hugging Face.
