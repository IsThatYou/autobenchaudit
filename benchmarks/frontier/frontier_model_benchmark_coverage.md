# Frontier Model Benchmark Coverage

Compiled from the cited public release sources on April 13, 2026. `Y` means the benchmark is explicitly reported in the source for that model. `-` means it is not shown in that source. `Count` is the number of model sources in this table that explicitly reported the benchmark. This is publication coverage, not an exhaustive list of every internal eval a lab may have run.

Sources:
- Opus 4.6: `benchmarks/frontier/opus4.6.png`
- GPT-5.4: https://openai.com/index/introducing-gpt-5-4/
- GLM-5.1: https://huggingface.co/zai-org/GLM-5.1
- Kimi K2.5: https://huggingface.co/moonshotai/Kimi-K2.5
- MiniMax M2.7: `benchmarks/frontier/minimax_m2.7.png`

Normalization notes:
- I merged obvious naming variants: `OSWorld` / `OSWorld-Verified`, `GDPval` / `GDPval-AA`, `Humanity's Last Exam` / `HLE`, `MMMU Pro` / `MMMU-Pro`, `BrowseComp` variants, `MCP Atlas` / `MCP-Atlas`, `Finance Agent` / `FinanceAgent v1.1`, `Multi-SWE Bench` / `SWE-Bench Multilingual`, `Toolathon` / `Toolathlon`, and `MM Claw` / `MM-ClawBench`.
- I kept distinct benchmark families or versions separate when the source names imply different tests, for example `Tau2-bench` vs `tau3-Bench`, `AIME 2025` vs `AIME 2026`, and the individual `Graphwalks` / `OpenAI MRCR v2` ranges.
- For MiniMax M2.7 and Opus 4.6, the table only reflects the benchmarks visible in the provided images.

## Coding

| Benchmark | Count | Opus 4.6 | GPT-5.4 | GLM-5.1 | Kimi K2.5 | MiniMax M2.7 |
| --- | --- | --- | --- | --- | --- | --- |
| CyberGym | 2 | - | - | Y | Y | - |
| LiveCodeBench (v6) | 1 | - | - | - | Y | - |
| MLE-Bench lite | 1 | - | - | - | - | Y |
| Multi-SWE Bench / SWE-Bench Multilingual | 2 | - | - | - | Y | Y |
| NL2Repo | 1 | - | - | Y | - | - |
| OJBench (cpp) | 1 | - | - | - | Y | - |
| PaperBench | 1 | - | - | - | Y | - |
| SciCode | 1 | - | - | - | Y | - |
| SWE-Bench Pro | 4 | - | Y | Y | Y | Y |
| SWE-Bench Verified | 2 | Y | - | - | Y | - |
| Terminal-Bench 2.0 | 4 | Y | Y | Y | Y | - |
| VIBE-Pro | 1 | - | - | - | - | Y |

## Tool Use And Agent

| Benchmark | Count | Opus 4.6 | GPT-5.4 | GLM-5.1 | Kimi K2.5 | MiniMax M2.7 |
| --- | --- | --- | --- | --- | --- | --- |
| BrowseComp | 4 | Y | Y | Y | Y | - |
| DeepSearchQA | 1 | - | - | - | Y | - |
| FinanceAgent | 2 | Y | Y | - | - | - |
| FinSearchCompT2&T3 | 1 | - | - | - | Y | - |
| MCP Atlas | 3 | Y | Y | Y | - | - |
| MM-ClawBench | 1 | - | - | - | - | Y |
| Seal-0 | 1 | - | - | - | Y | - |
| Tau2-bench Retail | 1 | Y | - | - | - | - |
| Tau2-bench Telecom | 2 | Y | Y | - | - | - |
| Tool-Decathlon | 1 | - | - | Y | - | - |
| Toolathlon | 2 | - | Y | - | - | Y |
| Vending Bench 2 | 1 | - | - | Y | - | - |
| WideSearch | 1 | - | - | - | Y | - |
| tau3-Bench | 1 | - | - | Y | - | - |

## Computer Use

| Benchmark | Count | Opus 4.6 | GPT-5.4 | GLM-5.1 | Kimi K2.5 | MiniMax M2.7 |
| --- | --- | --- | --- | --- | --- | --- |
| GDPval / GDPval-AA | 3 | Y | Y | - | - | Y |
| OSWorld / OSWorld-Verified | 2 | Y | Y | - | - | - |

## Vision

| Benchmark | Count | Opus 4.6 | GPT-5.4 | GLM-5.1 | Kimi K2.5 | MiniMax M2.7 |
| --- | --- | --- | --- | --- | --- | --- |
| CharXiv (RQ) | 1 | - | - | - | Y | - |
| InfoVQA (val) | 1 | - | - | - | Y | - |
| LongVideoBench | 1 | - | - | - | Y | - |
| LVBench | 1 | - | - | - | Y | - |
| MathVision | 1 | - | - | - | Y | - |
| MathVista (mini) | 1 | - | - | - | Y | - |
| MMMU Pro | 3 | Y | Y | - | Y | - |
| MMVU | 1 | - | - | - | Y | - |
| MotionBench | 1 | - | - | - | Y | - |
| OCRBench | 1 | - | - | - | Y | - |
| OmniDocBench | 2 | - | Y | - | Y | - |
| SimpleVQA | 1 | - | - | - | Y | - |
| VideoMME | 1 | - | - | - | Y | - |
| VideoMMMU | 1 | - | - | - | Y | - |
| WorldVQA | 1 | - | - | - | Y | - |
| ZeroBench | 1 | - | - | - | Y | - |

## Reasoning And Knowledge

| Benchmark | Count | Opus 4.6 | GPT-5.4 | GLM-5.1 | Kimi K2.5 | MiniMax M2.7 |
| --- | --- | --- | --- | --- | --- | --- |
| AIME 2025 | 1 | - | - | - | Y | - |
| AIME 2026 | 1 | - | - | Y | - | - |
| ARC-AGI-1 | 1 | - | Y | - | - | - |
| ARC-AGI-2 | 2 | Y | Y | - | - | - |
| Artificial Analysis Intelligence Index | 1 | - | - | - | - | Y |
| Frontier Science Research | 1 | - | Y | - | - | - |
| FrontierMath Tier 1-3 | 1 | - | Y | - | - | - |
| FrontierMath Tier 4 | 1 | - | Y | - | - | - |
| GPQA Diamond | 4 | Y | Y | Y | Y | - |
| HMMT 2025 (Feb) | 1 | - | - | - | Y | - |
| HMMT 2025 (Nov) | 1 | - | - | Y | - | - |
| HMMT 2026 (Feb) | 1 | - | - | Y | - | - |
| Humanity's Last Exam (HLE) | 4 | Y | Y | Y | Y | - |
| IMOAnswerBench | 2 | - | - | Y | Y | - |
| MMLU-Pro | 1 | - | - | - | Y | - |
| MMMLU | 1 | Y | - | - | - | - |

## Long Context

| Benchmark | Count | Opus 4.6 | GPT-5.4 | GLM-5.1 | Kimi K2.5 | MiniMax M2.7 |
| --- | --- | --- | --- | --- | --- | --- |
| AA-LCR | 1 | - | - | - | Y | - |
| Graphwalks BFS 0K-128K | 1 | - | Y | - | - | - |
| Graphwalks BFS 256K-1M | 1 | - | Y | - | - | - |
| Graphwalks parents 0-128K | 1 | - | Y | - | - | - |
| Graphwalks parents 256K-1M | 1 | - | Y | - | - | - |
| LongBench v2 | 1 | - | - | - | Y | - |
| OpenAI MRCR v2 8-needle 4K-8K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 8K-16K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 16K-32K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 32K-64K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 64K-128K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 128K-256K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 256K-512K | 1 | - | Y | - | - | - |
| OpenAI MRCR v2 8-needle 512K-1M | 1 | - | Y | - | - | - |

## Harbor Note

In this repo, the following benchmarks can be run via `harbor/swe-bench`:
- Multi-SWE Bench / SWE-Bench Multilingual
- FinanceAgent
- ARC-AGI-2
- GPQA Diamond
- Humanity's Last Exam (HLE)

Benchmarks in `configs/frontier_benchmarks` that still need static audit here, excluding the `harbor/swe-bench` ones:
- BrowseComp
- MCP Atlas
- Tau2-bench Telecom
- Toolathlon
- GDPval / GDPval-AA
- OSWorld / OSWorld-Verified
- MMMU Pro
- OmniDocBench
- IMOAnswerBench
- LongBench v2
