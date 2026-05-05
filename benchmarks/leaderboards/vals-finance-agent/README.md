# Vals AI Finance Agent leaderboard snapshot

Snapshot of the public [Vals AI Finance Agent benchmark](https://www.vals.ai/benchmarks/finance_agent)
leaderboard — "Evaluating agents on core financial analyst tasks". Private
537-question evaluation set. 45 model entries at time of snapshot.

## Granularity caveat — read this first

**Vals AI does not publish per-question pass/fail data for any model.**
The finest breakdown they expose publicly is **aggregate accuracy per model
per category**, across nine categories (plus an overall score):

- `simple_retrieval_quantitative`
- `simple_retrieval_qualitative`
- `complex_retrieval`
- `numerical_reasoning`
- `financial_modeling` (labelled "Financial Modeling / Projections")
- `market_analysis`
- `beat_or_miss`
- `trends`
- `adjustments`

So in this snapshot, **one "task" = one category**, not one question. If
you need per-instance data for subset recomputation, see the DABStep
leaderboard (`../dabstep/`) — that benchmark is also finance-domain and does
publish per-question scores for every submission.

## Source

A single Astro-rendered page:

  https://www.vals.ai/benchmarks/finance_agent

The full leaderboard payload is embedded in the page HTML as props on the
`BenchmarkView` Astro island. No API, no auth. `refresh.py` parses the
island's `props="..."` attribute, strips Astro's `[type, value]` type
markers, and writes the snapshot.

Payload shape (after unwrapping):

```
benchmarkView
  metadata: {benchmark, slug, updated, total_models, models: [...], tasks: {slug: label, ...}}
  tasks:
    <category_slug>:
      <model_key>:           # e.g. anthropic/claude-opus-4-7
        accuracy              # percent, 0-100
        stderr                # percentage points, as displayed
        latency, cost_per_test
        temperature, top_p, max_output_tokens
        reasoning, reasoning_effort, verbosity, compute_effort
        provider
```

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 45 model rows — overall accuracy + per-category accuracy, generation config, reported cost/latency. |
| `rows/<slug>.json` | One file per model with metadata + per-category stats (accuracy, stderr, cost, latency). Slug matches the `/models/<slug>` URL. |
| `rows_index.json` | Sorted one-line summary per model (by overall accuracy). |
| `per_task_matrix.json` | `{category: {model_slug: {accuracy, stderr, cost_per_test, latency}}}`. Same shape as the DABStep matrix, but cells are **aggregates per category**, not per-instance pass/fail. |
| `public_questions.json` | Maps each of the 50 public-split questions (from `data/benchmark_repos/finance_agent/data/public.csv`) to one of the 9 category slugs via the CSV's `Question Type` column. Emitted so downstream consumers can tag audited tasks with their Vals category and aggregate per-task severities up to the category level. Skipped if the CSV isn't present. |
| `refresh.py` | Scrape + build pipeline. |

## Stats at time of snapshot

- **45** models
- **9** task categories (+ 1 aggregate "overall")
- Benchmark version: `Finance Agent (v1.1)`
- Updated: `2026-04-20`
- Dataset: private (50/537 questions public on HuggingFace)

### Top 10 by overall accuracy

| Model | Provider | Overall | Cost/test |
| --- | --- | ---: | ---: |
| claude-opus-4-7 | Anthropic | 64.37 ± 2.79 | $1.34 |
| claude-sonnet-4-6 | Anthropic | 63.33 ± 2.84 | $1.44 |
| muse_spark | Meta | 60.60 ± 2.84 | $0.06 |
| claude-opus-4-6-thinking | Anthropic | 60.05 ± 2.78 | $1.11 |
| gemini-3.1-pro-preview | Google | 59.72 ± 2.80 | $0.87 |
| claude-opus-4-5-thinking | Anthropic | 58.81 ± 2.81 | $1.50 |
| gpt-5.2-2025-12-11 | OpenAI | 58.53 ± 2.87 | $0.98 |
| glm-5.1-thinking | Zhipu AI | 57.66 ± 2.80 | $0.29 |
| gpt-5.4-2026-03-05 | OpenAI | 57.15 ± 2.85 | $1.41 |
| gpt-5.1-2025-11-13 | OpenAI | 55.31 ± 2.80 | $0.47 |

## Refreshing

```sh
python refresh.py                          # fetch + rebuild all outputs
python refresh.py --html-cache page.html   # skip network fetch, rebuild from saved HTML
```

Fast (~1 s end-to-end; one HTTP GET). The upstream page is public; no auth.

## Recomputing accuracy on a category subset

Because "tasks" here are categories (not individual questions), subset
recomputation weights categories equally (or you can weight by your own
n-per-category estimate):

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"numerical_reasoning", "complex_retrieval", "adjustments"}
by_model = {}
for cat in subset:
    for slug, cell in m["matrix"].get(cat, {}).items():
        by_model.setdefault(slug, []).append(cell["accuracy"])
ranking = sorted(
    ((slug, sum(xs) / len(xs)) for slug, xs in by_model.items()),
    key=lambda x: -x[1],
)
```

For a properly weighted subset score you'd need question counts per
category — Vals doesn't publish those, but you can approximate from
`stderr`: for binary accuracy, `n ≈ p(1-p) / (stderr/100)²`.
