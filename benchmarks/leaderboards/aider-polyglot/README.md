# Aider Polyglot leaderboard snapshot

Aggregate-only snapshot of the public Aider Polyglot leaderboard.

## Scope — no per-task data

Unlike `terminal-bench_v2/` and `swe-bench-*/`, this snapshot does **not**
include per-exercise pass/fail. Aider never publishes that: individual
runs produce a local `tmp.benchmarks/<dirname>/` with one
`.aider.results.json` per exercise, but those folders are kept by whoever
ran the benchmark and never uploaded. Only aggregate rows are public.

Consequence: task-subset recomputation (the whole point of
`per_task_matrix.json` in the other snapshots) is not possible here. What
this snapshot supports is leaderboard ranking + cost / token / error
analysis.

## Source

Single file, mirrored from the Aider website's Jekyll data dir:

- https://github.com/Aider-AI/aider/blob/main/aider/website/_data/polyglot_leaderboard.yml

This is the exact YAML that backs https://aider.chat/docs/leaderboards/.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | All 69 rows, verbatim from the YAML, plus a header describing every field. |
| `rows_index.json` | Normalized per-row summary, sorted by `pass_rate_2` desc. Includes `accuracy = pass_rate_2 / 100` for consistency with the other snapshots. |
| `refresh.py` | Fetch + parse pipeline (pyyaml required). |

## Headline metric

`pass_rate_2` is the % of the 225 exercises solved within two attempts —
this is the score shown on aider.chat/docs/leaderboards/. `pass_rate_1`
is the first-attempt rate. Both are stored per row.

## Stats at time of snapshot

- 69 leaderboard rows (one row per model/config combination)
- 225 exercises per run (C++, Go, Java, JavaScript, Python, Rust)
- Each row includes cost, token usage, error counts, edit-format metadata

## Refreshing

```sh
python refresh.py    # fetches YAML, writes leaderboard.json + rows_index.json
```

Requires `pyyaml`. No auth needed.
