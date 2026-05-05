from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def generate_trajectories(
    harbor_config: Path,
    benchmark_type: str,
    agent_cli: str,
    model: str,
    dataset: str | None = None,
    download_dir: Path | None = None,
    save_dir: Path | None = None,
    jobs_type: str = "actual",
) -> Path:
    """Run Harbor to generate trajectories and emit a collection config."""

    harbor_data = yaml.safe_load(harbor_config.read_text())
    harbor_jobs_dir = Path(harbor_data["jobs_dir"])

    # Patch dataset fields if overrides provided.
    if download_dir and Path(download_dir).is_dir():
        # Local dataset: use Harbor's `path` field instead of registry lookup.
        ds = harbor_data["datasets"][0]
        ds.pop("name", None)
        ds.pop("version", None)
        ds.pop("registry_path", None)
        ds.pop("download_dir", None)
        ds["path"] = str(download_dir)
    else:
        if dataset:
            harbor_data["datasets"][0]["name"] = dataset
            harbor_data["datasets"][0].pop("version", None)
        if download_dir:
            harbor_data["datasets"][0]["download_dir"] = str(download_dir)

    effective_download_dir = harbor_data["datasets"][0].get("path") or harbor_data["datasets"][0].get("download_dir", "")

    # Write patched config to a temp file.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    tmp_config = Path(tmp_path)
    try:
        tmp_config.write_text(yaml.dump(harbor_data, default_flow_style=False, sort_keys=False))

        # Snapshot existing subdirs so we can find the new one after harbor run.
        existing = set(p.name for p in harbor_jobs_dir.iterdir()) if harbor_jobs_dir.is_dir() else set()

        print(f"Running harbor with config {harbor_config} …", flush=True)
        result = subprocess.run(
            ["harbor", "run", "-c", str(tmp_config)],
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"harbor run failed with exit code {result.returncode}")
    finally:
        tmp_config.unlink(missing_ok=True)

    # Discover the newly created timestamped directory.
    current = set(p.name for p in harbor_jobs_dir.iterdir()) if harbor_jobs_dir.is_dir() else set()
    new_dirs = current - existing
    if not new_dirs:
        raise SystemExit("No new directory found under jobs_dir after harbor run")
    if len(new_dirs) > 1:
        new_dir_name = sorted(new_dirs)[-1]
    else:
        new_dir_name = new_dirs.pop()

    discovered_jobs_dir = harbor_jobs_dir / new_dir_name
    name = dataset if dataset else benchmark_type
    benchmark_data_dir = str(save_dir / name) if save_dir else effective_download_dir

    # Write collection config.
    collection = {
        "benchmark_name": name,
        "benchmark_type": benchmark_type,
        "agent_cli": agent_cli,
        "model": model,
        "output_subdir": f"{benchmark_type}_collection",
        "benchmark_data_dir": benchmark_data_dir,
        "jobs_dir": str(discovered_jobs_dir),
        "jobs_type": jobs_type,
    }

    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / "configs" / "harbor"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"collection_{name}.yaml"
    out_path.write_text(yaml.dump(collection, default_flow_style=False, sort_keys=False))

    print(f"Collection config written to {out_path}", file=sys.stderr)
    print(str(out_path))
    return out_path
