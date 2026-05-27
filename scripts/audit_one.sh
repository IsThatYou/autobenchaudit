#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
[ -f "${ROOT_DIR}/.env" ] && { set -a; source "${ROOT_DIR}/.env"; set +a; }

URL=""
NAME=""
SAMPLE_N=5
DOMAIN="misc"
MODEL="claude-opus-4-7"
SKIP_BENCHMARK_AUDIT=0

usage() {
    cat <<'EOF'
Usage: scripts/audit_one.sh --url <github_url> [options]

Run a static-mode audit on any benchmark repo in one command. Wraps:
  bench-audit audit-benchmark  →  collect-evidence  →  audit-tasks --mode static

Required:
  --url <github_url>      Benchmark source repository.

Optional:
  --name <slug>           Override the auto-derived benchmark name.
  --sample-n <N>          How many tasks to audit (default: 5).
  --domain <cat>          domain_categories entry (default: misc).
  --model <claude-...>    Model id (default: claude-opus-4-7).
  --skip-benchmark-audit  Skip the benchmark-level phase (saves ~1 call).
  -h, --help              Show this help and exit.

Environment:
  ANTHROPIC_API_KEY       Required. Read from .env or shell.
  BENCHMARK_REPOS_DIR     Where to clone benchmark repos. Wrapper falls back
                          to ./data/benchmark_repos if unset.
  AUDIT_RUN_DIR           Where audit outputs are written. Wrapper falls back
                          to ./data/audit_runs if unset.

Example:
  scripts/audit_one.sh --url https://github.com/centerforaisafety/hle --sample-n 3
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --url) URL="$2"; shift 2;;
        --name) NAME="$2"; shift 2;;
        --sample-n) SAMPLE_N="$2"; shift 2;;
        --domain) DOMAIN="$2"; shift 2;;
        --model) MODEL="$2"; shift 2;;
        --skip-benchmark-audit) SKIP_BENCHMARK_AUDIT=1; shift;;
        -h|--help) usage; exit 0;;
        *) echo "unknown arg: $1" >&2; usage; exit 1;;
    esac
done

if [ -z "$URL" ]; then
    echo "error: --url is required" >&2
    usage
    exit 1
fi
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "error: ANTHROPIC_API_KEY is not set (check .env)" >&2
    exit 1
fi

if [ -z "$NAME" ]; then
    NAME=$(basename "${URL%.git}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_')
    NAME="${NAME%_}"
fi

absolutize() {
    # Normalize $1 to an absolute path. Relative paths resolve against ROOT_DIR
    # so the YAML we generate doesn't get re-resolved against configs/quick/
    # by bench-audit's config loader.
    local val="$1"
    case "$val" in
        /*) printf '%s' "$val";;
        *)  printf '%s/%s' "$ROOT_DIR" "$val";;
    esac
}
export BENCHMARK_REPOS_DIR="$(absolutize "${BENCHMARK_REPOS_DIR:-${ROOT_DIR}/data/benchmark_repos}")"
export AUDIT_RUN_DIR="$(absolutize "${AUDIT_RUN_DIR:-${ROOT_DIR}/data/audit_runs}")"

REPO_DIR="${BENCHMARK_REPOS_DIR}/${NAME}/repo"
DATA_DIR="${BENCHMARK_REPOS_DIR}/${NAME}/data"
CONFIG_DIR="${ROOT_DIR}/configs/quick"
CONFIG_PATH="${CONFIG_DIR}/${NAME}.yaml"

mkdir -p "$(dirname "$REPO_DIR")" "$DATA_DIR" "$CONFIG_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "[audit_one] cloning $URL -> $REPO_DIR"
    git clone "$URL" "$REPO_DIR"
else
    echo "[audit_one] repo already present at $REPO_DIR (skipping clone)"
fi

echo "[audit_one] writing config $CONFIG_PATH"
cat > "$CONFIG_PATH" <<EOF
benchmark_name: ${NAME}
benchmark_type: neurips
agent_cli: claude
model: ${MODEL}
output_subdir: quick

code_url: ${URL}
benchmark_data_dir: ${DATA_DIR}
benchmark_repo_dir: ${REPO_DIR}

domain_categories:
  - ${DOMAIN}
EOF

if [ -x "${ROOT_DIR}/.venv/bin/bench-audit" ]; then
    BENCH_AUDIT="${ROOT_DIR}/.venv/bin/bench-audit"
else
    BENCH_AUDIT="bench-audit"
fi

if [ "$SKIP_BENCHMARK_AUDIT" -eq 0 ]; then
    echo "[audit_one] phase 1/3: audit-benchmark"
    "$BENCH_AUDIT" audit-benchmark --config "$CONFIG_PATH"
else
    echo "[audit_one] skipping audit-benchmark"
fi

echo "[audit_one] phase 2/3: collect-evidence"
"$BENCH_AUDIT" collect-evidence --config "$CONFIG_PATH"

echo "[audit_one] phase 3/3: audit-tasks (static, sample-n=$SAMPLE_N)"
"$BENCH_AUDIT" audit-tasks \
    --config "$CONFIG_PATH" \
    --all \
    --mode static \
    --sample-n "$SAMPLE_N"

OUT_DIR="${AUDIT_RUN_DIR}/neurips/${NAME}__quick__actual"
echo ""
echo "[audit_one] done."
echo "[audit_one] output root: $OUT_DIR"
echo "[audit_one] findings:    $OUT_DIR/task_audits_static/"
