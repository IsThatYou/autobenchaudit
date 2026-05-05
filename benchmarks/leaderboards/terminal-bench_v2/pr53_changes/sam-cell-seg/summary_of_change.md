# sam-cell-seg

## Summary of changes (from PR #53 body)

- Update task description with `--` prefixes for argument names (`weights_path` → `--weights_path`, etc.).
  - Writing these without `--` (as in previous version) suggests they should be positional arguments, but tests explicitly need them to be 'required optional' arguments

## Additional changes observed in diff

- Diff matches the summary. All four args (`weights_path`, `output_path`, `rgb_path`, `csv_path`) get the `--` prefix in `instruction.md`.

## Issues found

- **Prompt vs. test argument-form mismatch** (addressed) — Prompt wrote argument names without `--` prefix (`weights_path`, etc.), which reasonably reads as positional; but the test invokes them as required `--`-prefixed options. Agents implementing positional args would fail. All four args now carry `--` in the prompt. Audit finding `sam-cell-seg-argparse-flag-vs-positional` (Major/ambiguity) — supported.
- **High OOM rate on Google models** (NOT addressed) — Reviewer (giansegato) profiled 46% OOM for Google; peak 4–11G vs. 4G declared. One in five agents installed CUDA torch (11G) vs. CPU torch (4G). PR #53 author said they'd check with task creator before changing limits; no change landed in PR #53.
- **Internal contradiction on `output_path`: folder vs. file** (NOT addressed) — Prompt describes `output_path` as "the path to the output folder" but the test invokes it as a CSV file path, and the prompt itself later refers to it as "this file". PR #53 only adds `--` prefixes; the folder/file contradiction in the argument description is untouched. Audit finding `sam-cell-seg-output-path-folder-vs-file` (Minor/ambiguity) — not supported.
