# caffe-cifar-10

## Summary of changes (from PR #53 body)

- Increase agent timeout to 3600s (oracle solution requires about 20 minutes)
- Accept both `make` and `cmake` Caffe builds (previous test hardcoded for `make`)
- Specify solver path in task instructions to avoid ambiguity
- Add nproc wrapper. Workaround given that `nproc` inside a Docker container returns the **host** CPU count, not the container's limit.
- Increase cpus to 4 and memory to 8GB. This matches the oracle's `make -j4` and gives headroom for compilation

Related PRs: [PR #1398](https://github.com/harbor-framework/terminal-bench/pull/1398), [PR #50](https://github.com/harbor-framework/terminal-bench-2/pull/50).

## Additional changes observed in diff

- `environment/Dockerfile`: also adds `procps` to the apt install list (likely needed by the nproc wrapper / by tests). Not mentioned in summary.
- `task.toml`: docker image bumped from `alexgshaw/caffe-cifar-10:20251031` → `:20260403`. Implicit, expected given the Dockerfile changes.

## Issues found

- **Timeout too short for oracle** (addressed by tb2#50) — Oracle solution takes ~20 minutes; default agent timeout left no budget for exploration. Agent timeout bumped to 3600s.
- **Test hardcoded to `make` build** (addressed) — Previous test rejected valid `cmake` Caffe builds. Test now accepts both.
- **Solver config path ambiguous** (addressed by tb#1398) — Tests hardcoded `examples/cifar10/cifar10_quick_solver.prototxt`, but agents often created a new solver file (e.g., `cifar10_quick_solver_cpu.prototxt`) during exploration, causing tests to fail even when training succeeded. Instruction now specifies the solver path. Audit finding `caffe-cifar-10-F1` (Minor/test_quality) — supported.
- **`nproc` returns host CPU count inside container** (addressed) — Known Docker behavior. `make -j$(nproc)` caused the container to spawn more g++ processes than its CPU cap allowed, driving OOMs. Fixed with an `nproc` wrapper hardcoded to the task's CPU quota.
- **CPU/memory limits below oracle's footprint** (addressed) — Audit commenter giansegato profiled 10.6G peak vs. 2G declared, 34% cross-family OOM rate. Limits bumped to 4 CPUs / 8GB to match `make -j4` plus headroom.
