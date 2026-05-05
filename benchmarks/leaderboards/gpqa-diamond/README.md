# GPQA Diamond leaderboard snapshot

Snapshot of a public aggregate leaderboard for **GPQA Diamond** — the
198-question subset of GPQA (Rein et al. 2024, arXiv:2311.12022) where
three expert validators all agreed on the gold answer.

## Sources

- **Aggregate leaderboard**:
  [`artificialanalysis.ai/evaluations/gpqa-diamond`](https://artificialanalysis.ai/evaluations/gpqa-diamond).
  Next.js SSR page. `refresh.py` extracts two arrays from
  `self.__next_f.push` chunks:
  - `"models":[...]` — metadata catalogue (id, slug, name, creator,
    `isReasoning`, `deprecated`).
  - `"defaultData":[...]` — per-model scores, joined by `id`. The
    `gpqa` field is AA's in-house measured GPQA Diamond score; the
    `lab_claimed_gpqa` field is the vendor-reported number (often null).
  The AA-measured score is the headline — it's the one number that has
  been run under a consistent harness across all 462 models.
- **Task universe**:
  [`hendrydong/gpqa_diamond`](https://huggingface.co/datasets/hendrydong/gpqa_diamond)
  — ungated mirror of the 198 Diamond questions. The canonical
  `Idavidrein/gpqa` dataset is gated behind a contact-sharing
  agreement, and its `Record ID` column is not surfaced in ungated
  mirrors, so we derive a stable `task_id` from sha256(problem)[:12].

## No per-instance data

Unlike SWE-bench Verified, **no public source publishes per-model,
per-question pass/fail data for GPQA Diamond at frontier scale**:

- `Idavidrein/gpqa` is gated; the official `dataset.zip` on GitHub is
  password-protected specifically to limit contamination. The mirrors
  we use carry questions but no predictions.
- **HELM** runs GPQA but on the 448-question `gpqa_main` subset, with
  instance text encrypted in `instances.json` (ID keys like
  `id0..id445`, no way to slice the Diamond subset without decryption
  access).
- **Open LLM Leaderboard v2** dumps per-sample GPQA Diamond outputs
  (`samples_gpqa_diamond_*.json`) but the `details_*` datasets are
  gated.
- **Epoch AI Inspect logs** preserve the canonical `Record ID` and
  cover frontier models, but the log viewer is CAPTCHA-gated and there
  is no bulk download endpoint.

We mirror the HLE leaderboard pattern: every row lives under
`missing_detail`, and `per_task_matrix.json` is populated with the 198
task IDs but empty cells (shape placeholder). If a consumer later
ingests per-instance data, they can join via `question_hash`
(sha256(problem)[:12]) or `hf_row_idx`.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 462 aggregate rows sorted by AA-measured accuracy. |
| `tasks.json` | 198 canonical Diamond task IDs with domain + hash metadata (no question text — see notes on the license). |
| `rows/<slug>.json` | Per-row detail + 198-entry zeroed `tasks` array for shape parity. |
| `rows_index.json` | One-line summary per row, sorted by accuracy; all rows under `missing_detail`. |
| `per_task_matrix.json` | `{tasks: [...198 ids...], matrix: {id: {}}}` — empty cells. |
| `refresh.py` | End-to-end refresh pipeline. |

## Stats at time of snapshot

- 462 leaderboard rows (all with AA-measured `gpqa` score)
- 198 canonical Diamond tasks
- 0 rows with per-instance data (all under `missing_detail`)

Top of the board (AA-measured, 0–1):

| Accuracy | Model | Creator |
| --- | --- | --- |
| 0.941 | Gemini 3.1 Pro Preview | Google |
| 0.935 | GPT-5.5 (xhigh) | OpenAI |
| 0.932 | GPT-5.5 (high) | OpenAI |
| 0.926 | GPT-5.5 (medium) | OpenAI |
| 0.920 | GPT-5.4 (xhigh) | OpenAI |
| 0.915 | GPT-5.3 Codex (xhigh) | OpenAI |
| 0.914 | Claude Opus 4.7 (Adaptive Reasoning, Max Effort) | Anthropic |
| 0.911 | Grok 4.20 0309 v2 (Reasoning) | xAI |
| 0.911 | Kimi K2.6 | Moonshot AI |

## Refreshing

```sh
python refresh.py                  # full refresh
python refresh.py --skip-scrape    # reuse cached AA HTML
python refresh.py --skip-tasks     # reuse cached HF parquet
```

No auth required. The AA HTML (~7 MB) and the HF parquet (~60 KB) are
cached under `.cache/` and reused when the corresponding `--skip-*`
flag is passed.

## Caveats

- **Single-source leaderboard.** Unlike SWE-bench (official leaderboard
  with published run configs), GPQA Diamond has no canonical public
  leaderboard. We use Artificial Analysis as the source of truth
  because it's the only site that runs every model under its own
  harness (so scores are directly comparable). AA's harness details
  are described at
  [artificialanalysis.ai/methodology](https://artificialanalysis.ai/methodology).
- **AA vs. vendor-reported.** `lab_claimed_accuracy` is the number the
  provider reported in a blog post or technical report; `accuracy` is
  AA's measurement. These often disagree by several points because of
  sampling, prompting, and harness differences. AA's number is the
  head-to-head comparable one.
- **Reasoning knobs.** Models often appear multiple times with
  different reasoning-effort settings (`xhigh`, `high`, `medium`,
  `low`, non-reasoning). These are separate rows, not duplicates.
  `is_reasoning` captures whether the row uses reasoning mode.
- **Contamination.** GPQA is fully public in the clear (with a
  password-protected zip and a canary string for contamination
  testing). AA does not surface a contamination flag per-row, but
  nearly every post-release frontier submission is potentially
  contaminated — treat absolute scores cautiously.
- **Dataset license.** We don't persist question text or gold answers
  in `tasks.json` — the upstream GPQA license is intentionally
  restrictive to discourage contamination. Pull the HF mirror directly
  if you need question text and join via `hf_row_idx` or
  `question_hash`.

## Recomputing accuracy on a task subset

Until per-instance data becomes available, subset recomputation is not
possible for GPQA Diamond. The matrix is shaped correctly so the
recipe used elsewhere still works once cells are populated:

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"gpqa_diamond_b698ebb0cb6d", ...}  # e.g. physics-only
by_row = {}
for task in subset:
    for slug, agg in m["matrix"].get(task, {}).items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```
