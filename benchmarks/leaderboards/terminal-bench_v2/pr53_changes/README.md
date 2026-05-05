# PR #53 — Terminal-Bench 2.1 Per-Task Change Summary

Source: <https://github.com/harbor-framework/terminal-bench-2/pull/53>
Title: Terminal-Bench 2.1 — "Update instructions, tests, and resources in Terminal-Bench 2.0 tasks."
PR state at time of capture: OPEN

This directory holds one subdir per task touched by PR #53. Each subdir contains
`summary_of_change.md` with:

1. The PR body's stated **Summary of changes** for that task (verbatim where present).
2. **Additional changes observed in diff** — any file edits in PR #53 that are not
   mentioned in the PR's per-task summary (e.g., docker image rebumps, undocumented
   pin removals, side edits in test files).

Tasks documented in the PR body (22):

- adaptive-rejection-sampler
- build-pmars
- caffe-cifar-10
- compile-compcert
- configure-git-webserver
- extract-moves-from-video
- filter-js-from-html
- fix-git
- hf-model-inference
- install-windows-3.11
- make-doom-for-mips
- mteb-leaderboard
- mteb-retrieve
- polyglot-c-py
- polyglot-rust-c
- protein-assembly
- query-optimize
- rstan-to-pystan
- sam-cell-seg
- torch-pipeline-parallelism
- torch-tensor-parallelism
- train-fasttext

Tasks touched by PR #53 but **not mentioned in the body** (4):

- build-pov-ray
- financial-document-processor
- mcmc-sampling-stan
- overfull-hbox

These four are flagged in their summary files as undocumented changes.

---

## Tasks with PR #53 changes outside the ambiguity_v3 rubric

The audit rubric (`rubrics/task_rubric_ambiguity_v3.txt`) only covers prompt-vs-test
contract gaps: ambiguous/missing instructions, hidden requirements the tests enforce,
and tests that are too narrow or too broad. The tasks below have edits in PR #53 that
fall outside that scope (resource bumps, dependency rot, external-API drift, oracle
bugs, anti-cheat, library workarounds, etc.).

**Every change is outside the rubric** (no in-rubric edits in this PR):

- build-pov-ray
- compile-compcert
- financial-document-processor
- make-doom-for-mips
- mcmc-sampling-stan
- overfull-hbox
- rstan-to-pystan
- torch-pipeline-parallelism

**Mixed** (some in-rubric edits, some outside):

- adaptive-rejection-sampler
- build-pmars
- caffe-cifar-10
- extract-moves-from-video
- filter-js-from-html
- fix-git
- install-windows-3.11
- mteb-leaderboard
- mteb-retrieve
- polyglot-rust-c
- protein-assembly
- torch-tensor-parallelism
- train-fasttext

**Entirely in-rubric** (all PR #53 edits address ambiguity / underspecification /
test narrowness or breadth):

- configure-git-webserver
- hf-model-inference
- polyglot-c-py
- query-optimize
- sam-cell-seg

See each task's `summary_of_change.md` for the per-edit reasoning.
