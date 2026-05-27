<h1 align="center">Automated Auditing for LLM &amp; Agent Benchmarks</h1>

<p align="center">
  <a href="https://arxiv.org/abs/2605.26079">
    <img alt="arXiv" src="https://img.shields.io/badge/arXiv-2605.26079-b31b1b.svg">
  </a>
  <a href="https://autobenchaudit.com">
    <img alt="Website" src="https://img.shields.io/badge/Website-autobenchaudit.com-4c8bf5.svg">
  </a>
  <a href="https://www.python.org/downloads/release/python-3120/">
    <img alt="Python" src="https://img.shields.io/badge/python-3.12+-blue.svg">
  </a>
</p>

**`auto-bench-audit`** (ABA) is an agentic pipeline that audits LLM and agent benchmarks for task ambiguity, environment conflicts, and evaluation defects — issues that even original benchmark authors miss. It operates across agentic, patch-based, and static-QA benchmarks under a single protocol: (1) a benchmark-level audit, (2) evidence collection that normalizes heterogeneous artifacts into a uniform task manifest, and (3) a per-task audit emitting structured findings (claim, severity, evidence file path, suggested fix).

## Setup

Requires Python 3.12+. Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv venv --python 3.12
uv sync
cp .env.example .env   # then fill in API keys and data paths
```

All scripts in this repo source `${REPO_ROOT}/.env` automatically; see `.env.example` for the full list of supported variables.

## Audit any benchmark in one command

Point `scripts/audit_one.sh` at any public benchmark's GitHub URL:

```bash
scripts/audit_one.sh --url https://github.com/centerforaisafety/hle --sample-n 3
```

This clones the repo, writes a minimal config to `configs/quick/<name>.yaml`, and runs the three audit phases end-to-end in static mode (`audit-benchmark` → `collect-evidence` → `audit-tasks --mode static --sample-n N`).

The wrapper works for static-QA benchmarks (HLE, GPQA, MMLU-style) and agentic ones (SWE-bench, OSWorld, τ-bench) alike — the collector agent figures out each repo's structure on its own. For full control over phases, configs, trajectory-mode audits, and batch runs, see the rest of this README.

```bash
scripts/audit_one.sh --help        # all flags
```

## Audit Pipeline

For batch runs across many benchmarks, trajectory-mode audits, or custom configs, use the underlying `bench-audit` CLI directly. End-to-end, the streaming pipeline runs five stages per benchmark: `audit-benchmark` → `collect-evidence` → `sample-tasks` → `audit-tasks` → cleanup.

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

### Step 1 — Benchmark-level audit

The auditor agent is given the benchmark's repository and documentation and characterizes the benchmark as a whole — its scope, evaluation methodology, known limitations, and structural risks. This stage runs once per benchmark and produces a benchmark-level report that guides downstream task sampling.

```bash
bench-audit audit-benchmark \
    --config configs/multi_domain_all/medical_health/clinbench.yaml
```

### Step 2 — Evidence collection

The collector agent resolves the benchmark's heterogeneous artifacts (repo, dataset, recorded trajectories) into a uniform manifest plus per-task `TaskConfig` / `EvalConfig` JSONs that downstream auditors can consume without knowing each benchmark's idiosyncratic layout.

```bash
bench-audit collect-evidence \
    --config configs/multi_domain_all/medical_health/clinbench.yaml
```

### Step 3 — Task-level audit

The auditor agent is initialized per task with the task configuration and file paths to the relevant artifacts. Using shell tools, it inspects each task against a standardized rubric and emits structured findings (claim, category, severity, evidence, why-it-matters, suggested fix). Findings are emitted along three independent axes — Instruction, Environment, Evaluation — each scored 0/1/2.

Run the auditor in one of two modes:

**Static audit** — the auditor reads only the task definition: the instruction the agent would receive, the tests its solution would be graded against, the evaluation configuration, etc. No execution is observed.

```bash
bench-audit audit-tasks \
    --config configs/multi_domain_all/medical_health/clinbench.yaml \
    --mode static --all
```

**Trajectory audit** — the auditor additionally reads recorded agent traces (`trajectory_path`) and test outputs (`test_output_path`), allowing it to catch runtime issues that static inspection cannot.

If you do not already have recorded trajectories, `auto-bench-audit` can generate them by wrapping [Harbor](https://github.com/harbor-framework/harbor). The example below runs Claude Code Sonnet on Terminal-Bench 2 and writes a ready-to-audit collection config to `configs/harbor/collection_<name>.yaml`:

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
auto-bench-audit/
├── benchmarks/        # Benchmark indexes (multi-domain, frontier, leaderboards, benchguard)
├── configs/           # Per-benchmark YAML configs (multi_domain_all, frontier_benchmarks,
│                      #   swe_bench, tb2, harbor, quick)
├── rubrics/           # general_rubric.yaml + benchmark/task rubric .txt files
├── scripts/           # audit_one.sh (one-command audit), multi_domain_streaming_pipeline
│                      #   (batch), sample_tasks helper
├── src/bench_audit/   # Audit CLI implementation
└── pyproject.toml
```

## Citation

If you use `auto-bench-audit` in your research, please cite:

```bibtex
@misc{wang2026automatedbenchmarkauditingai,
  title         = {Automated Benchmark Auditing for AI Agents and Large Language Models},
  author        = {Junlin Wang and Federico Bianchi and Shang Zhu and Fan Nie and Yongchan Kwon and Bhuwan Dhingra and James Zou},
  year          = {2026},
  eprint        = {2605.26079},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2605.26079},
}
```

