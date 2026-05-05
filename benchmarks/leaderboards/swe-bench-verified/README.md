# SWE-bench Verified leaderboard snapshot

Snapshot of the public SWE-bench Verified leaderboard plus per-instance
pass/fail data for every submission that has published per-instance results.
Intended for recomputing leaderboards on a subset of tasks.

## Sources

Data is pulled from the canonical SWE-bench repositories:

- Overview: `swe-bench/swe-bench.github.io` `data/leaderboards.json`
  (Jekyll data file that backs https://www.swebench.com/verified.html).
  We keep the `Verified` slice.
- Per-submission detail: `SWE-bench/experiments`, two known schemas:
  - `evaluation/verified/<folder>/results/results.json` — classic
    submissions; the `resolved` key is a list of instance IDs.
  - `evaluation/bash-only/<folder>/per_instance_details.json` — mini-SWE-agent
    maintainer baselines; `{instance_id: {resolved, cost, api_calls}}`.
- Task universe: `SWE-bench/SWE-bench_Verified` on Hugging Face
  (canonical 500 instance IDs).

SWE-bench Verified is pass@1 (single trial per instance), so `n_trials == 1`
for every (row, task) cell.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 180 overview rows from the Verified leaderboard. |
| `rows/<folder>.json` | Per-row detail: metadata + per-task stats (`task_name`, `n_trials`, `n_success`, `pass_rate`). 173 rows — 7 submissions have no published per-instance data. |
| `rows_index.json` | One-line summary per row, sorted by accuracy. Includes `recomputed_pass_rate` (from per-task counts) — should match `accuracy` within rounding. `missing_detail` lists rows with no per-instance file. |
| `per_task_matrix.json` | `{task: {row_slug: {pass_rate, n_trials, n_success}}}`. Use this to recompute leaderboards on a task subset. |
| `refresh.py` | End-to-end refresh pipeline. |

## Stats at time of snapshot

- 180 leaderboard rows; **173** carry per-instance data
- 500 canonical tasks (all covered)
- 1 trial per task per submission (pass@1)
- 7 rows with no per-instance data in `SWE-bench/experiments` —
  the maintainers published only `metadata.yaml` (often alongside a
  `git_peek_suspicious_commits.md` audit note flagging possible `git log`
  contamination). See `rows_index.json` → `missing_detail`.

## Known upstream quirks

Two rows have `recomputed_pass_rate` that disagrees with the advertised
`accuracy` by >1%. These reflect real upstream data, not a bug in this
snapshot:

- `20260226_mini-v2.0.0_gemini-3-pro-high` — advertised 69.6%, but
  `per_instance_details.json` lists all 500 instances as `resolved: false`
  (likely a partial/pre-audit upload).
- `20250720_mini-v0.0.0-claude-3-7-sonnet-20250219` — advertised 52.8%,
  per-instance file shows 10.2%. The folder also contains a
  `git_peek_suspicious_commits.md` audit note; the published per-instance
  file appears to reflect a post-audit corrected count.

## Refreshing

```sh
python refresh.py                # full refresh (~60s with 16 workers)
python refresh.py --skip-scrape  # reuse existing leaderboard.json
python refresh.py --skip-details # reuse rows/, just rebuild matrix
python refresh.py --workers 32   # more parallelism
```

No auth needed — all sources are public raw files on GitHub and
datasets-server.huggingface.co.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"astropy__astropy-12907", "django__django-11179", ...}
by_row = {}
for task in subset:
    for slug, agg in m["matrix"][task].items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```
