# mteb-leaderboard

## Summary of changes (from PR #53 body)

- Add `Pillow` dependency to environment `Dockerfile` (`mteb==1.38.41` dropped `Pillow` as a transitive dependency, making rebuilds with `force_build: true` cause ImportError).
- Update task description to specify that only models with results for all tasks in the benchmark should be considered (test filters to 28/28 tasks, previously not mentioned in description).
- Update memory from 4B to 16GB.

Related PRs: [PR #27](https://github.com/harbor-framework/terminal-bench-2/pull/27)

## Additional changes observed in diff

- **Memory bump mismatch**: Summary says "Update memory from 4B to 16GB" but the actual `task.toml` change is `4G` → `8G`, not `16G`.
- **Undocumented pin**: `Dockerfile` also pins `transformers==4.57.1` alongside the new `Pillow==12.0.0`. Only `Pillow` is mentioned in the summary.
- `task.toml`: docker image bumped from `:20251031` → `:20260403` (implicit).
- The audit's primary finding (`live-external-resource-no-snapshot`, severity 3) — that the leaderboard is a live resource with no frozen snapshot — is **not addressed**. The instruction still says "as of August 2025" and there is no bundled data or pinned commit in the prompt.

## Issues found

- **Missing Pillow transitive dep after mteb upgrade** (addressed by tb2#27) — `mteb==1.38.41` dropped `Pillow` as a transitive dependency. Rebuilds with `force_build: true` raised `ImportError` for Pillow. Now pinned as `Pillow==12.0.0` in the Dockerfile.
- **Prompt didn't specify all-28-task coverage requirement** (addressed) — Test filters to models with results on all 28 tasks in the MTEB(Scandinavian, v1) benchmark, but the prompt never said so. Agents picking a model with partial coverage would get the wrong answer. Instruction now states the full-coverage requirement. Audit finding `mteb-leaderboard-ambiguity-missing-tasks` (Major/ambiguity) — supported.
- **Memory too tight relative to documented-API path** (partially addressed) — Reviewer (giansegato) profiled 12.6G peak vs. 4G declared, 6% cross-family OOM. Oracle pre-filters models via filesystem walk before `load_results()` — a technique not in the documented API. Agents calling `load_results()` unfiltered (the obvious documented path) OOM. Memory bumped but to 8G, not 16G as the summary claimed.
- **PR summary vs. diff mismatch** — Summary says "Update memory from 4B to 16GB"; actual `task.toml` change is `4G` → `8G`.
- **Undocumented `transformers==4.57.1` pin** — Added to Dockerfile alongside the documented Pillow pin; not mentioned in summary.
- **Live external resource, no frozen snapshot** (NOT addressed) — Instruction still references "as of August 2025" without pinning a commit or bundling data. Audit finding `mteb-leaderboard-ambiguity-date-pin` (Major/ambiguity) — not supported. Primary audit concern `live-external-resource-no-snapshot` (severity 3) also unaddressed.
- **Benchmark-version string not explicitly named** (partial) — Prompt's full-coverage update implicitly disambiguates which task set is meant, but the canonical string "MTEB(Scandinavian, v1)" and direct leaderboard URL are not in the prompt. Audit finding `mteb-leaderboard-ambiguity-benchmark-version` (Minor/ambiguity) — partial.
- **Grader uses exact-string match** (NOT addressed) — Grader still hardcodes `GritLM/GritLM-7B` as the exact expected answer. Audit finding `mteb-leaderboard-test-quality-exact-match` (Minor/test_quality) — not supported.
