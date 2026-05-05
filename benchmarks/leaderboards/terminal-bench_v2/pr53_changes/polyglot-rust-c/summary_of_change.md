# polyglot-rust-c

## Summary of changes (from PR #53 body)

- Update tests to replace `os.listdir == ["main.rs"]` with `os.path.isfile` check (allows byproducts of compilation to exist in the target dir, which is allowed by the task description).

Related PRs: [PR #37](https://github.com/harbor-framework/terminal-bench-2/pull/37).

## Additional changes observed in diff

- Diff matches the summary. Also drops a `print(polyglot_files)` debug line and an extra blank line.

## Issues found

- **Test enforced unstated "source file only" constraint** (addressed by tb2#37) — Same class as polyglot-c-py. Test asserted `os.listdir(/app/polyglot) == ["main.rs"]`, failing when compiled binaries from prior runs were present. Replaced with `os.path.isfile("main.rs")` and an autouse fixture that cleans non-source artifacts before and after each test. Audit finding `polyglot-rust-c-001` (Minor/test_quality) — supported.
- **Debug `print` left in tests** (addressed) — Stray `print(polyglot_files)` removed during the rewrite.
