# HLE third-party per-question snapshot

Per-question judged results collected from two independent evaluation
dumps on GitHub. These are **NOT** Scale submissions — they let you
reason about *which questions* each model gets right, not about where a
model ranks on `labs.scale.com`.

## Why this exists

The parent `hle/` snapshot (Scale leaderboard) ships aggregate accuracy
only: Scale does not re-export model predictions, `cais/hle` is a gated
dataset, and every row in `hle/rows/` has an empty `tasks: []`. So
there's no way to recompute accuracy on a subset (the whole point of
`per_task_matrix.json` in the SWE-bench and Aider snapshots).

Two third-party projects publish the exact
`run_judge_results.py`-shaped output for their own runs, keyed by the
canonical `cais/hle` question IDs. Since both use the same IDs the
cells merge into one `per_task_matrix`.

## Sources

| Source | Repo | Coverage | Run date | Judge |
| --- | --- | --- | --- | --- |
| ZenMux | [`ZenMux-1/zenmux-benchmark`](https://github.com/ZenMux-1/zenmux-benchmark) | 60 (vendor, model, provider) rows × 2,158 text-only questions | 2025-09-22 / 2025-09-28 | gpt-5 |
| supaihq | [`supaihq/hle`](https://github.com/supaihq/hle) | 18 frontier-model rows × up to 1,369 questions | 2025-11 / [whitepaper](https://sup.ai/research/hle-white-paper-jan-9-2026.pdf) | not documented |

Both sources publish full per-question payloads with
`judge_response.correct ∈ {"yes","no"}` plus model confidence and the
extracted final answer. `refresh.py` extracts only the minimal fields
that support task-subset analysis (task_id, correct, confidence,
truncated model_answer) and drops the full response / reasoning text.

## The honest health warnings

- **Accuracies here do not match Scale's leaderboard.** Different
  prompts, temperatures, judge configs, and (for supaihq) extra tooling
  shift the numbers. Use per-question pass/fail, not aggregate ranking.
- **ZenMux is text-only.** The `dataset_config.text_only` flag in each
  ZenMux file drops multimodal questions, leaving 2,158 of the 2,500.
  Questions with images never get judged by ZenMux runs.
- **supaihq uses tool use.** Their README: *"Individual model scores
  below are higher than their published benchmarks because we use custom
  instructions, web search, and retry when confidence is too low."*
  Per-question `correct` is still a valid signal; accuracies inflate
  ~5–10 points versus stock eval.
- **supaihq is a subset, not a random sample.** 1,369 out of 2,500
  public questions, with model coverage varying (some models judged
  only ~50 questions). Look at `num_questions` per row in
  `rows_index.json` before drawing conclusions — some supaihq rows are
  too sparse to be meaningful.
- **"main" is dropped from supaihq rows.** `judged_hle_pro.json` stores
  one key called `"main"` which is Sup AI's ensembled answer, not an
  individual model. We skip it.
- **Judge variance exists.** ZenMux uses gpt-5 as judge; the canonical
  HLE harness uses o3-mini. A judge swap on the same predictions would
  produce slightly different `correct` labels.

## Files

| File | What it is |
| --- | --- |
| `rows/<slug>.json` | One per (source, vendor, model, provider): metadata + `tasks: [{task_id, correct, confidence, model_answer}]` (2,158 or fewer entries each). |
| `rows_index.json` | One-line summary per row, sorted by accuracy desc. |
| `per_task_matrix.json` | `{tasks: [...], matrix: {task_id: {row_slug: {pass_rate, n_trials, n_success, confidence, source}}}}`. pass@1 cells — `n_trials = 1`. Not every (task, row) pair is filled; use `matrix[task_id].keys()` to see who judged what. |
| `leaderboard_alignment.json` | Best-effort map from third-party slugs → `../rows/<slug>.json` (Scale) slugs. `single` = one Scale row matches, `multi` = several (thinking/non-thinking, date variants) — pick by date or reasoning effort, `none` = no Scale analog. |
| `refresh.py` | Full pipeline. Also writes a local `_cache/` (gitignored, ~800 MB) so re-runs can skip the GitHub fetch. |

## Slug conventions

- ZenMux: `zenmux__<vendor>__<model>__<provider>` — e.g.
  `zenmux__openai__gpt-5__openai`, `zenmux__anthropic__claude-opus-4__google-vertex`.
  The provider axis is kept because ZenMux's dataset compares the same
  model across Anthropic / AWS Bedrock / Google Vertex / etc.
- supaihq: `supai__<vendor>-<model>` — e.g. `supai__openai-gpt-5.1`.
  supaihq doesn't track a provider axis.

## Refreshing

```sh
python refresh.py                # fetch both sources + rebuild (~2-5 min, ~800 MB download)
python refresh.py --skip-fetch   # reuse prior _cache/ payloads; just rebuild outputs
python refresh.py --workers 6    # increase download parallelism
```

No auth needed. The `_cache/` directory is gitignored and can be
deleted at any time — the next refresh will redownload.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))

# e.g. only biology questions (you'd join against cais/hle metadata here)
subset = {"668825f80a642802bdfeadfa", "668828540a642802bdfeadfc", ...}

by_row = {}
for task in subset:
    for slug, cell in m["matrix"].get(task, {}).items():
        by_row.setdefault(slug, []).append(cell["pass_rate"])

ranking = sorted(
    ((slug, sum(rs) / len(rs), len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
for slug, acc, n in ranking:
    print(f"{slug:<70} {acc:6.1%}  (n={n})")
```

Always print `n` — some rows judge far fewer questions than others and
subset accuracy can be misleading if coverage isn't flagged.

## Coverage at a glance

78 third-party rows total (60 ZenMux + 18 supaihq), spanning 2,337
unique question IDs (union of ZenMux's text-only 2,158 and supaihq's
1,369 subset). See `leaderboard_alignment.json` for which rows map to
which Scale leaderboard entries.
