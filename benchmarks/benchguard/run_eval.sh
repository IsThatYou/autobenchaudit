#!/usr/bin/env bash
# Run convert -> match -> metrics for one benchmark (bixbench|sab).
# Outputs land under bench_audit/benchmarks/benchguard/output/.

set -euo pipefail

if [[ $# -ne 1 || ( "$1" != "bixbench" && "$1" != "sab" ) ]]; then
  echo "usage: $0 {bixbench|sab}" >&2
  exit 2
fi
BENCH="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

# Load .env (GOOGLE_API=...) and remap to LiteLLM's expected name.
if [[ -f bench_audit/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source bench_audit/.env
  set +a
fi
if [[ -z "${GEMINI_API_KEY:-}" && -n "${GOOGLE_API:-}" ]]; then
  export GEMINI_API_KEY="$GOOGLE_API"
fi
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "ERROR: GEMINI_API_KEY not set (and GOOGLE_API not in bench_audit/.env)" >&2
  exit 1
fi

# Make benchguard package importable when not pip-installed.
export PYTHONPATH="${PYTHONPATH:-}:$REPO_ROOT/BenchGuard/src"

OUT="$SCRIPT_DIR/output"
GOLD="BenchGuard/eval/data/gold/${BENCH}_gold.json"

case "$BENCH" in
  bixbench) AUDITS="data/bench_audit/benchguard/neurips/bixbench__v3__actual/task_audits_static" ;;
  sab)      AUDITS="data/bench_audit/benchguard/neurips/science_agent_bench__v4__actual/task_audits_static" ;;
esac

mkdir -p "$OUT/normalized" "$OUT/matches" "$OUT/reports"

echo "==> [1/3] convert audits -> findings"
python "$SCRIPT_DIR/audits_to_benchguard_findings.py" \
  --benchmark "$BENCH" \
  --audits-dir "$AUDITS" \
  --gold "$GOLD" \
  --output "$OUT/normalized/${BENCH}_findings.json"

echo "==> [2/3] LLM-judge pairwise matching"
JUDGE_MODEL="${JUDGE_MODEL:-gemini/gemini-3-flash-preview}"
JUDGE_MAX_TOKENS="${JUDGE_MAX_TOKENS:-8192}"
# Cache key doesn't include model, so isolate cache per model to avoid stale verdicts.
JUDGE_MODEL_SLUG="$(echo "$JUDGE_MODEL" | tr '/:' '__')"
python BenchGuard/eval/match.py \
  --gold "$GOLD" \
  --findings "$OUT/normalized/${BENCH}_findings.json" \
  --output "$OUT/matches/${BENCH}_matches.json" \
  --cache-dir "$OUT/matches/cache_${BENCH}__${JUDGE_MODEL_SLUG}" \
  --model "$JUDGE_MODEL" \
  --max-tokens "$JUDGE_MAX_TOKENS" \
  --max-concurrent 10

echo "==> [3/3] compute metrics + reports"
python BenchGuard/eval/metrics.py \
  --matches "$OUT/matches/${BENCH}_matches.json" \
  --gold "$GOLD" \
  --findings "$OUT/normalized/${BENCH}_findings.json" \
  --output "$OUT/reports"

echo
echo "Done. Reports:"
echo "  $OUT/reports/${BENCH}_eval.md"
echo "  $OUT/reports/${BENCH}_eval.json"
