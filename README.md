# bench-audit

Per-task and benchmark-level audit tooling for coding benchmarks.

## Setup

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv venv --python 3.12
uv sync
```

## Running the multi-domain audit pipeline

The streaming pipeline drives, per benchmark:
1. `audit-benchmark`
2. `collect-evidence`
3. `sample-tasks`
4. `audit-tasks` (batched over sampled task IDs)
5. cleanup of fetched repo/data dirs on success

```bash
# Run all benchmarks under configs/multi_domain_all/
bash scripts/multi_domain_streaming_pipeline.sh

# Limit to one domain
bash scripts/multi_domain_streaming_pipeline.sh --domain medical_health

# Run a specific config
bash scripts/multi_domain_streaming_pipeline.sh \
    --config configs/multi_domain_all/medical_health/clinbench.yaml

# Inspect tracker state
bash scripts/multi_domain_streaming_pipeline.sh --status
```

Configure run output via the `AUDIT_RUN_DIR` env var (or `MULTI_DOMAIN_AUDIT_RUN_DIR`).
The pipeline writes its tracker to
`configs/multi_domain_all/streaming_pipeline_tracking.json`.

## Layout

```
bench_audit_clean/
├── benchmarks/        # Benchmark categorization (multi-domain)
├── configs/           # Per-benchmark YAML configs (multi_domain_all)
├── rubrics/           # benchmark_rubric.txt + task_rubric_ambiguity_v3.txt
├── scripts/           # Streaming pipeline + sample-tasks helper
├── src/bench_audit/   # Audit CLI implementation
└── pyproject.toml
```

## Rubric Categories

The per-task rubric evaluates three independent dimensions, each with severity 0–3:

1. **Ambiguity / Underspecification** (A1–A7) — missing info, misleading prompts, undisclosed mechanisms
2. **Environment Conflict** (E1–E5) — broken tools, resource limits, test harness bugs
3. **Test Quality / Specifications** (T1–T5) — overly narrow tests, missing coverage, wrong targets
