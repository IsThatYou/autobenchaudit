# tau2-bench Telecom leaderboard snapshot

Snapshot of the public tau2-bench leaderboard (telecom domain) plus
per-task pass/fail data for every submission that has published
trajectories. Intended for recomputing leaderboards on a subset of
tasks.

The telecom domain is the "dual-control" mobile-service scenario from
the tau²-bench paper — 114 tasks, each a customer support conversation
between an LLM agent and a simulated user. A submission is evaluated
over 4 trials per task (1 trial for some older runs).

## Sources

Data is pulled from two canonical tau2-bench resources:

- Aggregate metadata: `github.com/sierra-research/tau2-bench`
  `web/leaderboard/public/submissions/<sub_id>/submission.json`
  gives `results.telecom.pass_{1..4}`, `cost`, methodology, and (when
  uploaded) the `trajectory_files.telecom` filename. Manifest at
  `manifest.json`; schema at `schema.json`.
- Per-trial trajectories: `sierra-tau-bench-public` S3 bucket
  (`us-west-2`, public, no auth) at
  `submissions/<sub_id>/trajectories/<file>.json`. Each telecom
  trajectory is `{timestamp, info, tasks[114], simulations[114 * n_trials]}`.
  `simulations[i].reward_info.reward` ∈ {0.0, 1.0} is the per-trial
  pass/fail signal, keyed by `task_id` and `trial`.

Some legacy submissions (`claude-3-7-sonnet`, `gpt-4.1`, `gpt-4.1-mini`,
`o4-mini`, `gpt-5`, `qwen3-max_2026-01-23`, `toolorchestra`) have
trajectories on S3 even though their `submission.json` has
`trajectories_available: false` or an unpopulated `trajectory_files`.
`refresh.py` falls back to listing the S3 `trajectories/` prefix and
picks the `*_telecom_default_*` / `*_telecom_base_*` file, skipping the
`telecom-workflow` / `no-user` ablation variants.

## Stats at time of snapshot

- **20** leaderboard entries carry a `telecom.pass_1` score
- **15** of those carry per-task trajectories on S3
- **114** canonical telecom tasks (all covered for every row with detail)
- 4 trials per task per submission for 14/15 rows; **1** trial for
  `toolorchestra_nvidia_2025-12-02` (only single-trial file published)
- 5 rows without per-task data (model-vendor aggregate-only submissions)
  — see `rows_index.json` → `missing_detail`. In particular, several
  >95% advertised scores (`claude-sonnet-4-5_anthropic`, `gemini-3-pro_google`,
  `deepseek-v3.2_deepseek`) sit in `missing_detail` because Sierra has
  not yet re-run + uploaded trajectories for those vendor submissions.
- Voice submissions (`gpt-realtime-*`, `gemini-*-live`, `xai-realtime`,
  `grok-voice-*`) use a different file layout (`results.json` + audio)
  and are **not** ingested here.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 20 overview entries flattened from `submission.json` files. |
| `rows/<slug>.json` | Per-row detail: metadata + per-task stats (`task_id`, `n_trials`, `n_success`, `pass_rate`). 15 rows. |
| `rows_index.json` | One-line summary per row, sorted by advertised `pass_1`. Includes `recomputed_pass_rate` (from per-task counts). `missing_detail` lists rows without per-trial trajectories. |
| `per_task_matrix.json` | `{task_id: {row_slug: {pass_rate, n_trials, n_success}}}`. Use this to recompute leaderboards on a task subset. Task IDs are semantic, e.g. `[mobile_data_issue]data_mode_off|data_usage_exceeded[PERSONA:None]`. |
| `refresh.py` | End-to-end refresh pipeline. |

## Known upstream quirks

For most rows `recomputed_pass_rate` matches the advertised `pass_1`
within 0.3pp. Two legacy rows disagree by >1pp:

- `o4-mini_openai_2024-06-20` — advertised `pass_1=50.2`, recomputed
  `42.1` (Δ +8.1pp). The S3 `_telecom_default_` trajectory has only
  192/456 passing trials.
- `gpt-4-1-mini_openai_2024-06-20` — advertised `pass_1=48.9`,
  recomputed `43.9` (Δ +5.0pp). S3 file is the `_telecom_base_`
  variant with 200/456 passing trials.

Both are legacy Sierra runs. The advertised leaderboard number likely
reflects a re-run that was never re-uploaded — treat `pass_1` in
`leaderboard.json` as the advertised score, and `recomputed_pass_rate`
as what you get from the trajectories actually shipped on S3.

## Refreshing

```sh
python refresh.py                  # full refresh (~550 MB of JSON)
python refresh.py --skip-scrape    # reuse existing leaderboard.json
python refresh.py --skip-details   # reuse existing rows/*.json
python refresh.py --workers 8      # more S3 download parallelism
```

No auth needed — both sources are public.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {
    "[mobile_data_issue]data_mode_off|data_usage_exceeded[PERSONA:None]",
    "[service_issue]airplane_mode_on|break_apn_settings|contract_end_suspension|unseat_sim_card[PERSONA:Easy]",
    # ...
}
by_row = {}
for task in subset:
    for slug, agg in m["matrix"][task].items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```

## References

- Paper: [τ²-Bench: Evaluating Conversational Agents in a Dual-Control
  Environment](https://arxiv.org/abs/2506.07982)
- Leaderboard site: <https://taubench.com/>
- Submission docs: <https://github.com/sierra-research/tau2-bench/blob/main/docs/leaderboard-submission.md>
- Maintainer S3 layout: <https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/scripts/leaderboard/MAINTAINER.md>
