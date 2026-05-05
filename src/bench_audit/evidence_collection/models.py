from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class TaskEntry:
    """Thin index entry in the manifest — just task_id and its eval_ids."""
    task_id: str
    eval_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEntry":
        # Support both flat eval_ids list and rich evals list (with eval_id key).
        raw_eval_ids = data.get("eval_ids")
        if raw_eval_ids is None:
            raw_evals = data.get("evals", [])
            raw_eval_ids = [e["eval_id"] for e in raw_evals if isinstance(e, dict) and "eval_id" in e]
        return cls(
            task_id=str(data.get("task_id") or ""),
            eval_ids=[str(eid) for eid in raw_eval_ids],
        )

    def validate(self) -> None:
        if not self.task_id:
            raise ValueError("task_id is required for every manifest task entry")
        for eval_id in self.eval_ids:
            if not eval_id:
                raise ValueError("eval_ids must be non-empty strings")


@dataclass(slots=True)
class ArtifactManifest:
    """Thin manifest — metadata plus an index of task_ids and their eval_ids.

    All actual data lives in TaskConfig and EvalConfig JSON files.
    """
    manifest_version: int = 2
    benchmark_name: str = ""
    benchmark_type: str = ""
    job_type: str = "actual"
    benchmark_data_dir: str = ""
    source_data_dir: str = ""
    output_root: str = ""
    tasks: list[TaskEntry] = field(default_factory=list)

    def validate(self) -> None:
        if self.manifest_version < 1:
            raise ValueError("manifest_version must be >= 1")
        if not self.benchmark_name:
            raise ValueError("benchmark_name is required")
        if not self.benchmark_type:
            raise ValueError("benchmark_type is required")
        if self.job_type not in {"actual", "oracle"}:
            raise ValueError("job_type must be either 'actual' or 'oracle'")
        if not self.benchmark_data_dir:
            raise ValueError("benchmark_data_dir is required")
        if not self.source_data_dir:
            raise ValueError("source_data_dir is required")
        if not self.output_root:
            raise ValueError("output_root is required")
        for task in self.tasks:
            task.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactManifest":
        tasks = [TaskEntry.from_dict(item) for item in data.get("tasks", [])]
        manifest = cls(
            manifest_version=int(data.get("manifest_version", 2)),
            benchmark_name=str(data.get("benchmark_name") or ""),
            benchmark_type=str(data.get("benchmark_type") or ""),
            job_type=str(data.get("job_type") or "actual"),
            benchmark_data_dir=str(data.get("benchmark_data_dir") or ""),
            source_data_dir=str(data.get("source_data_dir") or ""),
            output_root=str(data.get("output_root") or ""),
            tasks=tasks,
        )
        manifest.validate()
        return manifest

    @classmethod
    def load_yaml(cls, path: str | Path) -> "ArtifactManifest":
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls.from_dict(data)

    def save_yaml(self, path: str | Path) -> None:
        self.validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))


@dataclass(slots=True)
class TaskConfig:
    # Identity & classification
    benchmark_name: str          # e.g. "swe_bench", "tb2"
    benchmark_type: str          # benchmark family; controls evaluation logic
    job_type: str                # "actual" (agent under test) or "oracle" (reference solution)
    task_id: str                 # unique task identifier across the benchmark

    # Aggregate eval statistics (derived from this task's EvalConfigs)
    status: str                  # "passed" if any eval passed, else "failed"
    primary_eval_id: str | None  # eval_id of the best representative eval (prefer passed, then most recent)
    n_evals: int                 # total number of eval runs for this task
    n_passed: int                # how many evals passed
    n_failed: int                # how many evals failed

    # Task content paths (from benchmark data, not from eval runs)
    task_bundle_path: str | None   # root directory or file for the task definition
    instruction_path: str | None   # path to the instruction file (markdown, JSON, etc.)
    instruction_text: str | None   # instruction content for this task, inlined for convenience
    task_toml_path: str | None     # path to task.toml config (tb2 benchmarks only)
    environment_ref: str | None    # path to directory or file with environment setup files (Dockerfile, etc.)
    solution_ref: str | None       # path to directory or file with reference/gold solution or gold answer
    tests_ref: str | None          # path to tests used to verify success for this task — may be a directory of test files (tb2) or a single eval script or test related files (swe-bench)
    reference_answer: str | None    # inlined reference/gold answer (for static benchmarks without eval runs)
    audit_notes: str | None         # collector-generated guidance for the downstream audit agent — how to navigate the task data, where eval logic lives, benchmark-specific context

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskConfig":
        return cls(
            benchmark_name=str(data.get("benchmark_name") or ""),
            benchmark_type=str(data.get("benchmark_type") or ""),
            job_type=str(data.get("job_type") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or ""),
            primary_eval_id=_optional_str(data.get("primary_eval_id")),
            n_evals=int(data.get("n_evals", 0)),
            n_passed=int(data.get("n_passed", 0)),
            n_failed=int(data.get("n_failed", 0)),
            task_bundle_path=_optional_str(data.get("task_bundle_path")),
            instruction_path=_optional_str(data.get("instruction_path")),
            instruction_text=_optional_str(data.get("instruction_text")),
            task_toml_path=_optional_str(data.get("task_toml_path")),
            environment_ref=_optional_str(data.get("environment_ref") or data.get("environment_dir")),
            solution_ref=_optional_str(data.get("solution_ref") or data.get("solution_dir")),
            tests_ref=_optional_str(data.get("tests_ref") or data.get("tests_dir")),
            reference_answer=_optional_str(data.get("reference_answer")),
            audit_notes=_optional_str(data.get("audit_notes")),
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "TaskConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


@dataclass(slots=True)
class EvalConfig:
    # Link to parent task
    task_id: str                 # foreign key — matches TaskConfig.task_id

    # Eval identity
    eval_id: str                 # unique eval run identifier (e.g. "run1", "extract-elf__thfCyBb")
    eval_suffix: str | None      # short suffix portion of eval_id (e.g. "thfCyBb")
    is_primary_eval: bool        # True if this eval matches TaskConfig.primary_eval_id
    status: str                  # "passed" or "failed" — this eval's outcome

    # Eval output paths (produced by the eval/verifier pipeline)
    eval_results_dir: str | None    # root directory containing all outputs for this eval run
    trajectory_path: str | None     # agent conversation/action log (JSON)
    prediction_path: str | None     # agent's final output (patch, code, text)
    stdout_path: str | None         # captured stdout from the eval run
    stderr_path: str | None         # captured stderr from the eval run
    metrics_path: str | None        # path to structured metrics file (e.g. ctrf.json, report.json)
    test_output_path: str | None    # canonical test output file (verifier test results)

    # Eval data
    metrics: dict[str, Any] | list[Any] | None  # inlined content of metrics_path (null if missing/unreadable)
    started_at: str | None       # ISO 8601 timestamp when eval started
    finished_at: str | None      # ISO 8601 timestamp when eval finished
    artifacts: dict[str, str]    # additional named artifact paths (e.g. "result_json", "eval_script", "patch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalConfig":
        metrics = data.get("metrics")
        if metrics is not None and not isinstance(metrics, (dict, list)):
            metrics = None
        return cls(
            task_id=str(data.get("task_id") or ""),
            eval_id=str(data.get("eval_id") or ""),
            eval_suffix=_optional_str(data.get("eval_suffix")),
            is_primary_eval=bool(data.get("is_primary_eval", False)),
            status=str(data.get("status") or ""),
            eval_results_dir=_optional_str(data.get("eval_results_dir") or data.get("job_dir")),
            trajectory_path=_optional_str(data.get("trajectory_path")),
            prediction_path=_optional_str(data.get("prediction_path")),
            stdout_path=_optional_str(data.get("stdout_path")),
            stderr_path=_optional_str(data.get("stderr_path")),
            metrics_path=_optional_str(data.get("metrics_path")),
            test_output_path=_optional_str(data.get("test_output_path")),
            metrics=metrics,
            started_at=_optional_str(data.get("started_at")),
            finished_at=_optional_str(data.get("finished_at")),
            artifacts={str(key): str(value) for key, value in (data.get("artifacts") or {}).items()},
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "EvalConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


def normalize_manifest(manifest: ArtifactManifest) -> ArtifactManifest:
    for task in manifest.tasks:
        task.eval_ids = sorted(set(task.eval_ids))
    manifest.tasks = sorted(manifest.tasks, key=lambda task: task.task_id)
    manifest.manifest_version = max(manifest.manifest_version, 2)
    manifest.validate()
    return manifest


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
