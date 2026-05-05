from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def read_text(path: str | Path | None) -> str | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None
    return target.read_text()


def read_text_preview(path: str | Path | None, max_chars: int = 4000) -> str | None:
    content = read_text(path)
    if content is None:
        return None
    if len(content) <= max_chars:
        return content
    return content[: max_chars - 3] + "..."


def load_json(path: str | Path | None) -> dict[str, Any] | list[Any] | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None
    return json.loads(target.read_text())


def git_commit(path: str | Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def benchmark_snapshot(benchmark_repo: str | Path, requested_tasks: list[str]) -> dict[str, Any]:
    repo = Path(benchmark_repo).resolve()
    task_roots: list[str] = []
    if repo.exists():
        if requested_tasks:
            for task_id in requested_tasks:
                matches = list(repo.rglob(task_id))
                task_roots.extend(str(match) for match in matches if match.is_dir())
        else:
            task_roots.extend(str(path.parent) for path in repo.rglob("task.toml"))
    return {
        "benchmark_repo": str(repo),
        "benchmark_name": repo.name,
        "benchmark_commit": git_commit(repo),
        "requested_tasks": requested_tasks,
        "discovered_task_roots": sorted(set(task_roots)),
    }
