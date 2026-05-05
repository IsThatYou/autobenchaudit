from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..agent_cli import build_agent_request, invoke_text
from .config import EvidenceCollectionConfig
from .models import (
    ArtifactManifest,
    TaskConfig,
    normalize_manifest,
)
from .prompt import render_collect_prompt


def collect_evidence(
    config: EvidenceCollectionConfig,
    force: bool = False,
) -> dict[str, Any]:
    config.validate()
    output_root = resolve_output_root(config)
    layout = ensure_output_layout(output_root)
    collector_path = layout["collector"] / "collect_evidence.py"
    manifest_path = layout["root"] / "artifact_manifest.yaml"
    report_path = layout["root"] / "collection_report.md"

    prompt = render_collect_prompt(
        config,
        str(output_root),
        str(collector_path),
        str(manifest_path),
        str(layout["task_configs"]),
    )
    request = build_agent_request(
        config.agent_cli,
        config.model,
        add_dirs=build_agent_add_dirs(config, output_root),
        api_key_env=config.api_key_env,
    )
    invoke_text(
        request,
        prompt,
        conversation_log_path=layout["root"] / "evidence_collection_conversation.json",
    )

    manifest = normalize_manifest(ArtifactManifest.load_yaml(manifest_path))
    manifest.save_yaml(manifest_path)

    task_configs = _load_task_configs(layout["task_configs"], manifest)
    _validate_eval_configs(layout["task_configs"], manifest)

    _write_text(report_path, _collection_report(manifest, task_configs), force=True)
    return {
        "collector_path": str(collector_path),
        "manifest_path": str(manifest_path),
        "task_config_dir": str(layout["task_configs"]),
        "report_path": str(report_path),
        "output_root": str(output_root),
    }


def _load_task_configs(task_config_dir: Path, manifest: ArtifactManifest) -> dict[str, TaskConfig]:
    resolver = TaskConfigDirResolver(task_config_dir)
    configs: dict[str, TaskConfig] = {}
    for task in manifest.tasks:
        task_dir = resolver.resolve(task.task_id)
        path = task_dir / "task_config.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Agent did not generate TaskConfig for task {task.task_id}: expected {path}"
            )
        configs[task.task_id] = TaskConfig.load_json(path)
    return configs


def _validate_eval_configs(task_config_dir: Path, manifest: ArtifactManifest) -> None:
    resolver = TaskConfigDirResolver(task_config_dir)
    for task in manifest.tasks:
        task_dir = resolver.resolve(task.task_id)
        for eval_id in task.eval_ids:
            path = task_dir / f"{eval_id}.json"
            if not path.exists():
                raise FileNotFoundError(
                    f"Agent did not generate EvalConfig for eval {eval_id}: expected {path}"
                )


def resolve_output_root(config: EvidenceCollectionConfig) -> Path:
    audit_run_dir = os.environ.get("AUDIT_RUN_DIR", "").strip()
    if not audit_run_dir:
        raise ValueError("AUDIT_RUN_DIR must be set")
    return (
        Path(audit_run_dir).resolve()
        / _sanitize_dir_part(config.benchmark_type)
        / build_output_dir_name(config)
    ).resolve()


def build_output_dir_name(config: EvidenceCollectionConfig) -> str:
    return "__".join(
        [
            _sanitize_dir_part(config.benchmark_name),
            _sanitize_dir_part(config.output_subdir),
            _sanitize_dir_part(config.job_type),
        ]
    )


def build_agent_add_dirs(config: EvidenceCollectionConfig, output_root: Path) -> list[str]:
    candidates = [
        str(output_root),
    ]
    if config.benchmark_data_dir:
        candidates.append(str(Path(config.benchmark_data_dir).resolve()))
    if config.source_data_dir:
        candidates.append(str(Path(config.source_data_dir).resolve()))
    if config.runs_dir:
        candidates.append(str(Path(config.runs_dir).resolve()))

    add_dirs: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        resolved = str(Path(candidate).resolve())
        if resolved not in add_dirs:
            add_dirs.append(resolved)
    return add_dirs


def ensure_output_layout(output_root: str | Path) -> dict[str, Path]:
    root = Path(output_root).resolve()
    layout = {
        "root": root,
        "collector": root / "collector",
        "task_configs": root / "task_configs",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


def _sanitize_dir_part(value: str) -> str:
    sanitized = value.strip().replace(os.sep, "-").replace(" ", "-")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    return sanitized or "run"


class TaskConfigDirResolver:
    def __init__(self, task_configs_root: Path) -> None:
        self.root = Path(task_configs_root)
        self._index: dict[str, Path] | None = None

    def resolve(self, task_id: str) -> Path:
        for candidate in _task_dir_candidates(task_id):
            task_dir = self.root / candidate
            if task_dir.is_dir() and (task_dir / "task_config.json").exists():
                return task_dir
        if self._index is None:
            self._index = _build_task_dir_index(self.root)
        mapped = self._index.get(task_id)
        if mapped is not None and (mapped / "task_config.json").exists():
            return mapped
        tried = ", ".join(
            str(self.root / candidate / "task_config.json")
            for candidate in _task_dir_candidates(task_id)
        )
        raise FileNotFoundError(
            f"task_config.json not found for task_id {task_id!r}; tried: {tried}"
        )


def _task_dir_candidates(task_id: str) -> list[str]:
    candidates = [task_id]

    underscore_sanitized = (
        task_id
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )
    if underscore_sanitized not in candidates:
        candidates.append(underscore_sanitized)

    legacy_sanitized = task_id.replace("/", "__").replace("\\", "__")
    if legacy_sanitized not in candidates:
        candidates.append(legacy_sanitized)

    return candidates


def _build_task_dir_index(task_configs_root: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    if not task_configs_root.is_dir():
        return mapping
    for child in sorted(task_configs_root.iterdir()):
        if not child.is_dir():
            continue
        config_path = child / "task_config.json"
        if not config_path.exists():
            continue
        try:
            data = json.loads(config_path.read_text())
        except (OSError, ValueError):
            continue
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if isinstance(task_id, str):
            mapping.setdefault(task_id, child)
    return mapping


def _write_text(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _collection_report(manifest: ArtifactManifest, task_configs: dict[str, TaskConfig]) -> str:
    task_rows: list[str] = []
    total_evals = 0
    for task in manifest.tasks:
        tc = task_configs.get(task.task_id)
        total_evals += len(task.eval_ids)
        if tc:
            task_rows.append(
                "| "
                + " | ".join(
                    [
                        task.task_id,
                        tc.status,
                        str(tc.n_evals),
                        str(tc.n_passed),
                        str(tc.n_failed),
                        tc.primary_eval_id or "none",
                    ]
                )
                + " |"
            )
        else:
            task_rows.append(f"| {task.task_id} | unknown | {len(task.eval_ids)} | ? | ? | none |")

    return "\n".join(
        [
            "# Collection Report",
            "",
            f"- Benchmark: `{manifest.benchmark_name}`",
            f"- Benchmark type: `{manifest.benchmark_type}`",
            f"- Job type: `{manifest.job_type}`",
            f"- Benchmark data: `{manifest.benchmark_data_dir}`",
            f"- Source data: `{manifest.source_data_dir}`",
            f"- Tasks discovered: `{len(manifest.tasks)}`",
            f"- Evals discovered: `{total_evals}`",
            "",
            "| Task | Status | Evals | Passed | Failed | Primary eval |",
            "| --- | --- | --- | --- | --- | --- |",
            *task_rows,
            "",
        ]
    )
