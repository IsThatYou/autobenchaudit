# polyglot-c-py

## Summary of changes (from PR #53 body)

- Update tests to replace `os.listdir == ["main.c"]` with `os.path.exists` check (allows byproducts of compilation to exist in the target dir, which is allowed by the task description).

Related PRs: [#1390](https://github.com/harbor-framework/terminal-bench/pull/1390)

## Additional changes observed in diff

- Minor mismatch with summary wording: the file checked is `main.py.c`, not `main.c` (the summary's example name doesn't match the actual filename in this task). The behavioral change (replacing the equality check on `os.listdir` with `os.path.exists`) is correct.
- Diff otherwise matches the summary.

## Issues found

- **Test enforced unstated "source file only" constraint** (addressed by tb#1390) — Test asserted `os.listdir(/app/polyglot) == ["main.py.c"]` (strict single-file list), causing failures when compiled binaries from prior runs sat alongside the source file — even though the task description allows byproducts. Replaced with `os.path.exists("main.py.c")`. Audit finding `polyglot-c-py__cmain_artifact_trap` (Major/ambiguity) — supported.
- **PR #53 summary wording mismatch** — Summary says `main.c`; the actual file in this task is `main.py.c`. Behavior change is still correct.
