#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
[ -f "${ROOT_DIR}/.env" ] && { set -a; source "${ROOT_DIR}/.env"; set +a; }

URL=""
NAME=""
SAMPLE_N=5
DOMAIN="misc"
AGENT_CLI="claude"
MODEL=""
SKIP_BENCHMARK_AUDIT=0

REPO_DIR=""
DATA_DIR=""
CONFIG_PATH=""
BENCH_AUDIT=""

usage() {
    cat <<'EOF'
Usage: scripts/audit_one.sh --url <github_url> [options]

Run a static-mode audit on any benchmark repo in one command:
  audit-benchmark -> collect-evidence -> audit-tasks --mode static

Required:
  --url <github_url>      Benchmark source repository.

Optional:
  --name <slug>           Override the auto-derived benchmark name.
  --sample-n <N>          How many tasks to audit (default: 5).
  --domain <cat>          domain_categories entry (default: misc).
  --agent-cli <cli>       Auditor CLI: claude, cursor, or codex (default: claude).
  --model <model>         Model id passed to the agent CLI (default for claude: claude-opus-4-7).
  --skip-benchmark-audit  Skip the benchmark-level phase.
  -h, --help              Show this help and exit.

Environment:
  ANTHROPIC_API_KEY       Required when --agent-cli claude.
  BENCHMARK_REPOS_DIR     Clone/data root. Defaults to ./data/benchmark_repos.
  AUDIT_RUN_DIR           Audit output root. Defaults to ./data/audit_runs.

Example:
  scripts/audit_one.sh --url https://github.com/centerforaisafety/hle --sample-n 3
EOF
}

die() {
    echo "error: $*" >&2
    exit 1
}

log() {
    echo "[audit_one] $*"
}

require_value() {
    [ $# -ge 2 ] || die "$1 requires a value"
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --url)
                require_value "$@"; URL="$2"; shift 2;;
            --name)
                require_value "$@"; NAME="$2"; shift 2;;
            --sample-n)
                require_value "$@"; SAMPLE_N="$2"; shift 2;;
            --domain)
                require_value "$@"; DOMAIN="$2"; shift 2;;
            --agent-cli)
                require_value "$@"; AGENT_CLI="$2"; shift 2;;
            --model)
                require_value "$@"; MODEL="$2"; shift 2;;
            --skip-benchmark-audit)
                SKIP_BENCHMARK_AUDIT=1; shift;;
            -h|--help)
                usage; exit 0;;
            *)
                usage >&2
                die "unknown arg: $1";;
        esac
    done
}

validate_args() {
    if [ -z "$URL" ]; then
        usage >&2
        die "--url is required"
    fi
    case "$AGENT_CLI" in
        claude|cursor|codex) ;;
        *) die "--agent-cli must be one of: claude, cursor, codex";;
    esac
    if [ "$AGENT_CLI" = "claude" ]; then
        [ -n "${ANTHROPIC_API_KEY:-}" ] || die "ANTHROPIC_API_KEY is not set (check .env)"
    fi
}

apply_defaults() {
    if [ -z "$MODEL" ] && [ "$AGENT_CLI" = "claude" ]; then
        MODEL="claude-opus-4-7"
    fi
}

derive_name() {
    if [ -z "$NAME" ]; then
        NAME=$(basename "${URL%.git}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_')
        NAME="${NAME%_}"
    fi
}

absolutize() {
    local val="$1"
    case "$val" in
        /*) printf '%s' "$val";;
        *)  printf '%s/%s' "$ROOT_DIR" "$val";;
    esac
}

init_paths() {
    export BENCHMARK_REPOS_DIR
    BENCHMARK_REPOS_DIR="$(absolutize "${BENCHMARK_REPOS_DIR:-${ROOT_DIR}/data/benchmark_repos}")"

    export AUDIT_RUN_DIR
    AUDIT_RUN_DIR="$(absolutize "${AUDIT_RUN_DIR:-${ROOT_DIR}/data/audit_runs}")"

    REPO_DIR="${BENCHMARK_REPOS_DIR}/${NAME}/repo"
    DATA_DIR="${BENCHMARK_REPOS_DIR}/${NAME}/data"
    CONFIG_PATH="${ROOT_DIR}/configs/quick/${NAME}.yaml"

    mkdir -p "$(dirname "$REPO_DIR")" "$DATA_DIR" "$(dirname "$CONFIG_PATH")"
}

clone_repo_if_needed() {
    if [ -d "$REPO_DIR/.git" ]; then
        log "repo already present at $REPO_DIR (skipping clone)"
        return
    fi

    log "cloning $URL -> $REPO_DIR"
    git clone "$URL" "$REPO_DIR"
}

write_config() {
    log "writing config $CONFIG_PATH"
    {
        cat <<EOF
benchmark_name: ${NAME}
benchmark_type: neurips
agent_cli: ${AGENT_CLI}
EOF
        if [ -n "$MODEL" ]; then
            printf 'model: %s\n' "$MODEL"
        fi
        cat <<EOF
output_subdir: quick

code_url: ${URL}
benchmark_data_dir: ${DATA_DIR}
benchmark_repo_dir: ${REPO_DIR}

domain_categories:
  - ${DOMAIN}
EOF
    } > "$CONFIG_PATH"
}

resolve_bench_audit() {
    if [ -x "${ROOT_DIR}/.venv/bin/bench-audit" ]; then
        BENCH_AUDIT="${ROOT_DIR}/.venv/bin/bench-audit"
    else
        BENCH_AUDIT="bench-audit"
    fi
}

run_audit() {
    if [ "$SKIP_BENCHMARK_AUDIT" -eq 0 ]; then
        log "phase 1/3: audit-benchmark"
        "$BENCH_AUDIT" audit-benchmark --config "$CONFIG_PATH"
    else
        log "skipping audit-benchmark"
    fi

    log "phase 2/3: collect-evidence"
    "$BENCH_AUDIT" collect-evidence --config "$CONFIG_PATH"

    log "phase 3/3: audit-tasks (static, sample-n=$SAMPLE_N)"
    "$BENCH_AUDIT" audit-tasks \
        --config "$CONFIG_PATH" \
        --all \
        --mode static \
        --sample-n "$SAMPLE_N"
}

print_summary() {
    local out_dir="${AUDIT_RUN_DIR}/neurips/${NAME}__quick__actual"

    echo ""
    log "done."
    log "output root: $out_dir"
    log "findings:    $out_dir/task_audits_static/"
}

main() {
    parse_args "$@"
    validate_args
    apply_defaults
    derive_name
    init_paths
    clone_repo_if_needed
    write_config
    resolve_bench_audit
    run_audit
    print_summary
}

main "$@"
