# GDPval-AA leaderboard snapshot

Snapshot of the Artificial Analysis GDPval-AA leaderboard plus auxiliary
OpenAI-auto-grader breakdowns for the same 220-task universe.

GDPval is OpenAI's benchmark of 220 real-world economically valuable
knowledge-work tasks across 9 sectors and 44 occupations, graded by
blinded pairwise comparison against a human-expert baseline.

Two independent leaderboards score models on this task universe:

- **Artificial Analysis GDPval-AA** — runs its own reference agent
  (Stirrup; shell + web) and publishes ELO from blinded pairwise
  comparisons. 336 models on the public board. Only aggregate
  `elo`, 95% CI, `n_matches`, `avg_turns`, and token use are released —
  no per-sector, per-occupation, or per-instance breakdown.
- **OpenAI auto-grader** (`evals.openai.com/gdpval/leaderboard`) —
  17 entries (16 models + human baseline) with win-rate and
  win-or-tie-rate vs the human expert, broken down by sector (9) and
  occupation (44). No per-instance.

Neither source publishes per-instance pass/fail. The closest public
per-task proxy is OpenAI's per-occupation win rates (44 buckets of 5
tasks each).

## Sources

- Artificial Analysis: `https://artificialanalysis.ai/evaluations/gdpval-aa`
  (Next.js app-router page; model data is embedded in `__next_f` JSON
  chunks as `defaultData`).
- OpenAI grader: `https://evals.openai.com/gdpval/leaderboard`
  (Vite SPA; grader data is inlined inside `/assets/index-<hash>.js` as
  JS object literals — `totals`, per-model `by_sector`, `by_occupation`).
- Task universe: `https://huggingface.co/datasets/openai/gdpval` via
  `datasets-server.huggingface.co`.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | AA — 336 rows with ELO, 95% CI, `n_matches`, `avg_turns`, token use, creator metadata, `intelligence_index`, prices. |
| `rows/<slug>.json` | AA — per-row detail (same fields, one file per model). |
| `rows_index.json` | AA — sorted summary (best ELO first), one line per row. |
| `openai_grader/overall.json` | OpenAI — 17 totals rows (`win_rate`, `win_or_tie_rate`). |
| `openai_grader/by_sector.json` | OpenAI — 153 rows (17 × 9) of per-model per-sector rates. |
| `openai_grader/by_occupation.json` | OpenAI — 748 rows (17 × 44) of per-model per-occupation rates. |
| `openai_grader_rows/<model>.json` | OpenAI — per-model file joining totals + sector + occupation. |
| `tasks.json` | 220-task universe from HuggingFace (`task_id`, `sector`, `occupation`). |
| `per_task_matrix.json` | `{task_id: {sector, occupation, openai_grader_per_occupation_proxy}}`. AA has no per-instance data; each task inherits the model's per-occupation OpenAI win rate. |
| `refresh.py` | End-to-end refresh pipeline. |

## Stats at time of snapshot

- 336 AA leaderboard rows (ELO range ≈ 231 → 1753)
- 17 OpenAI grader rows (16 models + human baseline)
- 220 canonical tasks, 9 sectors, 44 occupations
- Pairwise-ELO — no native per-instance signal from either source

## Known caveats

- AA row names include the reasoning config (e.g.
  `Claude Opus 4.7 (Adaptive Reasoning, Max Effort)`) — the same model
  family can occupy several rows.
- AA model slugs (`claude-opus-4-7`) and OpenAI grader model ids
  (`claude-45`) are **not** interoperable. Join by model family manually
  if you need both views.
- `per_task_matrix.json` is a coarse proxy: every task in the same
  occupation gets the same number. Use for occupation-level analyses
  and recomputations, not per-instance audits.

## Refreshing

```sh
python refresh.py                 # full refresh (~30s)
python refresh.py --skip-aa       # reuse existing leaderboard.json
python refresh.py --skip-openai   # reuse existing openai_grader/*.json
python refresh.py --skip-tasks    # reuse existing tasks.json
```

No auth needed — all sources are public.

## Recomputing per-occupation rankings

```python
import json
oai = json.load(open("openai_grader/by_occupation.json"))["entries"]
subset = {"Software Developers", "Lawyers"}
by_model = {}
for r in oai:
    if r["occupation"] not in subset:
        continue
    by_model.setdefault(r["model"], []).append(r["win_or_tie_rate"])
ranking = sorted(
    ((m, sum(rs) / len(rs)) for m, rs in by_model.items()),
    key=lambda x: -x[1],
)
```
