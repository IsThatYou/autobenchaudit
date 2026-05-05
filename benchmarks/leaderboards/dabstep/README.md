# DABStep (Finance Agent) leaderboard snapshot

Snapshot of the public DABStep leaderboard plus per-task pass/fail data for
every submission. Intended for recomputing leaderboards on a subset of tasks.

DABStep — **D**ata **A**gent **B**enchmark for multi-**step** reasoning — is
the Adyen/HuggingFace finance agent benchmark. Agents answer 450 questions
grounded in anonymized Adyen payments data plus domain docs (manuals, fee
tables). It was the clearest "finance agent" candidate that publishes
per-instance results for every submission.

## Sources

All artifacts live in one HuggingFace dataset repo (`adyen/DABstep`):

- **Submission index**: `data/submissions/` directory — one file per
  submission, `v1__{submission_id}__{DD-MM-YYYY}.jsonl`, 450 rows each
  containing agent answers + metadata (the `validated` flag here is the
  authoritative signal).
- **Per-task scores**: `data/task_scores/` directory — same filename
  convention, 450 rows of `{submission_id, task_id, score (bool), level,
  agent_answer}`. Programmatic scoring; one trial per task (pass@1).
- **Task universe**: `data/tasks/all.jsonl` — canonical 450-task list with
  `{task_id, level}`. Gold answers live in a private `adyen/DABstep-internal`
  repo (we don't need them — `score` is already evaluated).

Aggregation logic follows the official HF Space (`adyen/DABstep`): the
leaderboard is the groupby of `task_scores` on `(submission_id, level)` with
mean `score`, joined to submission metadata. Sorted by hard accuracy, then
easy.

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 1872 overview rows across validated + unvalidated submissions. |
| `rows/<slug>.json` | Per-row detail: metadata + per-task stats (`task_name`, `level`, `n_trials`, `n_success`, `pass_rate`). |
| `rows_index.json` | One-line summary per row, sorted by `(hard, easy, overall)` pass rate. |
| `per_task_matrix.json` | `{task: {row_slug: {pass_rate, n_trials, n_success}}}`. Use this to recompute leaderboards on a task subset. ~97 MB. |
| `refresh.py` | End-to-end refresh pipeline (HF tree paginate → JSONL download → matrix build). |

## Stats at time of snapshot

- **1872** total submissions (every submission with a scored file on HF)
- **28** validated by Adyen maintainers — the rest are self-serve / unreviewed
- **450** tasks (72 easy, 378 hard)
- 1 trial per task per submission (pass@1)

The official HF Space splits its leaderboard into `validated` (maintainer-
verified) and `unvalidated` tabs. The validated set is tiny because flipping
the bit is a manual maintainer action; several real-looking high-score
submissions remain `validated=False`. We preserve the flag on every row so
downstream code can filter.

### Top 10 validated submissions (by hard-level accuracy)

| Agent | Model family | Hard % | Easy % |
| --- | --- | ---: | ---: |
| NVIDIA KGMON (NeMo Agent Toolkit) Data Explorer | claude haiku 4.5 | 89.9 | 87.5 |
| DataPilot | Qwen3 | 87.6 | 86.1 |
| gg-agent-gpt5-1104-1 | Doubao | 63.0 | 88.9 |
| CambioML energent.ai DS Agent | GPT-5 | 57.7 | 94.4 |
| DS-STAR | Gemini-2.5-Pro | 45.2 | 87.5 |
| Amity DA Agent v0.1 | Gemini-2.5-Pro | 41.0 | 80.6 |
| AgenticData | Qwen 3 | 40.5 | 94.4 |
| Mphasis-I2I-Agents | Claude 3.5 Sonnet | 28.0 | 80.6 |
| Claude 4 Sonnet ReACT Baseline | Claude Sonnet 4 | 19.8 | 81.9 |
| Open Data Scientist | DeepSeek-V3 | 16.4 | 84.7 |

## Known upstream quirks

- Many unvalidated entries are obvious tests/spam (e.g. "Not Applicable" for
  all 450 tasks, duplicate submissions with version bumps). Filtering on
  `validated=True` gives the clean board; unvalidated rows are still useful
  for trend analysis if you trust self-reported model families.
- A handful of unvalidated submissions post scores **higher** than the top
  validated row (e.g. `OceanBase-DataPilot` at 100% hard). Treat with
  caution — the validated gate exists to catch exactly this.
- `submission_id = "{organisation}-{agent_name}"` can contain spaces, dots,
  and hyphens. We slugify filesystem paths but keep the raw `submission_id`
  in every row.

## Refreshing

```sh
python refresh.py                  # full refresh (~4-6 min with 6 workers)
python refresh.py --skip-details   # reuse rows/, rebuild aggregates only
python refresh.py --workers 8      # more parallelism — but HF rate-limits (429)
python refresh.py --validated-only # drop unvalidated submissions entirely
```

The script is resume-safe: re-running picks up where it left off by keying on
`submission_id` from existing `rows/*.json`. No auth needed — everything
comes from public HF endpoints.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
subset = {"1712", "1810", ...}          # pick your task_ids
by_row = {}
for task in subset:
    for slug, agg in m["matrix"].get(task, {}).items():
        by_row.setdefault(slug, []).append(agg["pass_rate"])
ranking = sorted(
    ((slug, sum(rs) / len(rs)) for slug, rs in by_row.items()),
    key=lambda x: -x[1],
)
```

`m["task_levels"]` is a convenience dict mapping each `task_id` to its
`easy`/`hard` level, if you want to recompute per-level aggregates on the
subset.
