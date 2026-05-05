# build-pmars

## Summary of changes (from PR #53 body)

- Update task description and test: remove ambiguity in build destination

Related PRs: [PR #1401](https://github.com/harbor-framework/terminal-bench/pull/1401)

## Additional changes observed in diff

- The summary says "Update task description **and test**", but PR #53 only modifies `instruction.md` and `solution/solve.sh` — no test file is touched in this PR. Either the test edit landed elsewhere, or the wording is inaccurate.
- `solution/solve.sh`: removed pinned APT versions for `build-essential`, `libncurses-dev`, `ca-certificates`, `dpkg-dev`, `devscripts` (all now unpinned). Not mentioned in the summary.

## Issues found

- **Test enforces extraction layout not stated in prompt** (addressed by tb#1401) — Prompt only said "Extract the source to `/app`". Tests hardcoded paths like `/app/pmars-*`, so agents extracting to `/app/pmars/`, `/app/src/`, or any other reasonable layout would fail despite correct build behavior. tb#1401 replaces hardcoded patterns with `Path.rglob()` recursive search for `debian/control`, `debian/changelog`, and `src/`.
- **Stale APT pin in oracle `solve.sh`** (addressed during PR #53 review) — Oracle pinned `dpkg-dev=1.22.21`, but Debian repos moved on (`E: Version '1.22.21' for 'dpkg-dev' was not found`), causing oracle to exit 100 before building anything. Flagged by giansegato in PR #53 comments; the APT pin removals above are the fix.
