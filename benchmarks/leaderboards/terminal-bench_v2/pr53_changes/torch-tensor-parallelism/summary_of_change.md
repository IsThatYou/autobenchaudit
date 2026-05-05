# torch-tensor-parallelism

## Summary of changes (from PR #53 body)

- Update task description to clarify that `RowParallelLinear.forward()` receives a pre-scattered input slice (input already partitioned along the last dimension), not the full input. Agents that scatter internally cause a double-scatter shape mismatch.
- Increase memory from 4GB to 8GB to avoid failures due to agent and verifier installation overhead (e.g., transient spikes during pip install torch).

## Additional changes observed in diff

- Diff matches the summary. Both changes present (`instruction.md` description rewrite + `task.toml` memory bump).

## Issues found

- **`RowParallelLinear.forward()` input contract unstated** (addressed) — Prompt didn't clarify that `forward()` receives a pre-scattered per-rank input slice (already partitioned along the last dimension), not the full unsharded input. Agents that scatter internally produce a double-scatter shape mismatch. Prompt now states the contract explicitly. Audit finding `row-parallel-input-convention-unspecified` (Minor/ambiguity) — supported.
- **`pip install torch` memory spike OOMs at 4G cap** (addressed via limit bump) — Same root cause as torch-pipeline-parallelism. Reviewer (giansegato) profiled 8.5G peak vs. 4G declared; every OOM traces to torch wheel extraction. Memory bumped to 8G instead of pre-installing torch in the Dockerfile.
