<h1 align="center">Automated Benchmark Audit (ABA)</h1>

<p align="center">
  🌐 <a href="https://autobenchaudit.com">autobenchaudit.com</a>
</p>

<p align="center">
ABA is an auditing pipeline for agent and llm benchmarks that surfaces task ambiguity, environment conflicts, and evaluation issues. This code repo contains pipeline to run (1) a benchmark-level audit (2) samples tasks, and produces task-level audit so benchmark authors and users can trust the scores they report.
</p>

## Overview

Modern LLM benchmarks sit behind containerized environments, multi-stage harnesses, and grading logic that depends on runtime state — a complexity that outpaces manual review. ABA is an agentic framework that systematically audits these benchmarks and surfaces issues that even original authors miss: hidden environment dependencies, implicit specification gaps, and brittle evaluation logic.

The pipeline is benchmark-agnostic and operates across agentic, patch-based, and static-QA benchmarks under a single protocol. A deterministic evidence collector resolves each benchmark's heterogeneous artifacts (repo, dataset, recorded trajectories) into a uniform manifest, after which the framework emits structured per-task findings — each citing the file path it was drawn from — and can suggest targeted fixes alongside them.

## Setup

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv venv --python 3.12
uv sync
cp .env.example .env   # then fill in API keys and data paths
```

All scripts in this repo source `${REPO_ROOT}/.env` automatically; see `.env.example` for the full list of supported variables.

## Audit Pipeline

End-to-end, the streaming pipeline runs five stages per benchmark: `audit-benchmark` → `collect-evidence` → `sample-tasks` → `audit-tasks` → cleanup.

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

Configure run output via the `AUDIT_RUN_DIR` env var (or `MULTI_DOMAIN_AUDIT_RUN_DIR`). The pipeline writes its tracker to `configs/multi_domain_all/streaming_pipeline_tracking.json`.

### Benchmark-Level Audit

The auditor agent is given the benchmark's repository and documentation and characterizes the benchmark as a whole — its scope, evaluation methodology, known limitations, and structural risks. This stage runs once per benchmark and produces a benchmark-level report that guides downstream task sampling.

```bash
bench-audit audit-benchmark \
    --config configs/multi_domain_all/medical_health/clinbench.yaml
```

### Task-Level Audit

After evidence collection, the auditor agent is initialized per task with the task configuration and file paths to the relevant artifacts. Using shell tools, it inspects each task against a standardized rubric and emits structured findings (claim, category, severity, evidence, why-it-matters, suggested fix). Findings are emitted along three independent axes — Instruction, Environment, Evaluation — each scored 0/1/2.

Collect evidence first, then run the auditor in one of two modes:

```bash
bench-audit collect-evidence \
    --config configs/multi_domain_all/medical_health/clinbench.yaml
```

**Static audit** — the auditor reads only the task definition: the instruction the agent would receive, the tests its solution would be graded against, the evaluation configuration, etc. No execution is observed.

```bash
bench-audit audit-tasks \
    --config configs/multi_domain_all/medical_health/clinbench.yaml \
    --mode static --all
```

**Trajectory audit** — the auditor additionally reads recorded agent traces (`trajectory_path`) and test outputs (`test_output_path`), allowing it to catch runtime issues that static inspection cannot.

If you do not already have recorded trajectories, ABA can generate them by wrapping [Harbor](https://github.com/harbor-framework/harbor). The example below runs Claude Code Sonnet on Terminal-Bench 2 and writes a ready-to-audit collection config to `configs/harbor/collection_<name>.yaml`:

```bash
# 1. Generate trajectories via Harbor (writes collection_<name>.yaml).
bench-audit generate \
    --harbor-config configs/tb2/eval_claude_code_sonnet.yaml \
    --benchmark-type tb2 \
    --agent-cli claude \
    --model claude-sonnet-4-6

# 2. Audit the resulting trajectories.
bench-audit audit-tasks \
    --config configs/harbor/collection_terminal-bench.yaml \
    --mode trajectory --all
```

## Project Layout

```
bench_audit_clean/
├── benchmarks/        # Benchmark categorization (multi-domain)
├── configs/           # Per-benchmark YAML configs (multi_domain_all)
├── rubrics/           # benchmark_rubric.txt + task_rubric_ambiguity_v3.txt
├── scripts/           # Streaming pipeline + sample-tasks helper
├── src/bench_audit/   # Audit CLI implementation
└── pyproject.toml
```
