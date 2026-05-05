# fix-git

## Summary of changes (from PR #53 body)

- Delete the installation files after container is setup. Previously, they were left and agents could technically access them to cheat.
- Update tests with hardcoded md5 file hashes to account for the previous change.

Related PRs: [PR #50](https://github.com/harbor-framework/terminal-bench-2/pull/50).

## Additional changes observed in diff

- `task.toml`: docker image bumped from `:20251031` → `:20260403`. Implicit, expected.
- `tests/test_outputs.py`: switched from `compare_file_hashes(OLD, NEW)` (which read the patch_files at test time) to `check_file_hash(NEW, "<hardcoded md5>")` for both the about file and the layout file. Hashes hardcoded:
  - `about.md` → `0273104059c6bf524e767b8847b22946`
  - `default.html` → `0f879389f66640f45316e393a71c5f2f`
- (Helper functions `compare_file_hashes`/`check_file_hash` aren't shown in the diff — defined elsewhere.)

## Issues found

- **Patch files left in container enabled cheating** (addressed by tb2#50) — Installation `patch_files` were left accessible to the agent after setup; agents could read the expected diff and copy the answer. Flagged in tb2#50 body ("Hide the patch files from the agent").
- **Grader previously read patch files at test time** (addressed) — Test used `compare_file_hashes(OLD, NEW)` which re-read the patch files during verification. With the files removed, the test was rewritten to use `check_file_hash(NEW, "<hardcoded md5>")` — hashes now baked into `tests/test_outputs.py` at `0273104059c6bf524e767b8847b22946` (about.md) and `0f879389f66640f45316e393a71c5f2f` (default.html).
