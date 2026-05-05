# LongBench v2 leaderboard snapshot

Snapshot of the LongBench v2 leaderboard maintained at
`longbench2.github.io`. LongBench v2 (arXiv:2412.15204) is a 503-question
4-way multiple-choice benchmark for deep reasoning over realistic long
contexts, from 8k to 2M words. Built by THUDM / Tsinghua / Z.ai.

## Source

- **Project site / leaderboard**: <https://longbench2.github.io/#leaderboard>
  The leaderboard is **hard-coded inline** into `index.html` — the
  referenced JS files (`static/js/results/*.js`) 404. `refresh.py` parses
  the `<tbody>` of `<table id="results">` directly and extracts the 12
  metric cells per row (Overall / Easy / Hard / Short / Medium / Long ×
  w/o CoT / w/ CoT).
- **Eval code**: <https://github.com/THUDM/LongBench> (`pred.py`,
  `result.py`, `config/`, `prompts/`). No predictions directory.
- **Task dataset**: <https://huggingface.co/datasets/zai-org/LongBench-v2>
  (the `THUDM/LongBench-v2` path redirects here). One file: `data.json`
  (~465 MB including contexts). We fetch metadata only via HF's
  `datasets-server.huggingface.co/rows` pagination API — six calls at
  `length=100` — to get `_id`, `difficulty`, `length`, `domain`,
  `sub_domain`, and `answer` per question without downloading contexts.

## No per-instance data

LongBench v2 does **not** publish per-model, per-question predictions:

- The GitHub repo only ships eval code, not submission artifacts.
- The HF dataset repo has `data.json` (questions) only — no `pred/`,
  `results/`, or submissions directory.
- No HuggingFace Space or submissions portal — new entries are added to
  the site via PRs against the maintainers' repo.
- The 503-question test set is **public**, so every submission is
  potentially contamination-exposed; upstream does not add a
  contamination flag the way HLE does.

Every row therefore lands in `rows_index.json` → `missing_detail`.
Unlike HLE, `per_task_matrix.json` is **not** empty-shaped: since the
task universe itself is public, we list every `task_id` with its
difficulty/length/domain labels so downstream tools can still filter
to a subset — but the `matrix` (task → model) is `{}` until someone
runs `pred.py` against each model and contributes predictions.

## Stats at time of snapshot

- 36 model leaderboard rows + 2 baseline rows (`Human`, `Random`)
- 503 questions
  - Difficulty: 192 easy, 311 hard
  - Length: 180 short (≤32k), 215 medium (32k–128k), 108 long (128k–2M)
  - Domain: 175 Single-Doc QA, 125 Multi-Doc QA, 81 Long ICL,
    50 Code-Repo, 39 Long-Dialogue History, 33 Long Structured Data
- Single metric: accuracy % (4-way MCQ, pass@1)
- Reporting: 12 cuts per model — {Overall, Easy, Hard, Short, Medium,
  Long} × {w/o CoT, w/ CoT}. 🧠 reasoning models report **w/ CoT only**.
- Baselines: `Human` = 53.7% (15-min time budget), `Random` = 25.0%

## Top 10 by Overall (w/ CoT)

| Model | Company | 🧠 | Overall | Easy | Hard | Short | Medium | Long |
| --- | --- | :---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemini-2.5-Pro | Google | ✓ | 63.3 | 75.0 | 56.1 | 67.2 | 56.3 | 71.0 |
| Gemini-2.5-Flash | Google | ✓ | 62.1 | 72.3 | 55.8 | 68.3 | 60.0 | 55.7 |
| Qwen3-235B-A22B-Thinking-2507 | Alibaba | ✓ | 60.6 | 70.5 | 54.4 | 62.8 | 59.9 | 58.1 |
| DeepSeek-R1 | DeepSeek | ✓ | 58.3 | 66.1 | 53.4 | 62.2 | 54.4 | 59.3 |
| Qwen3-235B-A22B-Instruct-2507 | Alibaba |  | 58.3 | 66.7 | 53.1 | 63.3 | 55.3 | 55.6 |
| o1-preview | OpenAI | ✓ | 57.7 | 66.8 | 52.1 | 62.6 | 53.5 | 58.1 |
| DeepSeek-R1-0528 | DeepSeek | ✓ | 56.7 | 59.4 | 55.0 | 66.7 | 50.9 | 51.4 |
| MiniMax-Text-01 | MiniMax |  | 56.5 | 66.1 | 50.5 | 61.7 | 56.7 | 47.2 |
| Gemini-2.0-Flash-Thinking | Google | ✓ | 56.0 | 62.8 | 51.9 | 61.1 | 55.2 | 49.1 |
| Gemini-Exp-1206 | Google |  | 52.5 | 61.5 | 47.1 | 55.6 | 49.5 | 53.3 |

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 36 rows with all 12 metric cuts, plus a `baselines` array for Human/Random. |
| `rows/<slug>.json` | Per-row metadata. `tasks: []` — no per-instance data. |
| `rows_index.json` | One-line summary per row under `missing_detail`, sorted by overall (w/ CoT when available, else w/o CoT). |
| `per_task_matrix.json` | Task universe (503 ids with difficulty/length/domain/sub_domain). `matrix: {}` — no predictions. |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                  # full refresh (scrape + HF task fetch)
python refresh.py --skip-scrape    # reuse existing leaderboard.json
python refresh.py --skip-tasks     # reuse cached task universe from per_task_matrix.json
```

No auth required. `refresh.py` clears stale `rows/*.json` before writing
so rename-churn in the upstream table doesn't leave orphaned files.

## Caveats

- **Aggregate-only**. Without per-question predictions you cannot
  recompute accuracy on a task subset. `per_task_matrix.json` carries
  the task labels so you can pre-select a subset; actually scoring it
  still requires running `pred.py` yourself.
- **Reasoning vs. non-reasoning reporting is asymmetric**. Native
  reasoning models (🧠) only report w/ CoT. The w/o CoT column is `null`
  for those rows — don't average across models naïvely.
- **Contamination is not flagged upstream.** The 503 questions are
  public; treat post-release submissions with the same suspicion you
  would on HLE even though upstream doesn't annotate it.
- **Table has duplicate "GPT-4o" model names** (2024-08-06 and
  2024-11-20 snapshots). We distinguish by `date`; slug collisions get a
  `__N` suffix.
- `Human` baseline was measured with a 15-minute time constraint.
  Easy-bucket humans reach 100% without the constraint by construction.
