# torch-pipeline-parallelism

## Summary of changes (from PR #53 body)

- Increase memory from 4GB to 8GB to avoid failures due to agent and verifier installation overhead (e.g., transient spikes during pip install torch).

## Additional changes observed in diff

- Diff matches the summary. Single change in `task.toml`: `memory = "4G"` → `"8G"`.

## Issues found

- **`pip install torch` memory spike OOMs at 4G cap** (addressed via limit bump) — Reviewer (giansegato) profiled 16.6G peak vs. 4G declared; every OOM traces to torch wheel extraction. Base image is bare `ubuntu:24.04`; the agent installs torch, and `test.sh` installs it again via `uvx` — so the same ~10G spike happens twice. Oracle inherently skips install, so the 50%-of-oracle heuristic missed the spike. Memory bumped to 8G.
- **Pre-installing torch was the reviewer's recommended fix; not done** — giansegato recommended baking torch into the Dockerfile to eliminate the install-time spike entirely. PR author chose the memory bump instead, with the rationale that agents should reason about and discover resource constraints themselves.
