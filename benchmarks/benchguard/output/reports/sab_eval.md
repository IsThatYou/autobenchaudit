# BenchGuard Evaluation: ScienceAgentBench

## Summary
- Gold issues: 12 across 12 tasks
- Findings evaluated: 27 on revised tasks
- Models: static_audit
- Judge model: gemini/gemini-3-flash-preview

## Recall (per gold issue)
| Threshold | Count | Total | Rate |
|-----------|-------|-------|------|
| ALIGNED | 10 | 12 | 83.3% |
| ALIGNED+PARTIAL | 11 | 12 | 91.7% |

## Per-Model Recall
| Model | ALIGNED | PARTIAL+ | Total | Recall@A | Recall@A+P |
|-------|---------|----------|-------|----------|------------|
| static_audit | 10 | 11 | 12 | 83.3% | 91.7% |

## Per-Model Precision (revised tasks only)
| Model | ALIGNED | PARTIAL+ | Total | Prec@A | Prec@A+P |
|-------|---------|----------|-------|--------|----------|
| static_audit | 11 | 14 | 27 | 40.7% | 51.9% |

## Ensemble Analysis
| Strategy | Recall@ALIGNED | Recall@PARTIAL+ |
|----------|---------------|-----------------|
| Any model | 83.3% | 91.7% |
| >=2 models | 0.0% | 0.0% |
| >=3 models | 0.0% | 0.0% |

## Per-Issue Detail
| Issue ID | Task | Description | static_audit |
|----------|------|-------------|------|
| 9_issue_1 | 9 | The instruction was updated to require the square ... | A |
| 12_issue_1 | 12 | The required output format for the ranked list of ... | A |
| 21_issue_1 | 21 | The ground truth deforestation rate and its corres... | A |
| 26_issue_1 | 26 | Corrected the instruction to use the plural 'names... | A |
| 29_issue_1 | 29 | The instruction incorrectly referenced 'ecg_1000hz... | A |
| 31_issue_1 | 31 | The instruction was updated to specify the use of ... | A |
| 32_issue_1 | 32 | The analysis and visualization were updated to gro... | A |
| 34_issue_1 | 34 | The instruction was updated to remove the requirem... | A |
| 35_issue_1 | 35 | The instruction was updated to specify the exact f... | A |
| 67_issue_1 | 67 | Changed '...Save the results to 'pred_results/CogS... | - |
| 78_issue_1 | 78 | The test dataset `pucci-proteins_test.csv` contain... | A |
| 92_issue_1 | 92 | Changed '...entries in second column of H_high div... | P |

## Missed Issues (no ALIGNED or PARTIAL match)
| Issue ID | Task | Description |
|----------|------|-------------|
| 67_issue_1 | 67 | Changed '...Save the results to 'pred_results/CogSci_pattern_high_sim_data_pred.csv'....' to '...Save the similarity scores for every model...' |
