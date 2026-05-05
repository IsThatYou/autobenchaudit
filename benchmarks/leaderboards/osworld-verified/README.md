# OSWorld-Verified leaderboard snapshot

Snapshot of the public OSWorld-Verified leaderboard plus per-task scores
reconstructed from the public trajectory dataset. 361-task computer-use /
desktop-agent benchmark from XLANG (HKU), re-verified 2025-07-28.

## Sources

OSWorld-Verified publishes leaderboard and trajectory data in two places.
We pull from both:

**Aggregate (every submission):**
[`https://os-world.github.io/static/data/osworld_verified_results.xlsx`](https://os-world.github.io/static/data/osworld_verified_results.xlsx)

The project page ([os-world.github.io](https://os-world.github.io/)) is a
static site that loads this XLSX client-side. 139 submission rows × 10
app-category success counts. Cells like `"16.96/46"` = (success / total),
where success can be fractional (OSWorld evaluators return floats in [0,1]).

**Per-task (for submissions with trajectories):**
[`https://huggingface.co/datasets/xlangai/ubuntu_osworld_verified_trajs`](https://huggingface.co/datasets/xlangai/ubuntu_osworld_verified_trajs)

85 trajectory ZIPs (1–25 GB each, ~435 GB total). Each zip contains
`<model>/<category>/<task_uuid>/result.txt` — a scalar score in [0,1]. To
avoid the 435 GB download, `refresh.py` uses HTTP Range requests to stream
**only the `result.txt` entries** from the remote zips:

  1. Prefetch the last 2 MiB → parse the ZIP central directory.
  2. For each `result.txt` entry: one ranged GET covering the local file
     header + compressed data (~300 bytes each).
  3. Decompress in-memory, extract the float, done.

A 1.2 GB zip takes ~20 s (360-ish small HTTPS requests in parallel); a
20-ish GB zip takes the same — the constant is the number of entries, not
the file size.

Canonical 361-task universe comes from `all_result.json` at the root of the
HF dataset (it's Python-literal, `ast.literal_eval`, not JSON — a known
upstream quirk).

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 139 aggregate rows from the XLSX — overall accuracy + per-category success counts + run config. |
| `rows/<slug>.json` | Per-row detail: metadata + per-category stats + a `trajectory_zip_slug` pointer if we auto-matched this row to a zip. |
| `rows_index.json` | Sorted one-line summary (by overall success rate). Also reports which zips carry per-task data but have no matched row (`unreferenced_zips`). |
| `per_task_matrix.json` | `{task_uuid: {col_slug: {score, n_trials, n_success, category, trajectory_zip_slug}}}` — cells are float scores in [0,1]; `n_success` is binarised at `score >= 1.0`. Columns are keyed by **leaderboard row slug** when a zip maps to one or more rows via `trajectory_zip_slug`; zips without a matching row keep their zip slug so the data stays addressable. Every cell carries `trajectory_zip_slug` for zip-level provenance. |
| `tasks.json` | Canonical 361 task universe: `{task_id: uuid, category}`. |
| `_per_task_cache/` | Per-zip JSON cache so reruns can skip already-extracted zips. |

## Stats at time of snapshot

- **139** leaderboard rows (60 unique models × {15, 50, 100}-step budgets,
  some with multi-rollout repeats)
- **361** tasks across 10 app categories: `chrome`, `gimp`, `libreoffice_calc`,
  `libreoffice_impress`, `libreoffice_writer`, `multi_apps`, `os`,
  `thunderbird`, `vlc`, `vs_code`
- pass@1 by default (the `multiple_rollout` column marks opt-in multi-trial;
  only ~2 of 139 rows set it)

### Top 10 by overall success rate

| Model | Institution | Steps | Success rate | Date |
| --- | --- | ---: | ---: | --- |
| Holo3-35B-A3B | H Company | 100 | 82.56 | 2026-04-20 |
| OpenAPA | Laiye | 100 | 78.34 | 2026-04-17 |
| Holo3-35B-A3B | H Company | 100 | 78.15 | 2026-04-20 |
| HIPPO Agent w/ Opus 4.5 | Lenovo | 100 | 74.48 | 2026-02-25 |
| Kimi K2.6 | Moonshot AI | 100 | 73.06 | 2026-04-20 |
| agent s3 w/ Opus 4.5 + GPT-5 bBoN (N=10) | Simular | 100 | 72.58 | 2025-12-11 |
| claude-sonnet-4-6 | Anthropic | 100 | 72.11 | 2026-03-08 |
| agent s3 w/ GPT-5 bBoN (N=10) | Simular | 100 | 69.90 | 2025-10-04 |
| agent s3 w/ Opus 4.5 bBoN (N=1) | Simular | 100 | 67.46 | 2025-12-11 |
| UiPath Screen Agent w/ Opus 4.5 | UiPath | 100 | 67.14 | 2025-12-24 |

## Matching XLSX rows to trajectory zips (best-effort)

Zip filenames and XLSX model names don't share a clean schema, so the
mapping is auto-guessed per row: normalised model substring match on the
zip filename, constrained to zips carrying the row's `<max_steps>step` tag.
When no stepped zip matches, we fall back to step-less filenames (e.g.
`results_hippo_agent.zip`).

Current coverage (snapshot):

- **85 zips** have per-task data (all columns present in
  `per_task_matrix.json`).
- **64 / 139** leaderboard rows auto-matched to a zip slug.
- **38 zips** are in the matrix but have no leaderboard row pointer (often
  because the zip's name is opaque — e.g. `results_bbon_10_72_6.zip` —
  or the submission never made it onto the XLSX). `rows_index.json` lists
  them under `unreferenced_zips`; you can still recompute on a subset of
  columns by picking zip slugs directly.

If you need a specific row mapped and the auto-matcher missed it, edit
`trajectory_zip_slug` in the relevant `rows/<slug>.json` by hand — the
matrix already has the data.

## Known upstream quirks

- `all_result.json` is Python literals (`True`/`False`, single-quoted keys),
  not JSON. We parse with `ast.literal_eval`.
- XLSX dates are stored as Excel serials (e.g. `46132`); we decode to ISO.
- Some runs skipped 1–5 tasks; you'll see 352–360 tasks scored instead of
  361. Denominators in the per-category XLSX columns reflect this.
- `per_task_matrix.json` has **369** task_ids — 361 canonical + 8 tasks that
  were removed during the 2025-07-28 Verified re-cut. Those 8 only appear
  in older submissions (e.g. `results_agent_s2_*`, `results_gemini_*`).
  Use `tasks.json` → `tasks` to filter to the canonical 361.
- The `results_only` zips shipped for `maestro` are the only two dataset
  entries that are small; every other submission ships full trajectories
  (screenshots, logs), forcing the ranged-zip approach.

## Refreshing

```sh
python refresh.py                            # aggregate only (~2 s, 139 rows)
python refresh.py --with-per-task            # also fetch per-task scores from every zip
python refresh.py --with-per-task --workers 4  # tune zip-level parallelism
python refresh.py --with-per-task --only maestro  # filter by zip filename substring
```

Full per-task fetch is resume-safe: per-zip JSON caches land in
`_per_task_cache/`. Re-running picks up where the previous run left off.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"00fa164e-2612-4439-992e-157d019a8436", ...}  # task_uuids
by_col = {}
for task in subset:
    for col, cell in m["matrix"].get(task, {}).items():
        by_col.setdefault(col, []).append(cell["score"])
ranking = sorted(
    ((col, sum(xs) / len(xs)) for col, xs in by_col.items()),
    key=lambda x: -x[1],
)
```

Columns are leaderboard row slugs for zips matched to an XLSX row; zips
without a matching row keep their zip slug. Read `trajectory_zip_slug`
from any cell (or `rows_index.json`) to recover the zip identity.

OSWorld uses partial credit, so a pass-rate interpretation is slightly
lossy. Use `score` directly when summary statistics matter. Use
`n_success` (binarised at score ≥ 1.0) to get a SWE-bench-style resolved
count.

Verification: for `kimi-k26.zip`, recomputed mean over 352 scored tasks is
**72.89 %**; the XLSX lists **73.06 %**. The gap is the 9 skipped tasks
(360/361 is typical) — not a bug.
