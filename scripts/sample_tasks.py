#!/usr/bin/env python3
"""Sample N tasks from existing task_configs and write sampled_tasks.json.

Usage:
    python scripts/sample_tasks.py --config configs/shortlist/foo.yaml --max-tasks 100
    python scripts/sample_tasks.py --config configs/shortlist/foo.yaml --max-tasks 100 --seed 99

Reads the benchmark output dir (derived from config + AUDIT_RUN_DIR),
lists task_configs/, samples up to --max-tasks, and writes:
    <output_root>/sampled_tasks.json

The file records the sample parameters and selected task IDs so downstream
steps (audit-tasks, analysis) use a consistent subset.

Prints sampled task IDs to stdout (one per line) for shell consumption.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reuse the project's own config loader and path resolution
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bench_audit.evidence_collection import load_collection_config
from bench_audit.evidence_collection.runner import resolve_output_root


def print_task_ids(task_ids: list[str]) -> None:
    for tid in task_ids:
        print(tid)
    sys.stdout.flush()


def exit_quietly_on_broken_pipe() -> None:
    # Python flushes stdout again during interpreter shutdown. Point the file
    # descriptor at /dev/null so a closed pipe does not emit an ignored exception.
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
    finally:
        os.close(devnull)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Sample tasks from existing task_configs")
    parser.add_argument("--config", required=True, help="Benchmark collection config YAML")
    parser.add_argument("--max-tasks", type=int, required=True, help="Max tasks to sample (0 = all)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing sampled_tasks.json")
    args = parser.parse_args()

    config = load_collection_config(args.config)
    output_root = resolve_output_root(config)
    task_configs_dir = output_root / "task_configs"
    sample_path = output_root / "sampled_tasks.json"

    if sample_path.exists() and not args.force:
        # Reuse existing sample — just print the task IDs
        existing = json.loads(sample_path.read_text())
        print_task_ids(existing["task_ids"])
        print(f"Reusing existing sample: {len(existing['task_ids'])} tasks ({sample_path})",
              file=sys.stderr)
        return

    if not task_configs_dir.is_dir():
        print(f"ERROR: task_configs not found at {task_configs_dir}", file=sys.stderr)
        sys.exit(1)

    all_task_ids = sorted(
        d.name for d in task_configs_dir.iterdir()
        if d.is_dir() and (d / "task_config.json").exists()
    )

    if not all_task_ids:
        print(f"ERROR: no task configs found in {task_configs_dir}", file=sys.stderr)
        sys.exit(1)

    if args.max_tasks > 0 and len(all_task_ids) > args.max_tasks:
        random.seed(args.seed)
        sampled = sorted(random.sample(all_task_ids, args.max_tasks))
    else:
        sampled = all_task_ids

    record = {
        "benchmark_name": config.benchmark_name,
        "total_tasks": len(all_task_ids),
        "sampled_count": len(sampled),
        "max_tasks": args.max_tasks,
        "seed": args.seed,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "task_ids": sampled,
    }
    sample_path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"Sampled {len(sampled)}/{len(all_task_ids)} tasks → {sample_path}",
          file=sys.stderr)

    print_task_ids(sampled)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        exit_quietly_on_broken_pipe()
