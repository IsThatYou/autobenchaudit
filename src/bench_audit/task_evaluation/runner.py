from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..agent_cli import AgentCliError, build_agent_request, invoke_structured
from ..progress import ProgressTracker
from ..audit_models import TaskAuditRecord, parse_agent_json_object, task_audit_record_json_schema
from ..audit_protocol import (
    build_agent_add_dirs,
    load_collection_state,
    load_general_rubric,
    resolve_output_root,
    resolve_repo_path,
    task_audit_dir,
)
from ..evidence_collection import EvidenceCollectionConfig, TaskConfig
from ..report import render_audit_report
from .context import EvalArtifactPaths, eval_artifact_paths, select_eval_configs, select_task_configs
from .prompt import render_static_task_audit_prompt, render_task_audit_prompt

AUDIT_MODES = {"trajectory", "static"}


def _resolve_audit_mode(audit_mode: str | None, config: EvidenceCollectionConfig) -> str:
    """Resolve audit mode: explicit value, or auto-detect from benchmark type."""
    if audit_mode is not None:
        if audit_mode not in AUDIT_MODES:
            raise ValueError(f"unsupported audit mode: {audit_mode}")
        return audit_mode
    if config.benchmark_type == "neurips":
        return "static"
    return "trajectory"


def audit_tasks(
    config: EvidenceCollectionConfig,
    general_rubric_path: str | Path | None = None,
    rubric_text_path: str | Path | None = None,
    task_ids: list[str] | None = None,
    include_all: bool = False,
    force: bool = False,
    max_workers: int = 1,
    timeout: int = 800,
    eval_strategy: str = "mixed",
    audit_mode: str | None = None,
    sample_n: int | None = None,
    sample_seed: int = 42,
) -> dict[str, Any]:
    mode = _resolve_audit_mode(audit_mode, config)
    output_root = resolve_output_root(config)
    general_rubric = load_general_rubric(general_rubric_path)
    phase = general_rubric.phase("per_task_evaluation")
    if rubric_text_path:
        rubric_txt_path = Path(rubric_text_path).resolve()
    else:
        rubric_txt_path = resolve_repo_path(phase.rubric).with_suffix(".txt")
    if not rubric_txt_path.exists():
        raise FileNotFoundError(f"rubric text file not found: {rubric_txt_path}")
    rubric_text = rubric_txt_path.read_text()
    collection = load_collection_state(output_root)

    # In static mode, default to auditing all tasks (no pass/fail to filter on).
    task_filter = phase.task_filter or ("all" if mode == "static" else "failed_or_mixed")
    selected_tasks = select_task_configs(
        list(collection.task_configs.values()),
        task_filter=task_filter,
        task_ids=task_ids,
        include_all=include_all,
        sample_n=sample_n,
        sample_seed=sample_seed,
    )

    output_dir = task_audit_dir(output_root, general_rubric, audit_mode=mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    conversation_dir = output_dir / "conversations"
    conversation_dir.mkdir(parents=True, exist_ok=True)
    request = build_agent_request(
        config.agent_cli,
        config.model,
        add_dirs=build_agent_add_dirs(config, output_root),
        api_key_env=config.api_key_env,
    )

    progress = ProgressTracker(
        len(selected_tasks),
        label="Per-task audit",
        info={
            "benchmark": config.benchmark_name,
            "model": config.model or "(default)",
            "agent": config.agent_cli,
            "mode": mode,
            "rubric": str(rubric_txt_path),
            "filter": task_filter,
            "eval_strategy": eval_strategy if mode == "trajectory" else "N/A",
            "sample": f"{sample_n} (seed={sample_seed})" if sample_n else "all",
            "output": str(output_dir),
            "workers": str(max_workers),
            "timeout": f"{timeout}s",
            "force": str(force),
        },
    )

    # Separate cached (skipped) tasks from tasks that need work.
    to_run: list[tuple[Any, Path]] = []  # (task_config, target_path)
    written_paths: list[str] = []
    skipped_tasks: list[str] = []
    for task_config in selected_tasks:
        target_path = output_dir / f"{task_config.task_id}.json"
        if target_path.exists() and not force:
            skipped_tasks.append(task_config.task_id)
            progress.skip(task_config.task_id)
        else:
            to_run.append((task_config, target_path))

    def _process(task_config: Any, target_path: Path) -> tuple[str, Path, TaskAuditRecord]:
        progress.start(task_config.task_id)
        conversation_log_path = conversation_dir / f"{_sanitize_task_id(task_config.task_id)}.json"
        if mode == "static":
            record = _run_single_static_task(
                request, task_config, rubric_text, str(rubric_txt_path), config,
                timeout=timeout, agent_cli=request.agent_cli,
                conversation_log_path=conversation_log_path,
            )
        else:
            eval_configs = collection.eval_configs.get(task_config.task_id, [])
            selected_raw = select_eval_configs(task_config, eval_configs, eval_strategy=eval_strategy)
            selected_paths = [eval_artifact_paths(ec) for ec in selected_raw]
            selected_ids = [ec.eval_id for ec in selected_raw]
            record = _run_single_task(
                request,
                task_config,
                selected_paths,
                selected_ids,
                rubric_text,
                str(rubric_txt_path),
                timeout=timeout,
                agent_cli=request.agent_cli,
                conversation_log_path=conversation_log_path,
            )
        return task_config.task_id, target_path, record

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, tc, tp): tc.task_id for tc, tp in to_run}
        for future in as_completed(futures):
            task_id, target_path, record = future.result()
            is_error = record.overall_judgment == "agent_error"
            record.save_json(target_path)
            written_paths.append(str(target_path))
            progress.done(task_id, error=is_error)

    progress.finish()

    report_name = "audit_report.md" if mode == "trajectory" else "audit_report_static.md"
    report_path = Path(output_root) / report_name
    report_path.write_text(
        render_audit_report(
            output_root,
            general_rubric,
            audit_mode=mode,
            rubric_path=rubric_txt_path,
        )
    )
    return {
        "output_root": str(output_root),
        "task_audit_dir": str(output_dir),
        "report_path": str(report_path),
        "rubric_path": str(rubric_txt_path),
        "audit_mode": mode,
        "selected_tasks": [task.task_id for task in selected_tasks],
        "written_task_audits": written_paths,
        "skipped_tasks": skipped_tasks,
    }


def _run_single_task(
    request: Any,
    task_config: TaskConfig,
    selected_evals: list[EvalArtifactPaths],
    selected_eval_ids: list[str],
    rubric_text: str,
    rubric_path: str,
    timeout: int | None = None,
    agent_cli: str = "claude",
    conversation_log_path: Path | None = None,
) -> TaskAuditRecord:
    try:
        prompt = render_task_audit_prompt(task_config, selected_evals, rubric_text, agent_cli=agent_cli)
        response = invoke_structured(
            request,
            prompt,
            task_audit_record_json_schema(),
            timeout=timeout,
            conversation_log_path=conversation_log_path,
        )
        payload = parse_agent_json_object(response)
        payload["task_id"] = task_config.task_id
        payload["benchmark_name"] = task_config.benchmark_name
        payload["task_status"] = task_config.status
        payload["selected_eval_ids"] = list(selected_eval_ids)
        payload["rubric_path"] = rubric_path
        payload["audit_trajectory_path"] = str(conversation_log_path) if conversation_log_path else None
        return TaskAuditRecord.from_dict(payload)
    except (AgentCliError, ValueError, TypeError, KeyError) as exc:
        return TaskAuditRecord(
            task_id=task_config.task_id,
            benchmark_name=task_config.benchmark_name,
            task_status=task_config.status,
            selected_eval_ids=list(selected_eval_ids),
            rubric_path=rubric_path,
            audit_trajectory_path=str(conversation_log_path) if conversation_log_path else None,
            overall_judgment="agent_error",
            summary=f"Task audit failed before a valid record was produced: {exc}",
            confidence="low",
            findings=[],
        )


def _run_single_static_task(
    request: Any,
    task_config: TaskConfig,
    rubric_text: str,
    rubric_path: str,
    config: EvidenceCollectionConfig,
    timeout: int | None = None,
    agent_cli: str = "claude",
    conversation_log_path: Path | None = None,
) -> TaskAuditRecord:
    task_status = "unscored"  # static mode ignores eval results
    try:
        prompt = render_static_task_audit_prompt(task_config, rubric_text, config, agent_cli=agent_cli)
        response = invoke_structured(
            request,
            prompt,
            task_audit_record_json_schema(),
            timeout=timeout,
            conversation_log_path=conversation_log_path,
        )
        payload = parse_agent_json_object(response)
        payload["task_id"] = task_config.task_id
        payload["benchmark_name"] = task_config.benchmark_name
        payload["task_status"] = task_status
        payload["selected_eval_ids"] = []
        payload["rubric_path"] = rubric_path
        payload["audit_trajectory_path"] = str(conversation_log_path) if conversation_log_path else None
        return TaskAuditRecord.from_dict(payload)
    except (AgentCliError, ValueError, TypeError, KeyError) as exc:
        return TaskAuditRecord(
            task_id=task_config.task_id,
            benchmark_name=task_config.benchmark_name,
            task_status=task_status,
            selected_eval_ids=[],
            rubric_path=rubric_path,
            audit_trajectory_path=str(conversation_log_path) if conversation_log_path else None,
            overall_judgment="agent_error",
            summary=f"Static task audit failed before a valid record was produced: {exc}",
            confidence="low",
            findings=[],
        )


def _sanitize_task_id(task_id: str) -> str:
    sanitized = (
        task_id
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )
    return sanitized or "task"
