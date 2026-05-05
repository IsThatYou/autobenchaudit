# MMMU-Pro leaderboard snapshot

Snapshot of the MMMU-Pro leaderboard maintained at
`mmmu-benchmark.github.io`. MMMU-Pro (arXiv:2409.02813) is a multimodal
multi-discipline benchmark — 1,730 college-level multiple-choice
questions across 30 subjects grouped into 6 domains.

## Sources

Three places publish MMMU-Pro artifacts. We pull from all three:

| Source | What we take | Models covered |
| --- | --- | --- |
| `mmmu-benchmark.github.io` (leaderboard_data.json) | All 73 leaderboard rows | 73 models (aggregate only) |
| MMMU-Benchmark/MMMU GitHub (`mmmu-pro/output/`) | 4 JSONL prediction dumps | GPT-4o (0513) |
| `VLMEval/OpenVLMRecords` on HuggingFace | 12 xlsx prediction dumps | 7 open-weight VLMs |

Concrete URLs:

- **Leaderboard JSON**: <https://raw.githubusercontent.com/MMMU-Benchmark/MMMU-Benchmark.github.io/main/leaderboard_data.json>
- **Project page**: <https://mmmu-benchmark.github.io/>
- **GPT-4o dumps**: <https://github.com/MMMU-Benchmark/MMMU/tree/main/mmmu-pro/output>
- **VLMEvalKit dumps**: <https://huggingface.co/datasets/VLMEval/OpenVLMRecords/tree/main/mmeval>
  (backs the public OpenVLM Leaderboard HF Space)
- **Task dataset**: <https://huggingface.co/datasets/MMMU/MMMU_Pro>
- **Eval code**: <https://github.com/MMMU-Benchmark/MMMU/tree/main/mmmu-pro>

## Test configs

MMMU-Pro ships three test configs, all built on the same 1,730 questions:

| Config | Options | Image format | Leaderboard column |
| --- | --- | --- | --- |
| `standard (4 options)` | 4-way MCQ | question text + separate images | *(not reported)* |
| `standard (10 options)` | 10-way MCQ | question text + separate images | **`original`** → `pro_standard` |
| `vision` | 10-way MCQ | question + choices rendered into one screenshot; model OCRs | **`vision`** → `pro_vision` |

The headline `overall` column is the **average** of `vision` and
`original` (CoT prompting). Newer entries (mid-2024 onward) self-report
`overall` only — `vision` and `standard` cells are `null` for those.

## Per-instance data — 8 models, 16 runs

| Slug | Model | Config | Mode | Source | Acc. |
| --- | --- | --- | --- | --- | ---: |
| `gpt-4o__standard10_cot` | GPT-4o (0513) | standard (10 options) | CoT | MMMU authors | 55.03% |
| `gpt-4o__standard10_direct` | GPT-4o (0513) | standard (10 options) | direct | MMMU authors | 40.12% |
| `gpt-4o__vision_cot` | GPT-4o (0513) | vision | CoT | MMMU authors | 50.06% |
| `gpt-4o__vision_direct` | GPT-4o (0513) | vision | direct | MMMU authors | 42.43% |
| `InternVL2-8B__standard10` | InternVL2-8B | standard (10 options) | direct | VLMEvalKit | 24.22% |
| `InternVL2-8B__vision` | InternVL2-8B | vision | direct | VLMEvalKit | 13.76% |
| `InternVL2_5-8B__standard10` | InternVL2_5-8B | standard (10 options) | direct | VLMEvalKit | 28.61% |
| `InternVL2_5-8B__vision` | InternVL2_5-8B | vision | direct | VLMEvalKit | 16.30% |
| `Qwen2-VL-2B-Instruct__standard10` | Qwen2-VL-2B-Instruct | standard (10 options) | direct | VLMEvalKit | 17.75% |
| `Qwen2-VL-2B-Instruct__vision` | Qwen2-VL-2B-Instruct | vision | direct | VLMEvalKit | 14.68% |
| `Qwen2-VL-7B-Instruct__standard10` | Qwen2-VL-7B-Instruct | standard (10 options) | direct | VLMEvalKit | 27.98% |
| `Qwen2.5-VL-3B__standard10` | Qwen2.5-VL-3B | standard (10 options) | direct | VLMEvalKit | 26.71% |
| `Qwen2.5-VL-3B__vision` | Qwen2.5-VL-3B | vision | direct | VLMEvalKit | 19.25% |
| `Qwen2.5-VL-7B__standard10` | Qwen2.5-VL-7B | standard (10 options) | direct | VLMEvalKit | 28.73% |
| `Qwen2.5-VL-7B__vision` | Qwen2.5-VL-7B | vision | direct | VLMEvalKit | 20.29% |
| `llava_onevision_qwen2_7b_si__standard10` | LLaVA-OneVision-7B (si) | standard (10 options) | direct | VLMEvalKit | 22.43% |

Every other leaderboard row (57 of 73) is aggregate-only and lands in
`rows_index.json` → `missing_detail`.

### VLMEvalKit scores are direct-mode (no CoT)

The VLMEvalKit record dumps are the **non-CoT** runs. The MMMU-Pro
leaderboard `pro_standard` / `pro_vision` cells are typically CoT
numbers, which can be 5–10pp higher. Don't compare our `pass_rate_pct`
directly to the leaderboard's `pro_standard`:

| Model | Our 10c (direct) | Leaderboard `pro_standard` (CoT) |
| --- | ---: | ---: |
| InternVL2-8B | 24.2% | 32.5% |
| InternVL2_5-8B | 28.6% | 38.2% |
| LLaVA-OneVision-7B | 22.4% | 29.5% |

The upstream xlsx files also include `_COT.xlsx` variants where the
prediction column is a raw reasoning trace — VLMEvalKit runs a judge
LLM to extract the final letter. We **don't replicate that judge pass**
(it would require an API key and a non-deterministic inference run), so
CoT xlsx files are skipped. Add them later if needed.

## Letter extraction caveat

GPT-4o dumps carry an `if_right` bool — trust that field. VLMEvalKit
xlsx files store raw `prediction` strings. Most rows are clean letters
("B") but some models (e.g. Qwen2-VL-2B) emit strings like `"A. Political
instability..."` or `"Answer: C. Gavin Hamilton"`. We extract the
leading A–J with a small regex (`extract_choice_letter` in
`refresh.py`). This is a simpler approximation of VLMEvalKit's own
judge-based extractor — expect ±1pp vs. their published numbers on
models whose outputs are verbose.

## Stats at time of snapshot

- 73 leaderboard rows (37 with only `overall`; 36 with all three columns)
- 1,730 tasks
  - Domain: 417 Tech & Engineering, 291 Science, 286 Business,
    286 Health & Medicine, 228 Art & Design, 222 Humanities & Social Sci
  - Difficulty: 528 Easy, 801 Medium, 401 Hard
- 16 per-task runs (8 unique models × 1–4 config/mode variants each)
- Human Expert (High/Medium/Low): 85.4 / 80.8 / 73.0

## Top 10 by `pro_overall`

| Model | Type | Overall | Vision | Standard |
| --- | --- | ---: | ---: | ---: |
| Human Expert (High) | human_expert | 85.4 | 85.4 | 85.4 |
| GPT-5.4 Thinking w/ tools | proprietary | 82.1 | – | – |
| GPT-5.4 Thinking w/o tools | proprietary | 81.2 | – | – |
| Gemini 3.0 Pro | proprietary | 81.0 | – | – |
| Human Expert (Medium) | human_expert | 80.8 | 80.8 | 80.8 |
| Gemini 3.1 Pro Thinking (High) | proprietary | 80.5 | – | – |
| Muse Spark Thinking | proprietary | 80.4 | – | – |
| GPT-5.2 Thinking w/o Python | proprietary | 80.4 | – | – |
| GPT-5.2 Thinking w/o tools | proprietary | 79.5 | – | – |
| GPT-5.1 Thinking | proprietary | 79.0 | – | – |

## Files

| File | What it is |
| --- | --- |
| `leaderboard.json` | 73 entries with `pro_*` scores + secondary MMMU-val / MMMU-test fields. |
| `rows/<slug>.json` | 73 leaderboard row files (empty `tasks`) **plus** 16 synthetic detail rows (4 GPT-4o + 12 VLMEvalKit) carrying per-task scores. |
| `rows_index.json` | 16 detail rows + `missing_detail` for 73 leaderboard entries sorted by overall. |
| `per_task_matrix.json` | `{task: {run_slug: {pass_rate, n_trials, n_success, pred}}}` across 16 runs. `tasks` carries subject/domain/difficulty labels for all 1,730. ~4.5 MB. |
| `predictions/*.{jsonl,xlsx}` | Cached source dumps so re-runs don't re-download (~12 MB total). |
| `refresh.py` | End-to-end refresh pipeline. |

## Refreshing

```sh
python refresh.py                  # full refresh (~30s, hits 3 sources)
python refresh.py --skip-scrape    # reuse existing leaderboard.json
python refresh.py --skip-predict   # reuse predictions/*.jsonl on disk
python refresh.py --skip-vlmeval   # GPT-4o only (stdlib — no openpyxl needed)
```

`openpyxl` is required for VLMEvalKit ingestion (`pip install openpyxl`).
Everything else is stdlib. `refresh.py` clears stale `rows/*.json`
before writing so renames in `leaderboard_data.json` don't leave
orphaned files.

## Recomputing accuracy on a task subset

```python
import json
m = json.load(open("per_task_matrix.json"))
# E.g. all Hard Science questions
subset = {
    t["task_id"]
    for t in m["tasks"]
    if t["domain"] == "Science" and t["topic_difficulty"] == "Hard"
}
for run in m["runs"]:
    hits = [m["matrix"][tid][run["slug"]]["pass_rate"]
            for tid in subset if run["slug"] in m["matrix"].get(tid, {})]
    print(f"{run['slug']}: {sum(hits)/len(hits)*100:.1f}%  (n={len(hits)})")
```

## Caveats

- **Per-instance data ceiling is 8 models** (GPT-4o + 7 VLMEvalKit
  open-weight VLMs). Every other row is aggregate only.
- **Leaderboard drift vs. published predictions**: e.g. leaderboard's
  GPT-4o `pro_standard`=54.0 but the published CoT dump recomputes to
  55.0% — same variant, different scoring run. Trust the dump for
  task-level audits; trust the leaderboard for rankings.
- **VLMEvalKit xlsx are direct (non-CoT) mode**. To recover CoT-mode
  per-task pass/fail, either run the judge-extraction pass on the
  upstream `_COT.xlsx` files yourself, or contribute the extraction
  logic to this repo.
- **`pro_source: "author"`** on most newer entries — self-reported. No
  maintainer verification gate.
- **`pro.original`** is the upstream key name we remapped to
  `pro_standard` for clarity; the `standard (10 options)` config is
  what "original" refers to.
- **Duplicate model names** (e.g. multiple "Claude Opus 4.6" variants
  w/ and w/o tools) share a family but are distinct rows. Slug
  collisions get a `__N` suffix.
