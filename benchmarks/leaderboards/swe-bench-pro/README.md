# SWE-bench Pro (Public) leaderboard snapshot

Snapshot of the Scale Labs SWE-bench Pro public leaderboard plus per-instance
pass/fail data pulled from two backing sources (GitHub + Scale's S3 bucket).
Intended for recomputing leaderboards on a subset of tasks.

## Sources

Four sources, used end-to-end:

1. **Overview** — `https://labs.scale.com/leaderboard/swe_bench_pro_public`.
   Scraped out of the page's embedded Next.js RSC payload
   (`"entries":[...]`). 24 models, ranked, with 95% CI widths.
2. **GitHub pre-graded results** —
   `scaleapi/SWE-bench_Pro-os` `traj/<folder>/eval_results.json`.
   Each file is `{instance_id: bool}`. Nine folders available (5 paper +
   4 from the Oct 2025 leaderboard snapshot).
3. **S3 raw per-instance outputs** —
   `s3://scaleapi-results/swe-bench-pro/<folder>/`. Seven additional
   submissions live here only (newer models + debug runs).
   - A few folders ship a pre-graded `eval_results.json`
     (`<folder>/output/eval_results.json`) — we use it directly.
   - The rest have per-instance test outputs
     (`<folder>/eval/<instance>/_output.json` — JSON listing every
     test's name + PASSED/FAILED status). We grade locally using
     SWE-bench Pro's own rule:

         passed = {t for t in tests if t.status == "PASSED"}
         resolved = (fail_to_pass ∪ pass_to_pass) ⊆ passed

     (from `scaleapi/SWE-bench_Pro-os/swe_bench_pro_eval.py`).
4. **Task universe** — `ScaleAI/SWE-bench_Pro` on Hugging Face
   (Public split, 731 instance IDs). HF is also the source for the
   `fail_to_pass` / `pass_to_pass` test lists used when grading S3
   submissions.

SWE-bench Pro is pass@1 — `n_trials == 1` per (row, task) pair.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 24 leaderboard entries scraped from Scale Labs (aggregate scores only). |
| `rows/<folder>.json` | 16 submissions with per-instance data. Each row carries `source` (`github` / `s3_prebuilt` / `s3_graded`), `evaluated_instance_ids`, `resolved_instance_ids`, plus a per-task array with `{task_name, evaluated, n_trials, n_success, pass_rate}`. |
| `rows_index.json` | Per-row summary sorted by `accuracy` desc. Shows both "reported" counts (on the submission's own eval set, as `recomputed_pass_rate`) and "canonical" counts (`accuracy` = resolved / trials on the 731 Public instances). |
| `per_task_matrix.json` | `{task: {row_slug: {pass_rate, n_trials, n_success, evaluated}}}`. Use this to recompute leaderboards on a task subset. |
| `refresh.py` | End-to-end refresh pipeline. |

## Stats at time of snapshot

- 24 models on the public Scale Labs leaderboard
- 16 submissions with per-instance data captured here:
  - 9 from GitHub (pre-graded)
  - 1 from S3 with pre-graded `output/eval_results.json`
  - 6 graded locally from S3 per-instance outputs
- 731 canonical Public instances
- 1 trial per task per submission (pass@1)

Cross-check (grading sanity): our computed `claude-4-5-Sonnet` pass rate
(43.6% on canonical 731) matches Scale's leaderboard 43.60% exactly;
`claude-4-5-haiku` at 40.8% is within Scale's 95% CI of 39.45±3.6.

## Reported vs canonical — what to watch out for

Each submission's eval lists the instances it actually evaluated. This
set is **not** always equal to the canonical 731:

| Folder | Source | Reported n | Resolved | On canonical 731 |
| --- | --- | --- | --- | --- |
| `claude-45sonnet-10132025` | github | 730 | 319 (43.7%) | 319 (43.6%) |
| `claude-45haiku-10222025` | s3_graded | 727 | 298 (41.0%) | 298 (40.8%) |
| `glm-4p5-10222025` | s3_graded | 728 | 267 (36.7%) | 267 (36.5%) |
| `gpt-5-250-turns-10132025` | github | 729 | 265 (36.4%) | 265 (36.3%) |
| `claude-4sonnet-10132025` | github | **562** | 240 (42.7%) | 240 (32.8%) |
| `gpt-5-codex-debug-oct22` | s3_graded | 707 | 195 (27.6%) | 195 (26.7%) |
| `gpt-5-high-paper` | s3_graded | 707 | 180 (25.5%) | 180 (24.6%) |
| `claude-opus-4-1-paper` | github | **891** | 206 (23.1%) | 162 (22.2%) |
| `gemini-2-5-pro-preview-paper` | github | **955** | 105 (11.0%) | 90 (12.3%) |

Two reasons the counts diverge:

1. **Paper runs** used a superset of tasks (the paper's eval set wasn't
   filtered down to the final Public 731 yet), so some resolved IDs fall
   outside the canonical universe.
2. **Some leaderboard runs (e.g. `claude-4sonnet-10132025`) only
   evaluated a subset** — 562 of 731. Treating the 169 missing instances
   as failures is pessimistic (hence 32.8% canonical vs 42.7% reported,
   which matches Scale's 42.7% leaderboard number).

The matrix's `evaluated` flag lets you filter — see "Recomputing" below.

## Refreshing

```sh
python refresh.py                # full refresh (GitHub + S3 if AWS creds present)
python refresh.py --skip-scrape  # reuse existing leaderboard.json
python refresh.py --skip-details # reuse rows/, just rebuild matrix
python refresh.py --no-s3        # GitHub submissions only
python refresh.py --workers 16   # more parallelism
```

**Required credentials for S3 submissions:** `aws configure` must be set
up for an account with read access to `s3://scaleapi-results/`. Sync uses
a local cache at `/tmp/sbp_s3_cache/` (override via `SBP_S3_CACHE`).
Cached syncs are idempotent; rerunning only transfers new files.

The HF datasets-server endpoint (for the test-list index) requires no
auth.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"instance-id-1", "instance-id-2", ...}

# For fair comparison, only average over tasks the submission evaluated.
by_row = {}
for task in subset:
    for slug, cell in m["matrix"][task].items():
        if not cell["evaluated"]:
            continue
        by_row.setdefault(slug, []).append(cell["pass_rate"])

ranking = sorted(
    ((slug, sum(rs) / len(rs), len(rs)) for slug, rs in by_row.items() if rs),
    key=lambda x: -x[1],
)
# Each entry: (submission_slug, pass_rate_on_subset, num_evaluated_in_subset)
```
