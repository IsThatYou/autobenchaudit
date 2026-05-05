# hf-model-inference

## Summary of changes (from PR #53 body)

- Change the tests to allow using either `save_pretrained` format or HuggingFace cache format for the model weights.

Related PRs: [#1397](https://github.com/harbor-framework/terminal-bench/pull/1397)

## Additional changes observed in diff

- Diff matches summary. `tests/test_outputs.py::test_model_downloaded` now first attempts `from_pretrained(model_path)` and on failure falls back to scanning for `models--*` directories (HF cache layout) and loading via `cache_dir=model_path`.
- Note: only `test_model_downloaded` was updated. Other tests in the file (not shown in this PR's diff) are unchanged.

## Issues found

- **Test assumed `save_pretrained` layout only** (addressed by tb#1397) — Test expected `config.json` at the `model_path` root (save_pretrained format). Agents using the HuggingFace cache format (`models--*/blobs/...`) — which is what `from_pretrained(..., cache_dir=...)` produces by default — would fail even with a correctly downloaded model. Test now tries `from_pretrained(model_path)` first and falls back to `cache_dir=model_path` after scanning for `models--*`.
