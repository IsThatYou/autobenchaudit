from __future__ import annotations

from pathlib import Path

from .config import EvidenceCollectionConfig


def render_collect_prompt(
    config: EvidenceCollectionConfig,
    output_root: str,
    collector_path: str,
    manifest_path: str,
    task_config_dir: str,
) -> str:
    models_path = Path(__file__).with_name("models.py").resolve()

    if config.benchmark_type == "neurips":
        return _render_neurips_collect_prompt(
            config, output_root, collector_path, manifest_path, task_config_dir, models_path,
        )

    dirs_block = _dirs_block(config)
    swe_bench_test_download = _swe_bench_test_download_block(config)
    return f"""You are an evidence collector for bench-audit.

1. Read the dataclass definitions in {models_path} to understand ArtifactManifest,
   TaskEntry, TaskConfig, and EvalConfig schemas.

2. Explore the benchmark directories to understand the data layout.

3. Write a Python 3 collector script to: {collector_path}
   - Accept --manifest-path and --task-config-dir CLI arguments
   - Discover benchmark tasks and eval results from the configured directories
   - Write a YAML ArtifactManifest to --manifest-path
   - Write per-task TaskConfig JSON files to --task-config-dir/<task_id>/task_config.json
   - Write per-eval EvalConfig JSON files to --task-config-dir/<task_id>/<eval_id>.json

4. Run the collector script:
   python {collector_path} --manifest-path {manifest_path} --task-config-dir {task_config_dir}

You are responsible for both writing AND executing the collector.
The runtime will only validate the outputs afterward.

Benchmark inputs:
- benchmark_name: {config.benchmark_name}
- benchmark_type: {config.benchmark_type}
- job_type: {config.job_type}
- benchmark_data_dir: {config.benchmark_data_dir}
{dirs_block}\
- output_root: {output_root}

TaskConfig derivation rules (each task may have multiple evals):
- n_evals, n_passed, n_failed: count from the task's evals
- status: "passed" if any eval passed, otherwise "failed"
- primary_eval_id: prefer passed evals, then most recent by finished_at, then by eval_id

EvalConfig derivation rules (one per eval):
- EvalConfig contains only eval-specific data; task-level data lives in TaskConfig
- task_id: must match the parent TaskConfig.task_id
- is_primary_eval: true if this eval's eval_id matches the parent TaskConfig.primary_eval_id
- metrics: load and inline the JSON content from metrics_path (null if missing or unreadable)

Conventions:
- Use eval_results_dir (not job_dir) for the per-eval result directory path
- Use test_output_path for the single canonical test output file path
- Emit absolute paths everywhere
- Use yaml.safe_dump(..., sort_keys=False) for the manifest
- Use json.dumps(..., indent=2, sort_keys=True) for TaskConfig
- Status must be "passed" or "failed" only
- Derive instruction_text by reading instruction files
- Prefer deterministic ordering by task_id
- For missing optional files, use null
- Include all discovered evals per task; do not collapse multiple evals
- audit_notes: free-text guidance for the downstream task audit agent.
  Summarize what you learned about how this task is evaluated — which eval
  scripts/functions determine pass/fail, where they live in the codebase,
  and any benchmark-specific context the auditor needs to assess eval quality.
  If the task references external artifacts (images, audio, video, PDFs, or
  any other files the problem statement or reference answer depends on),
  resolve each artifact to its actual on-disk location and list the absolute
  paths under a "Referenced artifacts:" section. The auditor is required to
  read every path in audit_notes, so this is how you make those artifacts
  part of the audit. Do not trust paths stored inside upstream data files
  without verifying they exist — re-resolve against benchmark_data_dir.
{swe_bench_test_download}"""


def _render_neurips_collect_prompt(
    config: EvidenceCollectionConfig,
    output_root: str,
    collector_path: str,
    manifest_path: str,
    task_config_dir: str,
    models_path: Path,
) -> str:
    repo_line = ""
    if config.benchmark_repo_dir:
        repo_line = f"- benchmark_repo_dir: {config.benchmark_repo_dir}\n"
    dataset_line = ""
    if config.dataset_id:
        dataset_line = f"- dataset_id: {config.dataset_id}\n"
    code_url_line = ""
    if config.code_url:
        code_url_line = f"- code_url: {config.code_url}\n"
    data_acquisition_hint_block = ""
    if config.data_acquisition_hint:
        data_acquisition_hint_block = (
            "\n### Step 1d: Benchmark-specific data acquisition (REQUIRED)\n"
            "The following instructions override the generic Step 1c guidance for\n"
            "this benchmark. Follow them exactly to populate `benchmark_data_dir`:\n\n"
            f"{config.data_acquisition_hint.rstrip()}\n"
        )
    prompt = f"""You are an evidence collector for bench-audit.

## Phase 1: Ensure benchmark materials are available

Before collecting evidence, make sure the benchmark data is available locally.
The benchmark directory is organized as:
```
<benchmark_dir>/
├── repo/    ← cloned repository (benchmark_repo_dir)
├── data/    ← downloaded/processed dataset (benchmark_data_dir)
└── paper.pdf ← benchmark paper (if available)
```

### Step 1a: Clone the repository (if needed)
If `benchmark_repo_dir` is provided and is empty or does not exist, and `code_url`
is available, clone the repository into `benchmark_repo_dir`.

### Step 1b: Download the paper (if needed)
If there is no paper PDF in the benchmark directory, try to find and download it.
Check the repo's README for an arXiv link or paper URL. If found, download the
PDF to the parent of benchmark_repo_dir (i.e. alongside the `repo/` and `data/`
directories) as `paper.pdf`. The paper helps downstream auditors understand the
benchmark's methodology and evaluation design.

### Step 1c: Populate the data directory (if needed)
If `benchmark_data_dir` is empty or does not exist, you MUST populate it with
the benchmark's evaluation dataset.

Read the cloned repo's README, paper references, and source code to understand
how this benchmark's data is structured and where it comes from. Then acquire
the data using whatever method is appropriate — download it, copy it from the
repo, extract it from source code, or generate it using the repo's own scripts.

The goal is to have the actual evaluation tasks/problems available as files in
`benchmark_data_dir` so the collector script in Phase 2 can parse them.

- If acquisition requires authentication, load credentials from a `.env` file
  at the working directory (e.g., HF_TOKEN, KAGGLE_KEY) before downloading.
- Extract any downloaded archives (zip/tar/gz) into `benchmark_data_dir`,
  organize the contents so each task's files live under a self-contained
  per-task location, and ensure each TaskConfig path (task_bundle_path,
  tests_ref, solution_ref) resolves to a real file.

If you cannot obtain the data after investigating the repo, document what you
tried and proceed — but note "insufficient_data" in any output.
{data_acquisition_hint_block}
## Phase 2: Collect evidence

The goal of this phase is to produce a structured inventory of every task in the
benchmark, with clear pointers back to the data you acquired in Phase 1.
The downstream per-task audit agent will rely on these pointers to inspect
individual tasks, their evaluation criteria, and their test/scoring logic.

1. Read the dataclass definitions in {models_path} to understand ArtifactManifest,
   TaskEntry, and TaskConfig schemas.

2. Explore the benchmark data directory (and repo if available) to understand:
   - What constitutes a single "task" or "problem" in this benchmark
   - What the evaluation input (prompt, question, scenario) looks like
   - What the expected/reference answer or success criteria is
   - How tasks are evaluated — what scripts, test harnesses, or scoring
     functions determine correctness

3. Write a Python 3 collector script to: {collector_path}
   - Accept --manifest-path and --task-config-dir CLI arguments
   - Load and parse the benchmark dataset from benchmark_data_dir
   - Discover all tasks/problems in the dataset
   - For each task, extract the fields described below
   - Write a YAML ArtifactManifest to --manifest-path
   - Write per-task TaskConfig JSON files to --task-config-dir/<task_id>/task_config.json
   - Do NOT write EvalConfig files (there are no agent eval runs for this benchmark)

4. Run the collector script:
   python {collector_path} --manifest-path {manifest_path} --task-config-dir {task_config_dir}

You are responsible for both writing AND executing the collector.
The runtime will only validate the outputs afterward.

Benchmark inputs:
- benchmark_name: {config.benchmark_name}
- benchmark_type: {config.benchmark_type}
- job_type: {config.job_type}
- benchmark_data_dir: {config.benchmark_data_dir}
{repo_line}\
{code_url_line}\
- output_root: {output_root}

### TaskConfig field rules

These are the critical fields for downstream task auditing. The per-task audit
agent uses `task_bundle_path`, `tests_ref`, and `solution_ref` to navigate
directly to the relevant files — populate them carefully.

Identity & status (static benchmark — no eval runs):
- status: "unscored"
- n_evals: 0, n_passed: 0, n_failed: 0
- primary_eval_id: null

Task content — link these back to the actual files from Phase 1:
- task_bundle_path: path to the root directory or primary data file for this
  task (e.g. the task's subdirectory in benchmark_data_dir, or the source
  JSON/JSONL file that contains it). This is the entry point for the auditor.
- instruction_text: the full problem/question text for this task (inline it)
- instruction_path: path to the file containing the instruction (if it exists
  as a standalone file), null otherwise
- reference_answer: the gold/expected outcome for this task (inline the text).
  For standard benchmarks this is the correct answer or solution. For
  adversarial/security benchmarks, describe both what a successful attack
  looks like AND what a secure/correct agent response should be — make the
  ground-truth label clear (e.g. "attack succeeds" vs "agent resists"). For
  tasks with complex answers (code, structured output, multi-step reasoning),
  include enough to understand what correct behavior looks like and how it
  is scored.
- solution_ref: path to the reference answer or gold solution file on disk
  (null if the answer is only available inline or not on disk)
- tests_ref: path to the evaluation/test script, scoring function, or test
  harness that determines whether a response to this task is correct. Look in
  the repo for eval scripts, pytest files, grading functions, or judge prompts.
  This is critical — the task auditor needs to understand HOW correctness is
  determined, not just WHAT the answer is. Set to null only if no evaluation
  logic is discoverable.
- audit_notes: free-text guidance for the downstream task audit agent. Write
  this as a handoff note summarizing what you learned while exploring the
  benchmark. Include: how this specific task maps to source data (e.g. which
  file, array index, or key identifies it), where the eval logic for this
  task's eval_type lives in the codebase (file paths and class/function names),
  any benchmark-specific context the auditor needs (e.g. how scoring works,
  what the eval criteria actually check, which parameters are template-resolved
  at runtime). The auditor will read the actual files — your job is to tell
  them WHERE to look and WHAT to look for.
  If the task references external artifacts (images, audio, video, PDFs, or
  any other files the problem statement or reference answer depends on),
  resolve each artifact to its actual on-disk location and list the absolute
  paths under a "Referenced artifacts:" section. The auditor is required to
  read every path in audit_notes, so this is how you make those artifacts
  part of the audit. Do not trust paths stored inside upstream data files
  without verifying they exist — re-resolve against benchmark_data_dir.

ArtifactManifest rules:
- Each TaskEntry must have a task_id and an empty eval_ids list
- source_data_dir: set to benchmark_data_dir

Conventions:
- Emit absolute paths everywhere
- Use yaml.safe_dump(..., sort_keys=False) for the manifest
- Use json.dumps(..., indent=2, sort_keys=True) for TaskConfig
- Prefer deterministic ordering by task_id
- For missing optional fields, use null
- If the dataset is large (>5000 tasks), include all tasks — the downstream
  audit step handles sampling"""
    return prompt


_SWE_BENCH_TEST_DOWNLOAD = """
SWE-bench test file download (REQUIRED for swe_bench benchmark_type):

For each task, download the actual test source files from GitHub so that the
downstream audit agent can inspect the full test code (not just the test_patch diff).

Implementation:
1. Load the task JSON. Read the "repo" (e.g. "astropy/astropy"), "base_commit",
   and the test identifiers from "FAIL_TO_PASS" and "PASS_TO_PASS" lists.
2. Extract unique test file paths by stripping the "::test_name" suffix from each
   test identifier (e.g. "astropy/coordinates/tests/test_intermediate_transformations.py::test_foo"
   becomes "astropy/coordinates/tests/test_intermediate_transformations.py").
   Deduplicate the resulting paths.
3. For each unique test file path, download it from:
     https://raw.githubusercontent.com/{repo}/{base_commit}/{test_file_path}
   Use urllib.request.urlopen (stdlib, no extra deps). If a download fails
   (e.g. 404), log a warning and skip that file — do not abort the whole task.
4. Save the downloaded file to:
     {task_config_dir}/{task_id}/tests/{test_file_path}
   preserving the original directory structure inside the tests/ folder.
5. Set TaskConfig.tests_ref to the absolute path of:
     {task_config_dir}/{task_id}/tests
   (the root tests directory for that task). If no files were successfully
   downloaded, leave tests_ref as null.

This gives the audit agent a local tests_ref directory — the same contract as TB2.
"""


def _swe_bench_test_download_block(config: EvidenceCollectionConfig) -> str:
    if config.benchmark_type == "swe_bench" and config.fetch_test_sources:
        return _SWE_BENCH_TEST_DOWNLOAD
    return ""


def _dirs_block(config: EvidenceCollectionConfig) -> str:
    lines: list[str] = []
    lines.append(f"- source_data_dir: {config.source_data_dir}\n")
    if config.runs_dir:
        lines.append(f"- runs_dir: {config.runs_dir}\n")
    return "".join(lines)
