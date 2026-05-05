from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .audit_models import TaskAuditRecord
from .audit_protocol import GeneralRubric, task_audit_dir
from .evidence_collection import ArtifactManifest


def render_audit_report(
    output_root: str | Path,
    general_rubric: GeneralRubric,
    audit_mode: str = "trajectory",
    rubric_path: str | Path | None = None,
) -> str:
    root = Path(output_root).resolve()
    manifest = ArtifactManifest.load_yaml(root / "artifact_manifest.yaml")

    task_audit_rows: list[str] = []
    task_audit_counts: dict[str, int] = {}
    task_audits_path = task_audit_dir(root, general_rubric, audit_mode=audit_mode)
    task_audits: dict[str, TaskAuditRecord] = {}
    if task_audits_path.is_dir():
        for record_path in sorted(task_audits_path.glob("*.json")):
            record = TaskAuditRecord.load_json(record_path)
            task_audits[record.task_id] = record
            task_audit_counts[record.overall_judgment] = task_audit_counts.get(record.overall_judgment, 0) + 1

    # Detect audit mode from task records (all unscored = static mode).
    if task_audits:
        all_unscored = all(r.task_status == "unscored" for r in task_audits.values())
        audit_mode = "static" if all_unscored else "trajectory"
    rubric_values = _unique_nonempty_paths(
        [str(rubric_path)] if rubric_path is not None else [record.rubric_path for record in task_audits.values()]
    )
    rubric_summary = ", ".join(f"`{value}`" for value in rubric_values) if rubric_values else "`unknown`"

    for task in manifest.tasks:
        audit_record = task_audits.get(task.task_id)
        task_audit_rows.append(
            "| "
            + " | ".join(
                [
                    task.task_id,
                    audit_record.overall_judgment if audit_record else "not_run",
                    str(len(audit_record.findings)) if audit_record else "0",
                ]
            )
            + " |"
        )

    return "\n".join(
        [
            "# Audit Report",
            "",
            f"- Benchmark: `{manifest.benchmark_name}`",
            f"- Benchmark type: `{manifest.benchmark_type}`",
            f"- Job type: `{manifest.job_type}`",
            f"- Audit mode: `{audit_mode}`",
            f"- Rubric: {rubric_summary}",
            f"- Tasks discovered: `{len(manifest.tasks)}`",
            f"- Task audits written: `{sum(task_audit_counts.values())}`",
            "",
            "## Task Audit Summary",
            "",
            *(f"- `{key}`: `{value}`" for key, value in sorted(task_audit_counts.items())),
            "",
            "| Task | Audit judgment | Findings |",
            "| --- | --- | --- |",
            *(task_audit_rows or ["| none | none | 0 |"]),
            "",
        ]
    )


def _unique_nonempty_paths(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered
