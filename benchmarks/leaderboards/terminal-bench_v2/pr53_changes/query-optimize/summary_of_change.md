# query-optimize

## Summary of changes (from PR #53 body)

- Update task description to say "Do not modify the database file in any way" (agents that touch the database and revert changes leave a file that is logically identical but not bit-identical; test checks SHA256 hash).

## Additional changes observed in diff

- Diff matches the summary exactly. Single-line addition to `instruction.md`.

## Issues found

- **Test checks SHA256, agents modify-then-revert the DB** (addressed) — Grader verifies the database file's SHA256 hash. Agents that modify the DB during exploration and revert changes leave a file that is logically identical but not bit-identical (byte-level diffs from SQLite journaling, VACUUM, etc.). The prompt never forbade touching the DB. New line added: "Do not modify the database file in any way".
- **Performance target not disclosed** (NOT addressed) — Grader requires the optimized query to beat a hidden golden query by ~1.05×, but the target is not in the prompt. Audit finding `query-optimize-hidden-perf-target` (Minor/ambiguity) — not supported.
- **Unreliable timing measurement** (NOT addressed) — Performance gate is susceptible to container jitter (single-run timing, narrow tolerance). Audit finding `query-optimize-flaky-timing` (Minor/test_quality) — not supported.
