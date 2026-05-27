#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
[ -f "${ROOT_DIR}/.env" ] && { set -a; source "${ROOT_DIR}/.env"; set +a; }

# --- Usage --------------------------------------------------------------------
# bash scripts/batch_static_audit_pipeline.sh
# bash scripts/batch_static_audit_pipeline.sh --max-tasks 100 --batch 50 --workers 3
# bash scripts/batch_static_audit_pipeline.sh --domain medical_health
# bash scripts/batch_static_audit_pipeline.sh --config configs/multi_domain_all/medical_health/clinbench.yaml
# bash scripts/batch_static_audit_pipeline.sh --status
# bash scripts/batch_static_audit_pipeline.sh --keep            # disable cleanup
# bash scripts/batch_static_audit_pipeline.sh --reset-tracker   # fresh tracker
#
# Per-benchmark, runs:
#   1. audit-benchmark
#   2. collect-evidence
#   3. sample-tasks
#   4. audit-tasks (--batch first N pending)
#   5. cleanup benchmark_repo_dir + benchmark_data_dir on full success
#
# Tracking:
#   ${ROOT_DIR}/configs/multi_domain_all/streaming_pipeline_tracking.json
#
# Output root:
#   ${AUDIT_RUN_DIR} (default below)
# ------------------------------------------------------------------------------
export AUDIT_RUN_DIR="${MULTI_DOMAIN_AUDIT_RUN_DIR:-${ROOT_DIR}/data/multi_domain_all}"
export BENCH_AUDIT_DEBUG_PROMPTS="${BENCH_AUDIT_DEBUG_PROMPTS:-0}"

exec env PYTHONPATH=src ./.venv/bin/python scripts/multi_domain_streaming_pipeline.py "$@"
