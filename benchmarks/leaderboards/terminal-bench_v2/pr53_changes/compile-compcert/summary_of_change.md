# compile-compcert

## Summary of changes (from PR #53 body)

- Add nproc wrapper. Workaround given that `nproc` inside a Docker container returns the **host** CPU count, not the container's limit.

## Additional changes observed in diff

- `task.toml`: docker image bumped from `alexgshaw/compile-compcert:20251031` → `:20260403`. Implicit, expected given the Dockerfile changes.
- The nproc wrapper is hardcoded to `echo 2` (matches `cpus = 2` in `task.toml`).

## Issues found

- **`nproc` returns host CPU count inside container** (addressed) — Same class as caffe-cifar-10. Agents running `make -j$(nproc)` spawn more parallel `coqc` processes than the container's 2-CPU cap, inflating memory. `nproc` wrapper pins output to `echo 2`.
- **Memory too tight for parallel exploration** (NOT addressed) — Audit commenter giansegato profiled 11.4G peak vs. 4G declared, 11–14% OOM cross-family. Root cause: oracle uses serial `make -j1 OPAMJOBS=1`; agents using the documented `make -j$(nproc)` trigger parallel `coqc` and OOM. Memory limit was NOT bumped. PR author's rationale: pass rates are already >30% for terminus-2, so the limit stands.
