# adaptive-rejection-sampler

## Summary of changes (from PR #53 body)

- Update task description to specify the signature of the function the agent needs to implement (test code and oracle solution require a specific signature).

Related PRs: [#1391](https://github.com/harbor-framework/terminal-bench/pull/1391)

## Additional changes observed in diff

- `solution/solve.sh`: removed pinned APT versions for `r-base-core` and `r-base` (was `=4.3.3-2build2`, now unpinned). Not mentioned in the summary.

## Issues found

- **Function signature unspecified in prompt** (addressed) — Test code and oracle require a specific `ars(f, domain, n, ...)` signature with explicit parameter ordering, but the task description never stated the contract. Agents implementing a semantically correct but differently-named/ordered function would fail. Source: tb#1391 body ("Clarify the ars() function signature in task.yaml to match test expectations"); audit finding `ars-signature-underspecified` (Minor/ambiguity).
