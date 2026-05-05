from __future__ import annotations

from pathlib import Path
from typing import Any

from ..agent_cli import AgentCliError, build_agent_request, invoke_structured
from ..audit_models import (
    BENCHMARK_AUDIT_CATEGORIES,
    BenchmarkAuditRecord,
    CategoryVerdict,
    benchmark_audit_record_json_schema,
    parse_agent_json_object,
)
from ..audit_protocol import (
    benchmark_audit_path,
    build_agent_add_dirs,
    load_general_rubric,
    resolve_output_root,
    resolve_repo_path,
)
from ..evidence_collection import EvidenceCollectionConfig
from .prompt import render_benchmark_audit_prompt


def audit_benchmark(
    config: EvidenceCollectionConfig,
    general_rubric_path: str | Path | None = None,
    rubric_text_path: str | Path | None = None,
    force: bool = False,
    timeout: int = 800,
) -> dict[str, Any]:
    output_root = resolve_output_root(config)
    output_root.mkdir(parents=True, exist_ok=True)

    general_rubric = load_general_rubric(general_rubric_path)
    phase = general_rubric.phase("benchmark_audit")

    if rubric_text_path:
        rubric_txt = Path(rubric_text_path).resolve()
    else:
        rubric_txt = resolve_repo_path(phase.rubric).with_suffix(".txt")
    if not rubric_txt.exists():
        raise FileNotFoundError(f"benchmark rubric text file not found: {rubric_txt}")
    rubric_text = rubric_txt.read_text()

    target_path = benchmark_audit_path(output_root, general_rubric)
    if target_path.exists() and not force:
        print(f"Benchmark audit already exists at {target_path}, skipping (use --force to re-run)")
        return {
            "output_root": str(output_root),
            "benchmark_audit_path": str(target_path),
            "skipped": True,
        }

    add_dirs = _build_benchmark_add_dirs(config, output_root)
    request = build_agent_request(
        config.agent_cli,
        config.model,
        add_dirs=add_dirs,
        api_key_env=config.api_key_env,
    )

    conversation_log_path = output_root / "benchmark_audit_conversation.json"
    record = _run_benchmark_audit(
        request,
        config,
        rubric_text,
        str(rubric_txt),
        timeout=timeout,
        conversation_log_path=conversation_log_path,
    )
    record.save_json(target_path)

    report_path = output_root / "benchmark_audit_report.md"
    report_path.write_text(_render_benchmark_audit_report(record))

    return {
        "output_root": str(output_root),
        "benchmark_audit_path": str(target_path),
        "report_path": str(report_path),
        "rubric_path": str(rubric_txt),
        "overall_judgment": record.overall_judgment,
        "findings_count": len(list(record.findings)),
        "skipped": False,
    }


def _run_benchmark_audit(
    request: Any,
    config: EvidenceCollectionConfig,
    rubric_text: str,
    rubric_path: str,
    timeout: int | None = None,
    conversation_log_path: Path | None = None,
) -> BenchmarkAuditRecord:
    try:
        prompt = render_benchmark_audit_prompt(config, rubric_text, agent_cli=request.agent_cli)
        response = invoke_structured(request, prompt, benchmark_audit_record_json_schema(), timeout=timeout, conversation_log_path=conversation_log_path)
        payload = parse_agent_json_object(response)
        payload["benchmark_name"] = config.benchmark_name
        payload["benchmark_type"] = config.benchmark_type
        payload["domain_categories"] = config.domain_categories or []
        payload["rubric_path"] = rubric_path
        return BenchmarkAuditRecord.from_dict(payload)
    except (AgentCliError, ValueError, TypeError, KeyError) as exc:
        error_msg = f"Benchmark audit failed before a valid record was produced: {exc}"
        error_verdicts = {
            cat: CategoryVerdict(category=cat, severity=0, rationale=error_msg)
            for cat in BENCHMARK_AUDIT_CATEGORIES
        }
        return BenchmarkAuditRecord(
            benchmark_name=config.benchmark_name,
            benchmark_type=config.benchmark_type,
            domain_categories=config.domain_categories or [],
            rubric_path=rubric_path,
            overall_judgment="agent_error",
            summary=error_msg,
            confidence="low",
            category_verdicts=error_verdicts,
        )


def _build_benchmark_add_dirs(config: EvidenceCollectionConfig, output_root: Path) -> list[str]:
    candidates = [str(output_root)]
    if config.benchmark_repo_dir:
        candidates.append(str(Path(config.benchmark_repo_dir).resolve()))
    if config.benchmark_data_dir:
        candidates.append(str(Path(config.benchmark_data_dir).resolve()))
    add_dirs: list[str] = []
    for candidate in candidates:
        resolved = Path(candidate).resolve()
        # Ensure directory exists so --add-dir doesn't fail;
        # the agent will clone/download content into it.
        resolved.mkdir(parents=True, exist_ok=True)
        resolved_str = str(resolved)
        if resolved_str not in add_dirs:
            add_dirs.append(resolved_str)
    return add_dirs


def _render_benchmark_audit_report(record: BenchmarkAuditRecord) -> str:
    lines = [
        "# Benchmark Audit Report",
        "",
        f"- Benchmark: `{record.benchmark_name}`",
        f"- Benchmark type: `{record.benchmark_type}`",
        f"- Domain categories: `{', '.join(record.domain_categories) or 'none'}`",
        f"- Rubric: `{record.rubric_path or 'unknown'}`",
        f"- Overall judgment: `{record.overall_judgment}`",
        f"- Confidence: `{record.confidence}`",
        f"- Total findings: `{len(record.findings)}`",
        "",
        "## Summary",
        "",
        record.summary,
        "",
        "## Category Verdicts",
        "",
        "| Category | Severity | Findings | Rationale |",
        "| --- | --- | --- | --- |",
    ]
    for cat in sorted(record.category_verdicts):
        v = record.category_verdicts[cat]
        lines.append(f"| {cat} | {v.severity} | {len(v.findings)} | {v.rationale} |")

    findings = record.findings
    if findings:
        lines.extend([
            "",
            "## Findings Detail",
            "",
            "| Category | Subtype | Severity | Claim |",
            "| --- | --- | --- | --- |",
        ])
        for f in findings:
            lines.append(f"| {f.category} | {f.subtype} | {f.severity} | {f.claim} |")

    lines.append("")
    return "\n".join(lines)
