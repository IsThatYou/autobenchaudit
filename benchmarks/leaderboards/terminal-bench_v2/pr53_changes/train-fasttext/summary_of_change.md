# train-fasttext

## Summary of changes (from PR #53 body)

- Changed tests to evaluate model from Python `fasttext.load_model()` to CLI `fasttext test` command (CLI is more reliable than Python bindings in some environments; oracle solution already uses CLI).
- Made test.sh self-contained: verifier now builds fasttext from source and installs to `/usr/local/bin/` instead of relying on agent's PATH. Removed dead Python dependencies (`scikit-learn`, `fasttext-wheel`, `numpy`).

Related PRs: [PR #1399](https://github.com/harbor-framework/terminal-bench/pull/1399)

## Additional changes observed in diff

- Diff matches the summary. `tests/test.sh` adds `git build-essential`, clones and builds fastText from source. `tests/test_outputs.py::test_accuracy` switches to subprocess-invoking the `fasttext` CLI and parses `P@1` from stdout.
- Threshold change worth noting (not in summary): the CLI-based test uses `assert accuracy >= ACCURACY_THRESHOLD` (>=), whereas the previous Python-based test used `assert accuracy > ACCURACY_THRESHOLD` (strict >). Boundary semantics differ at the threshold value (0.62).

## Issues found

- **`fasttext-wheel` library bug: can't load its own saved models** (addressed by tb#1399) — The `fasttext-wheel` Python library's `load_model()` fails on models saved by its own `train_supervised()` call, though it can load models trained by the official C++ `fasttext` CLI. Test rewritten to subprocess-invoke the `fasttext` CLI's `test` command and parse `P@1` from stdout.
- **Verifier previously depended on agent's PATH** (addressed) — `test.sh` now clones and builds fasttext from source and installs to `/usr/local/bin/`, isolating verification from whatever the agent installed. Dead Python deps (`sklearn`, `fasttext-wheel`, `numpy`) removed.
- **Assertion boundary semantics changed** — CLI-based test uses `>=` vs. prior Python test's `>`. At threshold 0.62, a model scoring exactly 0.62 now passes (previously failed). Not flagged in the PR summary.
- **Memory tight vs. agent-chosen `-dim`** (NOT addressed) — Reviewer (giansegato) profiled 11.5G peak vs. 4G declared. Oracle uses `-dim 5` (tiny embedding); agents picking standard fastText values `-dim 50`–`150` OOM. PR author noted the "model must be <150MB" instruction line makes this out of scope for further limit changes, but the mismatch between oracle footprint and agent-exploration footprint remains.
