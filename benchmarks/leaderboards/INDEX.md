# Leaderboards Index

Audit of the 19 benchmark leaderboards in this directory, tracking general stats and whether per-instance data is actually available (vs. stubbed / per-category / absent).

Last audited: 2026-04-23.

## Per-instance status legend

- **full** — real per-instance (per-task/per-question) score for each model × each instance
- **partial** — some models have per-instance data, most don't
- **per-category** — only per-category or comparative aggregates, no per-instance scores
- **placeholder** — no per-instance data; either `per_task_matrix.json` is missing entirely or `matrix` is `{}` (tasks list may be populated for shape only)

## Summary table

| Benchmark | # Models | # Instances | Per-instance | Evidence |
|---|---:|---:|---|---|
| aider-polyglot | 69 | 225 exercises | **placeholder** | No `per_task_matrix.json`; upstream policy: per-exercise pass/fail not published |
| aime2425 | 227 (67 matharena + 53 llmstats-2024 + 107 llmstats-2025) | 60 problems (AIME 2024 I+II + 2025 I+II) | **partial** | 30/60 tasks (AIME 2025) have per-instance data from `MathArena/aime_2025_outputs`; AIME 2024 has no published per-instance data anywhere — only aggregate rows from llm-stats. 67 MathArena rows × 30 tasks with up to 4 samples/cell. |
| dabstep | 1,872 | 450 tasks | **full** | `per_task_matrix.json`: 450 × 1,872 with `{pass_rate, n_trials, n_success}` |
| gdpval_aa | 336 | 220 occupations | **per-category** | Per-occupation `{win_rate, tie_rate}` only; comparative, not absolute pass/fail |
| gpqa-diamond | 462 | 198 questions | **placeholder** | AA-measured aggregate only. `tasks` populated (198 sha-keyed ids, domain metadata), `matrix={}`. No public frontier-scale per-question dump — HELM uses `gpqa_main` with encrypted instances; Open LLM Leaderboard v2 has per-sample GPQA Diamond but the `details_*` datasets are gated; Epoch AI Inspect logs are CAPTCHA-gated. |
| hle | 49 (+78 third-party) | 2,500 questions (2,337 covered) | **placeholder** (Scale) / **full** (third-party) | Scale `per_task_matrix.json` is a 382 B stub. `third_party_per_task/` adds 78 rows × 2,337 questions from ZenMux (60 rows, text-only) and supaihq (18 rows, 1,369-q subset, tool use). Different prompts/judges than Scale — do not re-rank. |
| imoanswerbench | 12 | 400 problems | **placeholder** | `tasks` populated (400), `matrix={}`; per-model per-question results not published |
| longbench-v2 | 36 | 503 tasks | **placeholder** | `tasks` populated with difficulty/domain metadata, `matrix={}` |
| mcp-atlas | 18 | 500 tasks | **placeholder** | `tasks` populated (500), `matrix={}`; per-model results not published by Scale AI |
| mmmu-pro | 73 | 1,730 questions | **partial** | Per-task data for only 16/73 model configs (GPT-4o, InternVL, Qwen variants) |
| omnidocbench | 57 | 1,651 pages | **placeholder** | `tasks` populated (1,651 v1.6), `matrix={}`; no per-page predictions published |
| osworld-verified | 139 | 361 tasks | **full** | 361 × 139 with `{score 0/1, n_trials, n_success}`; per-category breakdowns in rows |
| swe-bench-multilingual | 14 | 300 instances | **full** | 300 × 14 with `{pass_rate, n_trials, n_success}` |
| swe-bench-pro | 24 | 731 instances | **full** | 731 × 24 with `{pass_rate, n_trials, n_success}` |
| swe-bench-verified | 180 | 500 instances | **full** | 500 × 180 with `{pass_rate, n_trials, n_success}` |
| tau2-bench-telecom | 20 | 114 tasks (`base` split) | **full** | 114 × 15 with `{pass_rate, n_trials, n_success}` (4 trials, 1 row with 1 trial); 5 vendor aggregate-only rows in `missing_detail`. Leaderboard evaluates on the `base` split; repo also defines `small` (20), `train` (74), `test` (40), and `full` (2,285) splits — no published trajectories for those |
| terminal-bench_v2 | 123 | 89 tasks | **full** | 89 × 123 with `{pass_rate, n_trials, n_success}` (up to 5 trials) |
| toolathlon | 44 | 108 tasks | **full** | 108 × 44 with `{pass_rate, n_trials, n_success}` |
| vals-finance-agent | 45 | 10 categories | **per-category** | Per-category `{accuracy %, stderr, cost, latency}`; no per-question scores |

## By status

### full (9) — usable for subset recomputation
dabstep, hle (third-party only — see placeholder note), osworld-verified, swe-bench-multilingual, swe-bench-pro, swe-bench-verified, tau2-bench-telecom, terminal-bench_v2, toolathlon

### partial (2)
mmmu-pro — only 16/73 model configs have per-task data; the rest are aggregate-only.
aime2425 — per-instance covers AIME 2025 only (30/60 tasks, 67 models from MathArena); AIME 2024 is aggregate-only (llm-stats self-reported numbers from provider blogs).

### per-category (2)
gdpval_aa (220 occupations, win/tie rates only — comparative, not absolute), vals-finance-agent (10 task categories).

### placeholder (7) — no per-instance data usable for subset recomputation
aider-polyglot, gpqa-diamond, hle, imoanswerbench, longbench-v2, mcp-atlas, omnidocbench. These either ship an empty `matrix={}` (sometimes with the `tasks` list populated for shape compatibility) or omit the file entirely (aider-polyglot) because the upstream leaderboards do not publish per-model predictions. **hle** additionally ships a `third_party_per_task/` matrix (78 rows × 2,337 questions from ZenMux + supaihq) usable for subset recomputation — see `hle/third_party_per_task/README.md` for caveats (different prompts/judges than Scale).

## Notes

- "# Instances" reflects the benchmark's native unit: SWE-style instances, OSWorld tasks, HLE questions, OmniDocBench pages, vals task categories, etc.
- "Placeholder" leaderboards are structurally compatible with the visualizer but cannot drive subset recomputation until upstream publishes per-instance predictions.
- mmmu-pro's partial coverage comes from self-hosted runs (OpenAI & open-weight VLMs) rather than the public leaderboard.
- hle's third-party matrix is keyed to the canonical `cais/hle` IDs but was produced outside Scale's harness; accuracies will not match `labs.scale.com`. Use for per-question pass/fail analysis, not leaderboard ranking.
- tau2-bench-telecom's 114 tasks are the `base` split (40 `PERSONA:None` + 38 `Easy` + 36 `Hard`). Five other splits exist in `data/tau2/domains/telecom/split_tasks.json` (`small`, `train`, `test`, `full`), but the leaderboard and all published trajectories only cover `base`.
