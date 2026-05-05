# benchguard — score static audits against BenchGuard's paper metrics

Reuses the BenchGuard paper's eval pipeline (`BenchGuard/eval/match.py` + `metrics.py`)
to score `task_audits_static/` from this repo's `bench_audit` framework.

## Layout

```
audits_to_benchguard_findings.py   # converter: our audit schema -> BenchGuard normalize.py output schema
run_eval.sh {bixbench|sab}         # convert -> match -> metrics
output/                            # generated; see run_eval.sh for paths
```

## Prereqs

- `bench_audit/.env` with `GOOGLE_API=...` (the runner remaps it to `GEMINI_API_KEY` for LiteLLM).
- BenchGuard either pip-installed (`pip install -e BenchGuard/`) or importable via
  `PYTHONPATH` (the runner sets this to `BenchGuard/src`).
- LiteLLM + python-dotenv already in BenchGuard's `pyproject.toml`.

## Run

From repo root:

```bash
bench_audit/benchmarks/benchguard/run_eval.sh bixbench
bench_audit/benchmarks/benchguard/run_eval.sh sab
```

Override the judge model (default `gemini/gemini-3-flash-preview`):

```bash
JUDGE_MODEL=gemini/gemini-2.5-flash bench_audit/benchmarks/benchguard/run_eval.sh bixbench
```

## Outputs (paper-style report)

- `output/reports/{bench}_eval.md` — human-readable: summary, recall, per-model
  precision/recall, ensemble, per-issue detail, missed issues.
- `output/reports/{bench}_eval.json` — same metrics, machine-readable.

Intermediates (kept for caching/debugging):
- `output/normalized/{bench}_findings.json` — audits in BenchGuard finding shape.
- `output/matches/{bench}_matches.json` + `output/matches/cache_{bench}/` — per-pair LLM verdicts (cached).

## Field mapping (audit -> BenchGuard finding)

| BenchGuard | Source |
|---|---|
| `category` | `ambiguity → INST`, `test_quality → EVAL`, `environment → ENV` |
| `severity` | `3 → CRITICAL`, `2 → HIGH`, `1 → MEDIUM`, `0 → LOW` |
| `confidence` (numeric) | record-level `low → 0.3`, `medium → 0.7`, `high → 0.9` |
| `confidence_level` | record-level `low → POSSIBLE`, `medium → LIKELY`, `high → CONFIRMED` |
| `title` | `claim` |
| `description` | `why_it_matters` (fallback to `claim`) |
| `subcategory` | `subtype` |

## Caveats

- Single auditor → ensemble columns ≥2/≥3 will be 0. To recover the paper's
  ensemble number, run multiple auditors and emit one findings file per "model".
- Your taxonomy has no `GT` category, so gold issues whose root cause is a wrong
  reference answer may come back UNRELATED more often. Read the *Missed Issues*
  section of the markdown report as the diagnostic.
- SAB task IDs: gold uses bare ints (`"9"`); audits use `task_009__name`. The
  converter strips the prefix automatically and aborts if any gold task is
  unmapped.
