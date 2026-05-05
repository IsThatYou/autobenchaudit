# mteb-retrieve

## Summary of changes (from PR #53 body)

- Pin `transformers==4.48.3` to environment `Dockerfile` (with `mteb==1.36.8` pinned, rebuilding with `force_build: true` pulls transformers 5.x, which is incompatible with mteb 1.36.8).
- Update task description to say agents must use the installed mteb package (previously said "You have the mteb package" which doesn't require using it; agents using SentenceTransformer directly skip prompt type prefixes and get different results).

## Additional changes observed in diff

- `task.toml`: docker image bumped from `:20251031` → `:20260403` (implicit, expected with the Dockerfile change).
- Diff otherwise matches the summary verbatim.

## Issues found

- **transformers 5.x incompatible with pinned mteb** (addressed) — With `mteb==1.36.8` pinned, `force_build: true` pulled `transformers` 5.x, which is API-incompatible with mteb 1.36.8. Now pinned `transformers==4.48.3`.
- **Prompt permitted bypassing the mteb encoding pipeline** (partially addressed) — Prior prompt said "You have the mteb package", which did not require agents to use it. Agents using SentenceTransformer directly skip the asymmetric `PromptType.query`/`PromptType.passage` prefixes mteb applies, producing different embeddings. Prompt now mandates using the installed mteb package. But the task name (`SciFact`) and the query-vs-passage PromptType asymmetry are still not spelled out. Audit finding `mteb-retrieve-prompt-underspecified-encoding` (Major/ambiguity) — partial.
