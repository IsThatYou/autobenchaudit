from __future__ import annotations

import json
from typing import Any

from ..audit_models import BENCHMARK_AUDIT_CATEGORIES
from ..evidence_collection import EvidenceCollectionConfig

_PREAMBLE = """\
You are auditing a benchmark as a whole to assess its quality, methodology, \
and fitness for evaluating AI systems.

Your goal: determine whether the benchmark is well-constructed, documented, \
reproducible, and free of contamination or methodological issues. \
If it is, report no findings. If not, document each defect with evidence."""

_WORKFLOW = """
## Workflow
1. Read the rubric below. It defines what counts as a finding, how to assess \
benchmark quality, and the severity scale.
2. Clone the benchmark repository if it is not already available locally \
(see Instructions below for the exact command). Then explore it thoroughly. \
Open and read files before making claims — do not guess at file contents.
3. If a paper is provided (`paper_path`), read it — it is a key source for \
assessing methodology, dataset construction, and evaluation design.
4. You MUST produce a verdict for EVERY category in the rubric — even categories \
where you find no issues. For those, set severity to 0 and write a rationale \
explaining why the category is clean. This forces thorough coverage.
5. Every finding MUST carry a `subtype` field equal to one of the subtype codes \
defined in the rubric for that category (e.g., D1, D2, D3, D4 for documentation; \
C1...C4 for contamination; etc.). Pick the closest match. If a finding does not \
fit any subtype, do not invent a new code — re-evaluate whether it belongs in this \
category at all.
6. Ground every claim in what you observed. Cite concrete file paths as evidence.

Important contract:
- You are auditing the benchmark itself, not any particular model's performance.
- A finding is a defect in the benchmark's design, documentation, methodology, \
or dataset — not a limitation that the authors already acknowledge and scope.

## Output format
Return exactly one JSON object and nothing else.
"""

_VERDICT_TEMPLATE = {
    "severity": "integer matching the rubric's severity scale (max across findings, or 0 if clean)",
    "rationale": "string (why this category is clean or what issues exist)",
    "findings": [
        {
            "subtype": "string (the rubric subtype code this finding maps to, e.g., D2, C1, M3, Q4, R5, I2 — must come from the rubric's Subtypes section for this category)",
            "severity": "integer matching the rubric's severity scale",
            "claim": "string",
            "why_it_matters": "string",
            "evidence": [{"path": "string", "note": "string"}],
            "suggested_fix": "string",
        }
    ],
}

_CURSOR_SCHEMA = {
    "overall_judgment": "audit_complete|insufficient_evidence|agent_error",
    "summary": "string",
    "confidence": "low|medium|high",
    "category_verdicts": {
        cat: _VERDICT_TEMPLATE for cat in sorted(BENCHMARK_AUDIT_CATEGORIES)
    },
}


def render_benchmark_audit_prompt(
    config: EvidenceCollectionConfig,
    rubric_text: str,
    agent_cli: str = "claude",
) -> str:
    parts = [_PREAMBLE]
    parts.append(_WORKFLOW)

    context: dict[str, Any] = {
        "benchmark_name": config.benchmark_name,
        "benchmark_type": config.benchmark_type,
    }
    if config.domain_categories:
        context["domain_categories"] = config.domain_categories
    if config.benchmark_repo_dir:
        context["benchmark_repo_dir"] = config.benchmark_repo_dir
    if config.benchmark_data_dir:
        context["benchmark_data_dir"] = config.benchmark_data_dir
    if config.paper_path:
        context["paper_path"] = config.paper_path
    if config.dataset_id:
        context["dataset_id"] = config.dataset_id
    if config.code_url:
        context["code_url"] = config.code_url

    parts.append(f"\n## Benchmark context\n{json.dumps(context, indent=2)}")

    parts.append(
        "\n## Instructions\n"
        "Before auditing, ensure the benchmark repository is available locally.\n"
        "1. If `code_url` is provided and `benchmark_repo_dir` is empty or does not "
        "exist, clone the repository: "
        "`mkdir -p <benchmark_repo_dir> && git clone --depth 1 <code_url> <benchmark_repo_dir>`.\n"
        "2. If `paper_path` is not provided or the file does not exist, check the "
        "repo's README for an arXiv link or paper URL. If found, download the PDF "
        "to `<benchmark_repo_dir>/../paper.pdf`.\n"
        "3. Once the repository is cloned, explore it thoroughly. "
        "Read the README, eval scripts, dataset construction code, test suites, "
        "and any paper or documentation.\n"
        "4. Assess the benchmark against each rubric category and report your findings."
    )

    parts.append(f"\n## Benchmark audit rubric\n{rubric_text}")

    if agent_cli == "cursor":
        parts.append(f"\nOutput schema:\n{json.dumps(_CURSOR_SCHEMA, indent=2)}")

    return "\n".join(parts)
