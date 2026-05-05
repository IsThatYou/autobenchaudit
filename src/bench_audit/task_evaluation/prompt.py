from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..evidence_collection import EvidenceCollectionConfig, TaskConfig
from .context import EvalArtifactPaths

_PREAMBLE = """\
You are auditing one coding benchmark task to determine whether failures \
(or even passes) reveal defects in the benchmark itself — not in the agent.

Your goal: decide whether the task's prompt, environment, and test suite are fair \
and well-specified. If they are, report no findings. If not, document each defect \
with evidence."""

_WORKFLOW = """
## Workflow
1. Read the rubric below. It defines what counts as a finding, how to distinguish \
agent error from genuine task issues, and the severity scale. Use its examples \
and criteria to guide your judgment.
2. Explore the eval artifacts further below. Open and read every path provided. \
Check them against the rubric and the prompt. \
Do not reason about file contents without reading them first.
3. Ground every claim in what you observed. Cite concrete file paths as evidence. \
If the evidence does not support a benchmark defect, return an empty findings list.

Return exactly one JSON object and nothing else.

Important contract:
- Artifacts are passed as filesystem paths, not inline content. \
You must open and read those files before making claims.
- Distinguish prompt/specification issues from agent issues.
- A finding is a benchmark defect, not an agent mistake. If the agent simply \
wrote wrong code and the task is fair, that is severity 0 with no findings.

"""

_FIELD_GUIDE = """\
- instruction_text: the exact prompt the agent received — this is what you audit \
for clarity and completeness. Check this against the reference solution, tests and \
agent evals to see if the prompt is underspecified or ambiguous.

Per-eval artifact paths (inside each selected_evals entry):
- metrics_path: structured test metrics — pass/fail counts and per-test details.
- test_output_path: raw stdout from the test harness run. Read this to \
see which tests passed/failed and why (assertion errors, tracebacks, etc.).
- prediction_path: the agent's final output (patch, code, or text).
- trajectory_path: the agent's full conversation/action log (JSON) — shows \
reasoning, tool calls, and decisions made during the attempt. Read this to \
understand why the agent succeeded or failed and whether confusion stemmed \
from benchmark defects.

Task-level paths (present when available):
- tests_ref: the test suite used to evaluate solutions — may be a directory of test \
files or a single eval script. Read these to check if tests are fair, narrow, or \
misaligned with the prompt.
- environment_ref: files placed in the container before the agent starts (starter \
code, data files, configs). Check for mismatches with what the prompt describes.
- solution_ref: the reference/gold solution. Compare against agent output to \
understand what was expected.
- task_bundle_path: JSON file containing the task definition \
(e.g. SWE-bench problem_statement, repo, patch, test_patch). Shown when \
tests_ref/environment_ref/solution_ref are not all available."""

_CURSOR_SCHEMA = {
    "task_id": "string",
    "benchmark_name": "string",
    "task_status": "passed|failed",
    "selected_eval_ids": ["string"],
    "overall_judgment": "audit_complete|insufficient_evidence|agent_error",
    "summary": "string",
    "confidence": "low|medium|high",
    "findings": [
        {
            "finding_id": "string",
            "category": "ambiguity|environment|test_quality",
            "subtype": "string describing the specific finding",
            "severity": "integer matching the rubric's severity scale",
            "claim": "string",
            "why_it_matters": "string",
            "evidence": [{"path": "string", "note": "string"}],
            "suggested_fix": "string",
        }
    ],
}


def _strip_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none(item) for item in obj]
    return obj


def _task_level_paths(task_config: TaskConfig) -> dict[str, str]:
    """Build task-level path dict.

    Always includes tests_ref, environment_ref, solution_ref when available.
    Includes task_bundle_path only when the three refs are not all present.
    """
    paths: dict[str, str] = {}
    has_all_refs = True
    for key in ("tests_ref", "environment_ref", "solution_ref"):
        val = getattr(task_config, key, None)
        if val:
            paths[key] = val
        else:
            has_all_refs = False
    if not has_all_refs and task_config.task_bundle_path:
        paths["task_bundle_path"] = task_config.task_bundle_path
    if task_config.audit_notes:
        paths["audit_notes"] = task_config.audit_notes
    return paths


def render_task_audit_prompt(
    task_config: TaskConfig,
    selected_evals: list[EvalArtifactPaths],
    rubric_text: str,
    agent_cli: str = "claude",
) -> str:
    parts = [_PREAMBLE]
    parts.append(_WORKFLOW)
    parts.append(f"\n## Per-task rubric\n{rubric_text}")

    if agent_cli == "cursor":
        parts.append(f"\nOutput schema:\n{json.dumps(_CURSOR_SCHEMA, indent=2)}")

    parts.append(f"\n## Evals artifacts field guide\n{_FIELD_GUIDE}")

    prompt_context: dict[str, Any] = {
        "task_id": task_config.task_id,
        "instruction_text": task_config.instruction_text,
        "selected_evals": [asdict(e) for e in selected_evals],
        **_task_level_paths(task_config),
    }
    prompt_context = _strip_none(prompt_context)
    parts.append(f"\n## Evals artifacts\n{json.dumps(prompt_context, indent=2)}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Static audit prompt (no trajectories / eval artifacts)
# ---------------------------------------------------------------------------

_STATIC_PREAMBLE = """\
You are auditing one benchmark task WITHOUT execution artifacts — no agent \
trajectories, test outputs, or eval run data. Your goal: determine whether \
the task's problem statement, reference answer, and evaluation logic are \
well-specified and fair.

If they are, report no findings. If not, document each defect with evidence."""

_STATIC_WORKFLOW = """
## Workflow
1. Read the rubric below. It defines what counts as a finding, the \
severity scale, and the distinction between benchmark defects and expected \
difficulty.
2. Read the problem statement and reference answer provided below.
3. If a benchmark repository or eval code is available (paths below), \
open and inspect the evaluation scripts, test harness, and scoring logic \
for fairness and correctness.
4. Ground every claim in what you observed. Cite concrete file paths or \
inline content as evidence. If the evidence does not support a benchmark \
defect, return an empty findings list.

Return exactly one JSON object and nothing else.

Important contract:
- You are auditing the benchmark task itself, not any model's performance.
- A finding is a defect in the task's definition, reference answer, or \
evaluation logic — not normal difficulty or expected domain knowledge.
- If `audit_notes` contains any filesystem paths (e.g. reference inputs, \
gold deliverables, rubric files, eval scripts), those paths are a critical \
part of the audit. You MUST open and read through every such path before \
forming conclusions. Do not reason about their contents based on filenames, \
directory listings, or the notes alone — read the files. This applies to \
PDFs, ZIPs, code directories, and any other artifact referenced by path.
"""

_STATIC_FIELD_GUIDE = """\
- instruction_text: the exact problem/question text — audit this for \
clarity and completeness.
- reference_answer: the gold/reference answer — check this for correctness, \
completeness, and whether alternative valid answers exist.

Task-level paths (present when available):
- solution_ref: path to reference solution file(s). Compare against \
reference_answer to check consistency.
- tests_ref: path to test/eval scripts. Inspect for fairness, narrowness, \
or misalignment with the problem statement.
- benchmark_repo_dir: root of the benchmark repository. Explore eval code, \
scoring scripts, and data loading logic.
- benchmark_data_dir: root of the dataset. Inspect data files if needed \
to verify task content.
- task_bundle_path: path to the source data file or directory for this task \
(e.g. the original JSON entry, task subdirectory). When solution_ref is null, \
this is the best place to find the raw task definition including structured \
eval criteria, scoring parameters, and the original reference answer.
- audit_notes: guidance from the evidence collector about how to navigate \
this task's data — where the eval logic lives, how the task maps to source \
data, and benchmark-specific context. Use this as a starting point, but \
verify claims by reading the actual files. If the notes list filesystem \
paths (reference inputs, gold deliverables, rubric files, etc.), treat \
those as required reading — open and read every one before drawing \
conclusions."""


def render_static_task_audit_prompt(
    task_config: TaskConfig,
    rubric_text: str,
    config: EvidenceCollectionConfig,
    agent_cli: str = "claude",
) -> str:
    parts = [_STATIC_PREAMBLE]
    parts.append(_STATIC_WORKFLOW)
    parts.append(f"\n## Per-task rubric\n{rubric_text}")

    if agent_cli == "cursor":
        parts.append(f"\nOutput schema:\n{json.dumps(_CURSOR_SCHEMA, indent=2)}")

    parts.append(f"\n## Artifacts field guide\n{_STATIC_FIELD_GUIDE}")

    prompt_context: dict[str, Any] = {
        "task_id": task_config.task_id,
        "instruction_text": task_config.instruction_text,
        "reference_answer": task_config.reference_answer,
    }
    # Add available task-level paths and audit notes
    for key in ("solution_ref", "tests_ref", "task_bundle_path", "audit_notes"):
        val = getattr(task_config, key, None)
        if val:
            prompt_context[key] = val
    if config.benchmark_repo_dir:
        prompt_context["benchmark_repo_dir"] = config.benchmark_repo_dir
    if config.benchmark_data_dir:
        prompt_context["benchmark_data_dir"] = config.benchmark_data_dir

    prompt_context = _strip_none(prompt_context)
    parts.append(f"\n## Task artifacts\n{json.dumps(prompt_context, indent=2)}")

    return "\n".join(parts)
