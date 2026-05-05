# BenchGuard Evaluation: BIXBench-V50

## Summary
- Gold issues: 24 across 17 tasks
- Findings evaluated: 28 on revised tasks
- Models: static_audit
- Judge model: gemini/gemini-3-flash-preview

## Recall (per gold issue)
| Threshold | Count | Total | Rate |
|-----------|-------|-------|------|
| ALIGNED | 15 | 24 | 62.5% |
| ALIGNED+PARTIAL | 19 | 24 | 79.2% |

## Per-Model Recall
| Model | ALIGNED | PARTIAL+ | Total | Recall@A | Recall@A+P |
|-------|---------|----------|-------|----------|------------|
| static_audit | 15 | 19 | 24 | 62.5% | 79.2% |

## Per-Model Precision (revised tasks only)
| Model | ALIGNED | PARTIAL+ | Total | Prec@A | Prec@A+P |
|-------|---------|----------|-------|--------|----------|
| static_audit | 14 | 20 | 28 | 50.0% | 71.4% |

## Ensemble Analysis
| Strategy | Recall@ALIGNED | Recall@PARTIAL+ |
|----------|---------------|-----------------|
| Any model | 62.5% | 79.2% |
| >=2 models | 0.0% | 0.0% |
| >=3 models | 0.0% | 0.0% |

## Per-Issue Detail
| Issue ID | Task | Description | static_audit |
|----------|------|-------------|------|
| bix-11-q1_issue_1 | bix-11-q1 | The original question did not specify the required... | x |
| bix-14-q1_issue_1 | bix-14-q1 | The original question was underspecified regarding... | A |
| bix-20-q3_issue_1 | bix-20-q3 | The original question did not specify the source f... | - |
| bix-20-q3_issue_2 | bix-20-q3 | The definition of 'benign' was ambiguous regarding... | - |
| bix-22-q4_issue_1 | bix-22-q4 | The original question was ambiguous regarding whet... | - |
| bix-26-q5_issue_1 | bix-26-q5 | The original question conflated gene-level differe... | A |
| bix-27-q5_issue_1 | bix-27-q5 | The original question failed to specify the number... | A |
| bix-28-q3_issue_1 | bix-28-q3 | The original question lacked a specific tool or me... | A |
| bix-31-q2_issue_1 | bix-31-q2 | The original question lacked necessary instruction... | A |
| bix-31-q2_issue_2 | bix-31-q2 | The original question incorrectly categorized FAM1... | A |
| bix-31-q2_issue_3 | bix-31-q2 | The ideal answer range was incorrect because it di... | A |
| bix-32-q2_issue_1 | bix-32-q2 | The original question used the vague term 'KEGG en... | P |
| bix-43-q2_issue_1 | bix-43-q2 | The original question lacked specific DESeq2 confi... | P |
| bix-43-q2_issue_2 | bix-43-q2 | The statistical threshold operators were inconsist... | A |
| bix-43-q4_issue_1 | bix-43-q4 | The original question used the ambiguous phrase 'p... | A |
| bix-49-q4_issue_1 | bix-49-q4 | The original question was missing the requirement ... | A |
| bix-52-q2_issue_1 | bix-52-q2 | The original question was ambiguous regarding whet... | A |
| bix-52-q2_issue_2 | bix-52-q2 | The original question did not specify the filterin... | A |
| bix-52-q7_issue_1 | bix-52-q7 | The term 'sites' was ambiguous and could be interp... | A |
| bix-54-q7_issue_1 | bix-54-q7 | The original question lacked the specific degrees ... | A |
| bix-54-q7_issue_2 | bix-54-q7 | The term 'frequency ratio' was ambiguous and was c... | - |
| bix-54-q7_issue_3 | bix-54-q7 | The question did not specify the required software... | P |
| bix-6-q4_issue_1 | bix-6-q4 | The original question was ambiguous regarding whic... | P |
| bix-61-q2_issue_1 | bix-61-q2 | The original question was ambiguous regarding whet... | A |

## Missed Issues (no ALIGNED or PARTIAL match)
| Issue ID | Task | Description |
|----------|------|-------------|
| bix-11-q1_issue_1 | bix-11-q1 | The original question did not specify the required numerical format for the difference, leading to potential ambiguity between decimal and percentage representations. |
| bix-20-q3_issue_1 | bix-20-q3 | The original question did not specify the source for variant classification, which could lead to inconsistent results. |
| bix-20-q3_issue_2 | bix-20-q3 | The definition of 'benign' was ambiguous regarding whether it included 'Likely Benign' variants. |
| bix-22-q4_issue_1 | bix-22-q4 | The original question was ambiguous regarding whether to include all protein-coding genes or only those with sufficient expression levels for the correlation calculation. |
| bix-54-q7_issue_2 | bix-54-q7 | The term 'frequency ratio' was ambiguous and was clarified to mean the 'proportion of strain 287 in the mixtures'. |
