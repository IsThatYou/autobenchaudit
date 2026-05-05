from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .evidence_collection import ArtifactManifest, EvalConfig, EvidenceCollectionConfig, TaskConfig, TaskEntry
from .evidence_collection.runner import TaskConfigDirResolver

PHASE_ORDER = ["benchmark_audit", "evidence_collection", "per_task_evaluation"]
TASK_FILTERS = {"failed_or_mixed", "all"}


@dataclass(slots=True)
class PhaseDefinition:
    enabled: bool
    rubric: str | None = None
    output_dir: str | None = None
    output_file: str | None = None
    task_filter: str | None = None
    requires: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhaseDefinition":
        phase = cls(
            enabled=bool(data.get("enabled", False)),
            rubric=_optional_str(data.get("rubric")),
            output_dir=_optional_str(data.get("output_dir")),
            output_file=_optional_str(data.get("output_file")),
            task_filter=_optional_str(data.get("task_filter")),
            requires=[str(item) for item in data.get("requires", [])],
        )
        phase.validate()
        return phase

    def validate(self) -> None:
        if self.task_filter is not None and self.task_filter not in TASK_FILTERS:
            raise ValueError(f"unsupported phase task_filter: {self.task_filter}")
        if self.output_dir is not None:
            output_path = Path(self.output_dir)
            if output_path.is_absolute() or ".." in output_path.parts:
                raise ValueError("phase output_dir must be a relative path inside the audit run")


@dataclass(slots=True)
class GeneralRubric:
    version: str
    phases: dict[str, PhaseDefinition]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeneralRubric":
        version = str(data.get("version") or "")
        phases = {
            str(name): PhaseDefinition.from_dict(phase_data)
            for name, phase_data in (data.get("phases") or {}).items()
        }
        rubric = cls(version=version, phases=phases)
        rubric.validate()
        return rubric

    def validate(self) -> None:
        if not self.version:
            raise ValueError("general rubric version is required")
        missing = [phase for phase in PHASE_ORDER if phase not in self.phases]
        if missing:
            raise ValueError(f"general rubric is missing phases: {', '.join(missing)}")
        for phase_name, phase in self.phases.items():
            phase.validate()
            for requirement in phase.requires:
                if requirement not in self.phases:
                    raise ValueError(f"phase {phase_name} requires unknown phase {requirement}")

    def phase(self, phase_name: str) -> PhaseDefinition:
        if phase_name not in self.phases:
            raise ValueError(f"unknown phase: {phase_name}")
        return self.phases[phase_name]


@dataclass(slots=True)
class CollectionState:
    output_root: Path
    manifest: ArtifactManifest
    task_configs: dict[str, TaskConfig]
    eval_configs: dict[str, list[EvalConfig]]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_output_root(config: EvidenceCollectionConfig) -> Path:
    audit_run_dir = os.environ.get("AUDIT_RUN_DIR", "").strip()
    if not audit_run_dir:
        raise ValueError("AUDIT_RUN_DIR must be set")
    return (
        Path(audit_run_dir).resolve()
        / _sanitize_dir_part(config.benchmark_type)
        / _build_output_dir_name(config)
    ).resolve()


def build_agent_add_dirs(config: EvidenceCollectionConfig, output_root: Path) -> list[str]:
    candidates = [str(output_root)]
    if config.benchmark_data_dir:
        candidates.append(str(Path(config.benchmark_data_dir).resolve()))
    if config.source_data_dir:
        candidates.append(str(Path(config.source_data_dir).resolve()))
    if config.runs_dir:
        candidates.append(str(Path(config.runs_dir).resolve()))
    if config.benchmark_repo_dir:
        candidates.append(str(Path(config.benchmark_repo_dir).resolve()))
    add_dirs: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        resolved = str(Path(candidate).resolve())
        if resolved not in add_dirs:
            add_dirs.append(resolved)
    return add_dirs


def resolve_repo_path(path: str | None) -> Path:
    if not path:
        raise ValueError("rubric path is not configured")
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root() / candidate
    return candidate.resolve()


def _build_output_dir_name(config: EvidenceCollectionConfig) -> str:
    return "__".join(
        [
            _sanitize_dir_part(config.benchmark_name),
            _sanitize_dir_part(config.output_subdir),
            _sanitize_dir_part(config.job_type),
        ]
    )


def _sanitize_dir_part(value: str) -> str:
    sanitized = value.strip().replace(os.sep, "-").replace(" ", "-")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    return sanitized or "run"


def default_general_rubric_path() -> Path:
    return repo_root() / "rubrics" / "general_rubric.yaml"


def load_general_rubric(path: str | Path | None = None) -> GeneralRubric:
    target = Path(path or default_general_rubric_path()).resolve()
    data = load_yaml_mapping(target)
    return GeneralRubric.from_dict(data)


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    target = Path(path).resolve()
    data = yaml.safe_load(target.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{target} must contain a top-level mapping")
    return data


def resolve_phase_sequence(
    general_rubric: GeneralRubric,
    start_phase: str,
    end_phase: str,
) -> list[str]:
    if start_phase not in PHASE_ORDER:
        raise ValueError(f"unsupported start phase: {start_phase}")
    if end_phase not in PHASE_ORDER:
        raise ValueError(f"unsupported end phase: {end_phase}")
    start_index = PHASE_ORDER.index(start_phase)
    end_index = PHASE_ORDER.index(end_phase)
    if start_index > end_index:
        raise ValueError("start_phase must come before end_phase")
    selected = PHASE_ORDER[start_index : end_index + 1]
    for phase_name in selected:
        phase = general_rubric.phase(phase_name)
        if not phase.enabled:
            raise ValueError(f"phase {phase_name} is disabled in the general rubric")
        for requirement in phase.requires:
            if requirement not in selected and PHASE_ORDER.index(requirement) < start_index:
                continue
            if requirement not in selected:
                raise ValueError(f"phase {phase_name} requires phase {requirement}")
    return selected


def load_collection_state(output_root: str | Path) -> CollectionState:
    root = Path(output_root).resolve()
    manifest = ArtifactManifest.load_yaml(root / "artifact_manifest.yaml")
    task_configs: dict[str, TaskConfig] = {}
    eval_configs: dict[str, list[EvalConfig]] = {}
    task_configs_root = root / "task_configs"
    resolver = TaskConfigDirResolver(task_configs_root)
    for task in manifest.tasks:
        task_dir = resolver.resolve(task.task_id)
        task_config = TaskConfig.load_json(task_dir / "task_config.json")
        canonical_task_id = task_config.task_id
        if canonical_task_id in task_configs:
            raise ValueError(f"duplicate task config id in collection state: {canonical_task_id}")
        task_configs[canonical_task_id] = task_config
        eval_configs[canonical_task_id] = [
            EvalConfig.load_json(task_dir / f"{eval_id}.json")
            for eval_id in task.eval_ids
        ]
    return CollectionState(output_root=root, manifest=manifest, task_configs=task_configs, eval_configs=eval_configs)


def benchmark_audit_path(output_root: str | Path, general_rubric: GeneralRubric) -> Path:
    phase = general_rubric.phase("benchmark_audit")
    filename = phase.output_file or "benchmark_audit.json"
    return Path(output_root).resolve() / filename


def task_audit_dir(output_root: str | Path, general_rubric: GeneralRubric, audit_mode: str = "trajectory") -> Path:
    phase = general_rubric.phase("per_task_evaluation")
    if not phase.output_dir:
        raise ValueError("per_task_evaluation.output_dir is not configured")
    dirname = phase.output_dir if audit_mode == "trajectory" else f"{phase.output_dir}_static"
    return Path(output_root).resolve() / dirname


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


