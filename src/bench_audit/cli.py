from __future__ import annotations

import argparse
import os
from pathlib import Path

from .audit_protocol import load_general_rubric, resolve_phase_sequence
from .benchmark_audit import audit_benchmark
from .evidence_collection import collect_evidence, load_collection_config
from .task_evaluation import audit_tasks
from .trajectory_generation import generate_trajectories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench-audit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bench_audit = subparsers.add_parser("audit-benchmark")
    bench_audit.add_argument("--config", required=True)
    bench_audit.add_argument("--general-rubric")
    bench_audit.add_argument("--rubric-text", help="Path to a .txt benchmark rubric file (overrides the default)")
    bench_audit.add_argument("--force", action="store_true")
    bench_audit.add_argument("--timeout", type=int, default=800)

    collect = subparsers.add_parser("collect-evidence")
    collect.add_argument("--config", required=True)
    collect.add_argument("--job-type", choices=["actual"])
    collect.add_argument("--force", action="store_true")

    audit_tasks = subparsers.add_parser("audit-tasks")
    audit_tasks.add_argument("--config", required=True)
    audit_tasks.add_argument("--general-rubric")
    audit_tasks.add_argument("--tasks", nargs="+")
    audit_tasks.add_argument("--all", action="store_true")
    audit_tasks.add_argument("--force", action="store_true")
    audit_tasks.add_argument("--rubric-text", help="Path to a .txt rubric file (overrides the default derived from general rubric)")
    audit_tasks.add_argument("--eval-strategy", choices=["mixed", "all_failed", "all"], default="mixed",
                             help="Eval selection strategy: 'mixed' (primary + contrast, default), 'all_failed' (all failed evals), or 'all' (all evals)")
    audit_tasks.add_argument("--mode", choices=["trajectory", "static"],
                             help="Audit mode: 'trajectory' (default for tb2/swe_bench) uses eval artifacts, 'static' (default for neurips) audits task definitions only")
    audit_tasks.add_argument("--sample-n", type=int, help="Randomly sample N tasks to audit (default: all)")
    audit_tasks.add_argument("--sample-seed", type=int, default=42, help="Random seed for task sampling (default: 42)")
    audit_tasks.add_argument("--max-workers", type=int, default=1)
    audit_tasks.add_argument("--timeout", type=int, default=800)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--harbor-config", required=True)
    generate.add_argument("--benchmark-type", required=True)
    generate.add_argument("--agent-cli", required=True)
    generate.add_argument("--model", required=True)
    generate.add_argument("--dataset", help="Override dataset name in Harbor config")
    generate.add_argument("--download-dir", help="Override dataset download_dir in Harbor config")
    generate.add_argument("--save-dir")
    generate.add_argument("--jobs-type", default="actual", choices=["actual"])

    run = subparsers.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--general-rubric")
    run.add_argument("--job-type", choices=["actual"])
    run.add_argument("--start-phase", default="benchmark_audit")
    run.add_argument("--end-phase", default="evidence_collection")
    run.add_argument("--tasks", nargs="+")
    run.add_argument("--all", action="store_true")
    run.add_argument("--force", action="store_true")
    run.add_argument("--rubric-text", help="Path to a .txt rubric file (overrides the default derived from general rubric)")
    run.add_argument("--eval-strategy", choices=["mixed", "all_failed", "all"], default="mixed",
                     help="Eval selection strategy: 'mixed' (primary + contrast, default), 'all_failed' (all failed evals), or 'all' (all evals)")
    run.add_argument("--mode", choices=["trajectory", "static"],
                     help="Audit mode: 'trajectory' (default for tb2/swe_bench) uses eval artifacts, 'static' (default for neurips) audits task definitions only")
    run.add_argument("--sample-n", type=int, help="Randomly sample N tasks to audit (default: all)")
    run.add_argument("--sample-seed", type=int, default=42, help="Random seed for task sampling (default: 42)")
    run.add_argument("--max-workers", type=int, default=1)
    run.add_argument("--timeout", type=int, default=800)

    return parser


def load_repo_env() -> None:
    env_path = repo_root() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    load_repo_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        generate_trajectories(
            harbor_config=Path(args.harbor_config).resolve(),
            benchmark_type=args.benchmark_type,
            agent_cli=args.agent_cli,
            model=args.model,
            dataset=args.dataset,
            download_dir=Path(args.download_dir) if args.download_dir else None,
            save_dir=Path(args.save_dir) if args.save_dir else None,
            jobs_type=args.jobs_type,
        )
        return 0

    if args.command == "audit-benchmark":
        config = load_collection_config(args.config)
        audit_benchmark(
            config,
            general_rubric_path=args.general_rubric,
            rubric_text_path=args.rubric_text,
            force=args.force,
            timeout=args.timeout,
        )
        return 0

    if args.command == "collect-evidence":
        config = load_collection_config(args.config)
        if args.job_type:
            config.jobs_type = args.job_type
        collect_evidence(config, force=args.force)
        return 0

    if args.command == "audit-tasks":
        config = load_collection_config(args.config)
        _validate_task_filters(args.tasks, args.all)
        audit_tasks(
            config,
            general_rubric_path=args.general_rubric,
            rubric_text_path=args.rubric_text,
            task_ids=args.tasks,
            include_all=args.all,
            force=args.force,
            max_workers=args.max_workers,
            timeout=args.timeout,
            eval_strategy=args.eval_strategy,
            audit_mode=args.mode,
            sample_n=args.sample_n,
            sample_seed=args.sample_seed,
        )
        return 0

    if args.command == "run":
        config = load_collection_config(args.config)
        if args.job_type:
            config.jobs_type = args.job_type
        _validate_task_filters(args.tasks, args.all)
        general_rubric = load_general_rubric(args.general_rubric)
        phases = resolve_phase_sequence(general_rubric, args.start_phase, args.end_phase)
        if "benchmark_audit" in phases:
            audit_benchmark(
                config,
                general_rubric_path=args.general_rubric,
                rubric_text_path=getattr(args, "rubric_text", None),
                force=args.force,
                timeout=getattr(args, "timeout", 800),
            )
        if "evidence_collection" in phases:
            collect_evidence(config, force=args.force)
        if "per_task_evaluation" in phases:
            audit_tasks(
                config,
                general_rubric_path=args.general_rubric,
                rubric_text_path=args.rubric_text,
                task_ids=args.tasks,
                include_all=args.all,
                force=args.force,
                max_workers=args.max_workers,
                timeout=args.timeout,
                eval_strategy=args.eval_strategy,
                audit_mode=args.mode,
                sample_n=args.sample_n,
                sample_seed=args.sample_seed,
            )
        return 0

    raise SystemExit(f"unknown command: {args.command}")


def _validate_task_filters(task_ids: list[str] | None, include_all: bool) -> None:
    if task_ids and include_all:
        raise SystemExit("--tasks and --all cannot be used together")
