from __future__ import annotations

import random
from dataclasses import dataclass

from ..evidence_collection import EvalConfig, TaskConfig


# Whitelist of eval-level fields shown in audit prompts.
_EVAL_PROMPT_FIELDS = ("eval_id", "status", "metrics_path", "test_output_path", "prediction_path", "trajectory_path")


@dataclass(slots=True, frozen=True)
class EvalArtifactPaths:
    eval_id: str
    status: str
    metrics_path: str | None
    test_output_path: str | None
    prediction_path: str | None
    trajectory_path: str | None

def select_task_configs(
    task_configs: list[TaskConfig],
    task_filter: str,
    task_ids: list[str] | None = None,
    include_all: bool = False,
    sample_n: int | None = None,
    sample_seed: int = 42,
) -> list[TaskConfig]:
    ordered = sorted(task_configs, key=lambda task: task.task_id)
    if task_ids:
        requested = set(task_ids)
        selected = [task for task in ordered if task.task_id in requested]
        missing = requested.difference(task.task_id for task in selected)
        if missing:
            raise ValueError(f"unknown task ids requested: {', '.join(sorted(missing))}")
        return selected
    if include_all or task_filter == "all":
        selected = ordered
    elif task_filter != "failed_or_mixed":
        raise ValueError(f"unsupported task filter for task evaluation: {task_filter}")
    else:
        selected = [task for task in ordered if task.status == "failed" or _is_mixed(task)]
    if sample_n is not None and len(selected) > sample_n:
        selected = sorted(
            random.Random(sample_seed).sample(selected, sample_n),
            key=lambda task: task.task_id,
        )
    return selected


EVAL_STRATEGIES = {"mixed", "all_failed", "all"}


def select_eval_configs(
    task_config: TaskConfig,
    eval_configs: list[EvalConfig],
    eval_strategy: str = "mixed",
) -> list[EvalConfig]:
    if not eval_configs:
        raise ValueError(f"task {task_config.task_id} does not have any eval configs")
    if eval_strategy not in EVAL_STRATEGIES:
        raise ValueError(f"unsupported eval strategy: {eval_strategy}")

    if eval_strategy == "all":
        return sorted(eval_configs, key=_eval_sort_key)

    if eval_strategy == "all_failed":
        failed = [e for e in eval_configs if e.status == "failed"]
        if not failed:
            failed = [max(eval_configs, key=_eval_sort_key)]
        return sorted(failed, key=_eval_sort_key)

    # Default "mixed" strategy: primary + one contrast eval.
    by_eval_id = {eval_config.eval_id: eval_config for eval_config in eval_configs}
    primary_eval = None
    if task_config.primary_eval_id:
        primary_eval = by_eval_id.get(task_config.primary_eval_id)
    if primary_eval is None:
        primary_eval = max(eval_configs, key=_eval_sort_key)

    selected = [primary_eval]
    if _is_mixed(task_config):
        contrast_status = "failed" if primary_eval.status == "passed" else "passed"
        contrasting = [eval_config for eval_config in eval_configs if eval_config.status == contrast_status]
        if contrasting:
            contrast_eval = max(contrasting, key=_eval_sort_key)
            if contrast_eval.eval_id != primary_eval.eval_id:
                selected.append(contrast_eval)
    return selected


def _is_mixed(task_config: TaskConfig) -> bool:
    return task_config.n_passed > 0 and task_config.n_failed > 0


def _eval_sort_key(eval_config: EvalConfig) -> tuple[str, str]:
    return (eval_config.finished_at or "", eval_config.eval_id)


def eval_artifact_paths(eval_config: EvalConfig) -> EvalArtifactPaths:
    return EvalArtifactPaths(
        eval_id=eval_config.eval_id,
        status=eval_config.status,
        metrics_path=eval_config.metrics_path,
        test_output_path=eval_config.test_output_path,
        prediction_path=eval_config.prediction_path,
        trajectory_path=eval_config.trajectory_path,
    )
