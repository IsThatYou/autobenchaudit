from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class EvidenceCollectionConfig:
    benchmark_name: str
    benchmark_type: str
    agent_cli: str
    output_subdir: str
    benchmark_data_dir: str
    jobs_type: str = "actual"
    model: str | None = None
    jobs_dir: str | None = None
    results_dir: str | None = None
    runs_dir: str | None = None
    api_key_env: str | None = None
    fetch_test_sources: bool = False
    # Phase 0 — benchmark audit fields (optional)
    benchmark_repo_dir: str | None = None
    paper_path: str | None = None
    domain_categories: list[str] | None = None
    dataset_id: str | None = None
    code_url: str | None = None
    data_acquisition_hint: str | None = None

    def validate(self) -> None:
        if not self.benchmark_name:
            raise ValueError("benchmark_name is required")
        if self.benchmark_type not in {"tb2", "swe_bench", "neurips"}:
            raise ValueError("benchmark_type must be one of: tb2, swe_bench, neurips")
        if not self.agent_cli:
            raise ValueError("agent_cli is required")
        if not self.output_subdir.strip():
            raise ValueError("output_subdir is required")
        if Path(self.output_subdir).is_absolute():
            raise ValueError("output_subdir must be a relative path")
        if ".." in Path(self.output_subdir).parts:
            raise ValueError("output_subdir must not contain '..'")
        if not self.benchmark_data_dir:
            raise ValueError("benchmark_data_dir is required")
        if self.jobs_type not in {"actual", "oracle"}:
            raise ValueError("jobs_type must be either 'actual' or 'oracle'")
        if self.benchmark_type == "tb2" and not self.jobs_dir:
            raise ValueError("jobs_dir is required for tb2 configs")
        if self.benchmark_type == "swe_bench" and not self.results_dir:
            raise ValueError("results_dir is required for swe_bench configs")

    @property
    def job_type(self) -> str:
        return self.jobs_type

    @property
    def source_data_dir(self) -> str:
        if self.benchmark_type == "tb2":
            return str(self.jobs_dir)
        if self.benchmark_type == "neurips":
            return str(self.benchmark_data_dir)
        return str(self.results_dir)


def load_collection_config(path: str | Path) -> EvidenceCollectionConfig:
    config_path = Path(path).resolve()
    data = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{config_path} must contain a top-level mapping")

    config = EvidenceCollectionConfig(
        benchmark_name=str(data["benchmark_name"]),
        benchmark_type=str(data["benchmark_type"]),
        agent_cli=str(data["agent_cli"]),
        output_subdir=str(data["output_subdir"]),
        benchmark_data_dir=_resolve_path(config_path.parent, data["benchmark_data_dir"]),
        jobs_type=str(data.get("jobs_type", "actual")),
        model=str(data["model"]) if data.get("model") is not None else None,
        jobs_dir=_resolve_optional_path(config_path.parent, data.get("jobs_dir")),
        results_dir=_resolve_optional_path(config_path.parent, data.get("results_dir")),
        runs_dir=_resolve_optional_path(config_path.parent, data.get("runs_dir")),
        api_key_env=str(data["api_key_env"]) if data.get("api_key_env") else None,
        fetch_test_sources=bool(data.get("fetch_test_sources", False)),
        benchmark_repo_dir=_resolve_optional_path(config_path.parent, data.get("benchmark_repo_dir")),
        paper_path=_resolve_optional_path(config_path.parent, data.get("paper_path")),
        domain_categories=data.get("domain_categories"),
        dataset_id=str(data["dataset_id"]) if data.get("dataset_id") else None,
        code_url=str(data["code_url"]) if data.get("code_url") else None,
        data_acquisition_hint=str(data["data_acquisition_hint"]) if data.get("data_acquisition_hint") else None,
    )
    config.validate()
    return config


def _resolve_optional_path(base: Path, value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _resolve_path(base, text)


def _resolve_path(base: Path, value: object) -> str:
    expanded = os.path.expandvars(str(value))
    candidate = Path(expanded).expanduser()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return str(candidate)
