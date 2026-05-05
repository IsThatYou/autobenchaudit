# make-doom-for-mips

## Summary of changes (from PR #53 body)

- Fixed oracle.sh: The package index inside the container was stale, so apt returned 404s and clang never installed.

## Additional changes observed in diff

- Diff matches summary. Single-line change in `solution/solve.sh`: `apt install ...` → `apt-get update && apt install ...`.
- Note: only the oracle was patched. The same stale-apt-index problem can still bite agents, since the task environment itself wasn't rebuilt — agents still have to know to run `apt-get update` themselves before installing the cross-compiler. Audit found "broken_tool" severity 3 for the cross-compile toolchain availability; this PR fixes the oracle but does not address agent-side reproducibility.

## Issues found

- **Stale APT index prevented clang install in oracle** (addressed) — Oracle's `apt install` returned 404s because the container's cached index was stale; clang never installed. Fixed by prepending `apt-get update`.
- **Agent-side toolchain availability unchanged** (NOT addressed) — The container image itself wasn't rebuilt, so agents hit the same stale-index problem unless they know to run `apt-get update` themselves. Prior audit flagged this as a Major/`broken_tool` issue (cross-compile toolchain availability); PR #53 fixes the oracle but leaves the agent-side reproducibility gap open.
