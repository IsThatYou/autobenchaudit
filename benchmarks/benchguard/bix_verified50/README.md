---
license: apache-2.0
task_categories:
  - question-answering
language:
  - en
tags:
  - biology
  - bioinformatics
  - benchmark
  - bixbench
size_categories:
  - n<1K
---

# BixBench-Verified-50

A curated subset of [BixBench](https://huggingface.co/datasets/futurehouse/BixBench) with 50 verified questions across 33 unique data capsules, designed for reliable evaluation of AI agents on computational biology tasks.

## Overview

BixBench-Verified-50 was created to isolate real agent performance from benchmark issues. Starting from the full BixBench benchmark, we sampled questions and identified problematic ones. Some were removed entirely. For others, we revised the question text for clarity or corrected the expected answer, while being careful not to overcorrect: we used our best judgment to leave in questions where we believe a competent expert should be able to fill in the details themselves. Questions were reviewed together with several domain experts to ensure correctness of ground truth, sufficiency of provided context, and clarity of the expected answer.

For more context on why we created this curated subset and our approach to evaluating AI agents in biology, see our blog post: [Evaluating AI Agents in Biology: Why We Need to Look Beyond the Final Answer](https://phylo.bio/blog/evaluating-ai-agents-in-biology-why-we-need-to-look-beyond-the-final-answer).

## Revision Notes

Of the 50 questions, 17 were revised from the original BixBench training set. Changes include clarifying question wording, specifying tools or methods based on the groundtruth, and correcting ideal answers where needed. A detailed comparison is provided in **`sample50_comparison.csv`**, which contains the original and updated question/ideal for each question along with notes describing what was changed and why.

## Dataset Statistics

| Property | Value |
|----------|-------|
| Total questions | 50 |
| Unique data capsules | 33 |
| Evaluation modes | `llm_verifier` (20), `str_verifier` (17), `range_verifier` (13) |
| Categories covered | 19 distinct category combinations |

## Files

- **`BixBench-Verified-50.jsonl`** — The dataset file with all 50 questions (one per line).
- **`sample50_comparison.csv`** — Comparison of original vs. revised questions/answers with notes on each change.
- **`CapsuleFolder-{uuid}.zip`** — Data capsules containing the underlying data for each question. Each zip contains:
  - `CapsuleData-{uuid}/` — The data files needed to answer the question.
  - `CapsuleNotebook-{uuid}/` — Reference notebook with executed analysis.

## Schema

Each row in the JSONL file contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `question_id` | string | Unique question identifier |
| `question` | string | The benchmark question |
| `ideal` | string | The ideal/correct answer |
| `answer` | boolean | Whether the hypothesis was confirmed |
| `hypothesis` | string | The scientific hypothesis being tested |
| `result` | string | Results summary |
| `eval_mode` | string | Evaluation method (`str_verifier`, `range_verifier`, or `llm_verifier`) |
| `capsule_uuid` | string | UUID of the associated data capsule |
| `data_folder` | string | Name of the capsule zip file |
| `categories` | string | Research domain categories |
| `paper` | string | Associated paper reference |
| `distractors` | list | Incorrect answer choices (for multiple-choice evaluation) |
| `canary` | string | Canary string for data provenance tracking |

## Usage

```python
from datasets import load_dataset

dataset = load_dataset("yuanhaoqu/BixBench-Verified-50")
```

Or load directly with pandas:

```python
import pandas as pd

df = pd.read_json("BixBench-Verified-50.jsonl", lines=True)
```

## Citation

If you use this dataset, please cite the original BixBench paper:

```bibtex
@article{mitchener2025bixbench,
  title={BixBench: a Comprehensive Benchmark for LLM-based Agents in Computational Biology},
  author={Mitchener, Ludovico and Laurent, Jon M and Andonian, Alex and Tenmann, Benjamin and Narayanan, Siddharth and Wellawatte, Geemi P and White, Andrew and Sani, Lorenzo and Rodriques, Samuel G},
  journal={arXiv preprint arXiv:2503.00096},
  year={2025}
}
```

## License

Apache 2.0 (same as the original BixBench dataset).
