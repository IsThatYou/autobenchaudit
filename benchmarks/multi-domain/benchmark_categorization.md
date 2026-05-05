# Multi-Domain Benchmark Categorization

This file groups the benchmark inventory into paper-facing domains for a NeurIPS submission. The goal is to make the benchmark-audit contribution read as a multi-domain evaluation study, rather than a coding/agent-only study.

Primary categories are not exclusive. Several benchmarks span multiple areas, but each is placed where it best supports the coverage story.

The unique domains in `ranked_benchmarks_popularity.json` are `agent_interactive`, `audio_speech`, `code_swe`, `creative_generation`, `embodied_3d`, `eval_methodology`, `medical_health`, `multimodal_vision`, `nlp_text`, `professional_economic_work`, `reasoning_math`, `remote_sensing`, `retrieval_rag`, `safety_alignment`, `science_expert_reasoning`, and `video_understanding`.

## Paper Benchmark Portfolio

Consolidated list of benchmarks for the NeurIPS submission. Combines the
paper-facing portfolio (audits driven from public leaderboards / external
sources) with the local NeurIPS Benchmark Track audits in
`data/bench_audit/multi_domain/v3/neurips/` (driven from configs in
`bench_audit/configs/multi_domain/`).

The current paper benchmark portfolio contains 46 benchmarks across nine paper-facing domains.

Audit status:
- **Audited** — local benchmark-level audit record present in
  `data/bench_audit/multi_domain/v3/neurips/<bench>__v1__actual/`.
- **Audited (external)** — audited via leaderboard / external trajectory data,
  no local NeurIPS audit dir.
- **Pending** — listed for paper coverage but no audit yet.

Task counts come from `artifact_manifest.yaml` for local audits; findings counts
sum `category_verdicts.*.findings` from `benchmark_audit.json`. `—` means the
field is not yet populated.

### Science / expert reasoning

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| HLE (Humanity's Last Exam) | Audited (external) | — | 10 |
| GPQA Diamond | Pending | — | — |
| SuperGPQA | Audited | 26,529 | 8 |
| PhysGym | Audited | 97 | 15 |
| Beyond Chemical QA (ChemCoTBench) | Audited | 1,485 | 16 |

### Multimodal / academic / document / visual reasoning

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| MMMU-Pro | Audited (external) | — | 10 |
| OCRBench v2 | Audited | 10,000 | 20 |
| From Flatland to Space | Audited | 7,211 | 12 |
| MMLongBench | Pending | 7,801 | — |
| DisasterM3 | Pending | 30,042 | — |

### Professional / economic work

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| GDPval AA | Audited (external) | — | 9 |
| Vals Finance Agent | Audited (external) | — | 12 |
| DABstep | Audited (external) | 450 | 9 |
| OfficeQA Pro | Pending | 133 | — |

### Interactive / agentic / tool-use

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| OSWorld Verified | Audited (external) | — | 9 |
| Toolathlon | Audited (external) | — | 0 |
| Tau2-Bench Telecom | Audited (external) | — | 5 |
| TheAgentCompany | Pending | 175 | — |
| ALE-Bench | Pending | 40 | — |

### Coding / SWE / terminal

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| SWE-Bench Verified | Audited (external) | — | 15 |
| SWE-Bench Pro | Audited (external) | — | 11 |
| SWE-Bench Multilingual | Audited (external) | — | 12 |
| Frontier SWE | Audited (external) | — | 9 |
| Terminal-Bench v2 | Audited (external) | — | 17 |
| Aider Polyglot | Audited (external) | — | — |

### Medical / clinical

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| ClinicalLab | Audited | 16 | 19 |
| MedChain | Audited | 2,362 | 23 |
| MTBBench | Audited | 573 | 22 |
| OralGPT (Dental AI) | Pending | 1,069 | — |
| EndoBench | Pending | 6,832 | — |

### Math / formal reasoning

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| MathArena | Audited | 951 | 13 |
| AIME 2024 + 2025 | Audited (external) | 60 | 12 |
| IMOAnswerBench | Audited (external) | 400 | 8 |
| RealMath | Pending | — | — |
| IneqMath (Solving Inequality Proofs) | Pending | 300 | — |
| OMEGA | Pending | 9,715 | — |

### Retrieval / RAG / search

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| Mind2Web 2 | Audited | 10 | 12 |
| FreshStack | Audited | 672 | 12 |
| C-SEO Bench | Audited | 1,921 | 8 |
| MMDocRAG | Pending | 4,055 | — |
| KGQAGen | Pending | 10,787 | — |

### Safety / alignment

| Benchmark | Audit status | Tasks | Findings |
| --- | --- | ---: | ---: |
| OpenUnlearning | Audited | 48 | 5 |
| BackdoorLLM | Audited | 4,200 | 19 |
| Artificial Hivemind | Audited | 1,350 | 13 |
| WASP (Web Agent Security) | Pending | 21 | — |
| OS-Harm (Computer-Use Agents) | Pending | 110 | — |

### Excluded from the paper portfolio

These appeared in earlier portfolio drafts but are not part of the current
paper scope:

- OmniDocBench — dropped from document / long-context coverage.
- LongBench v2 — dropped from document / long-context coverage.
- MMAR — audio / speech / music reasoning not in scope.

## Priority Static-Audit Domains

All nine domains are now in scope for the comprehensive audit run. This section enumerates every NeurIPS 2025 D&B Track benchmark whose primary category (the first value in `domain_categories`) falls into one of the nine paper-facing buckets, drawn from `ranked_benchmarks_popularity.json`. Privacy/security benchmarks remain folded into `safety_alignment`; secondary labels are preserved in the `Other categories` column.

Within each domain, the table is split into two groups:

- **Sampled** — already configured under `bench_audit/configs/multi_domain/`. These were the initial pilot subset for the paper portfolio. Cross-domain placements (e.g. WASP audited under `safety_alignment/` though its primary is `agent_interactive`) are noted in the config path.
- **Remaining** — primary-domain benchmarks not yet configured. Configs for these are generated under `bench_audit/configs/multi_domain_all/<domain>/`.

### medical_health (17)

**Sampled (5 / 17)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [ClinicalLab: Aligning Agents for Multi-Departmental Clinical Diagnostics in the Real World](https://github.com/WeixiangYAN/ClinicalLab) _(config: `multi_domain/medical_health/clinicallab.yaml`)_ | 0.4483 | 133 | none | NeurIPS D&B poster |
| [Towards Better Dental AI: A Multimodal Benchmark and Instruction Dataset for Panoramic X-ray Analysis](https://github.com/isbrycee/OralGPT) _(config: `multi_domain/medical_health/oralgpt.yaml`)_ | 0.4278 | 81 | multimodal_vision | NeurIPS D&B poster |
| [EndoBench: A Comprehensive Evaluation of Multi-Modal Large Language Models for Endoscopy Analysis](https://github.com/CUHK-AIM-Group/EndoBench) _(config: `multi_domain/medical_health/endobench.yaml`)_ | 0.4041 | 59 | none | NeurIPS D&B poster |
| [MedChain: Bridging the Gap Between LLM Agents and Clinical Practice with Interactive Sequence](https://github.com/ljwztc/MedChain) _(config: `multi_domain/medical_health/medchain.yaml`)_ | 0.3869 | 49 | none | NeurIPS D&B spotlight |
| [MTBBench: A Multimodal Sequential Clinical Decision-Making Benchmark in Oncology](https://github.com/bunnelab/MTBBench) _(config: `multi_domain/medical_health/mtbbench.yaml`)_ | 0.3416 | 30 | none | NeurIPS D&B poster |

**Remaining (12 / 17)** — to be configured under `configs/multi_domain_all/medical_health/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [MedMax: Mixed-Modal Instruction Tuning for Training Biomedical Assistants](https://github.com/Hritikbansal/medmax) | 0.3707 | 42 | none | NeurIPS D&B poster |
| [PatientSim: A Persona-Driven Simulator for Realistic Doctor-Patient Interactions](https://github.com/dek924/PatientSim) | 0.3244 | 25 | none | NeurIPS D&B spotlight |
| [TCM-Ladder: A Benchmark for Multimodal Question Answering on Traditional Chinese Medicine](https://github.com/orangeshushu/TCM-Ladder) | 0.3006 | 21 | nlp_text | NeurIPS D&B poster |
| [MedSG-Bench: A Benchmark for Medical Image Sequences Grounding](https://github.com/Yuejingkun/MedSG-Bench) | 0.278 | 17 | multimodal_vision | NeurIPS D&B spotlight |
| [DrVD-Bench: Do Vision-Language Models Reason Like Human Doctors in Medical Image Diagnosis?](https://github.com/Jerry-Boss/DrVD-Bench) | 0.2619 | 14 | multimodal_vision | NeurIPS D&B poster |
| [SMMILE: An expert-driven benchmark for multimodal medical in-context learning](https://github.com/eth-medical-ai-lab/smmile) | 0.2532 | 13 | none | NeurIPS D&B poster |
| [CGBench: Benchmarking Language Model Scientific Reasoning for Clinical Genetics Research](https://github.com/owencqueen/cgbench) | 0.1325 | 4 | none | NeurIPS D&B poster |
| [Simulating Viva Voce Examinations to Evaluate Clinical Reasoning in Large Language Models](https://github.com/chy-chiu/vivabench) | 0.07 | 1 | agent_interactive | NeurIPS D&B poster |
| [LTD-Bench: Evaluating Large Language Models by Letting Them Draw](https://github.com/walktaster/LTD-Bench) | 0.07 | 1 | none | NeurIPS D&B poster |
| [CXReasonBench: A Benchmark for Evaluating Structured Diagnostic Reasoning in Chest X-rays](https://github.com/ttumyche/CXReasonBench) | 0.07 | 1 | none | NeurIPS D&B spotlight |
| [Thousand Voices of Trauma: A Large-Scale Synthetic Dataset for Modeling Prolonged Exposure Therapy Conversations](https://huggingface.co/datasets/yenopoya/thousand-voices-trauma) | 0.0269 | 0 | none | NeurIPS D&B spotlight |
| [ClinBench: A Standardized Multi-Domain Framework for Evaluating Large Language Models in Clinical Information Extraction](https://github.com/ismaelvillanuevamiranda/ClinBench) | 0.0269 | 0 | nlp_text | NeurIPS D&B poster |

### safety_alignment (includes privacy/security) (22)

**Sampled (4 / 22)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [OpenUnlearning: Accelerating LLM Unlearning via Unified Benchmarking of Methods and Metrics](https://github.com/locuslab/open-unlearning) _(config: `multi_domain/safety_alignment/open_unlearning.yaml`)_ | 0.4871 | 522 | none | NeurIPS D&B poster |
| [BackdoorLLM: A Comprehensive Benchmark for Backdoor Attacks and Defenses on Large Language Models](https://github.com/bboylyg/BackdoorLLM) _(config: `multi_domain/safety_alignment/backdoorllm.yaml`)_ | 0.4828 | 291 | none | NeurIPS D&B poster |
| [Artificial Hivemind: The Open-Ended Homogeneity of Language Models (and Beyond)](https://github.com/liweijiang/artificial-hiveminds) _(config: `multi_domain/safety_alignment/artificial_hivemind.yaml`)_ | 0.4116 | 69 | none | NeurIPS D&B oral |
| [OS-Harm: A Benchmark for Measuring Safety of Computer Use Agents](https://github.com/tml-epfl/os-harm) _(config: `multi_domain/safety_alignment/os_harm.yaml`)_ | 0.4084 | 61 | agent_interactive | NeurIPS D&B spotlight |

**Remaining (18 / 22)** — to be configured under `configs/multi_domain_all/safety_alignment/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [GuardSet-X: Massive Multi-Domain Safety Policy-Grounded Guardrail Dataset](https://github.com/AI-secure/PolyGuard) | 0.2909 | 19 | none | NeurIPS D&B poster |
| [SECODEPLT: A Unified Benchmark for Evaluating the Security Risks and Capabilities of Code GenAI](https://github.com/ucsb-mlsec/SeCodePLT) | 0.2619 | 14 | code_swe | NeurIPS D&B poster |
| [BenchmarkCards: Standardized Documentation for Large Language Model Benchmarks](https://github.com/SokolAnn/BenchmarkCards) | 0.2414 | 12 | none | NeurIPS D&B poster |
| [DeceptionBench: A Comprehensive Benchmark for AI Deception Behaviors in Real-world Scenarios](https://github.com/Aries-iai/DeceptionBench) | 0.2091 | 10 | none | NeurIPS D&B poster |
| [Video-SafetyBench: A Benchmark for Safety Evaluation of Video LVLMs](https://github.com/flageval-baai/Video-SafetyBench) | 0.1929 | 9 | none | NeurIPS D&B poster |
| [InterMT: Multi-Turn Interleaved Preference Alignment with Human Feedback](https://github.com/cby-pku/InterMT) | 0.1778 | 8 | none | NeurIPS D&B spotlight |
| [Clean First, Align Later: Benchmarking Preference Data Cleaning for Reliable LLM Alignment](https://github.com/deeplearning-wisc/PrefCleanBench) | 0.1638 | 7 | eval_methodology | NeurIPS D&B poster |
| [SAGE-Eval: Evaluating LLMs for Systematic Generalizations of Safety Facts](https://github.com/YuehHanChen/SAGE-Eval) | 0.1487 | 5 | none | NeurIPS D&B spotlight |
| [UMU-Bench: Closing the Modality Gap in Multimodal Unlearning Evaluation](https://github.com/QDRhhhh/UMU-bench) | 0.1325 | 4 | none | NeurIPS D&B poster |
| [VMDT: Decoding the Trustworthiness of Video Foundation Models](https://github.com/sunblaze-ucb/VMDT) | 0.097 | 2 | none | NeurIPS D&B poster |
| [DataSIR: A Benchmark Dataset for Sensitive Information Recognition](https://github.com/Fan-Mo-ZJU/DataSIR) | 0.097 | 2 | none | NeurIPS D&B poster |
| [CHASM: Unveiling Covert Advertisements on Chinese Social Media](https://github.com/Jingyi62/CHASM) | 0.097 | 2 | none | NeurIPS D&B poster |
| [Risk Management for Mitigating Benchmark Failure Modes: BenchRisk](https://github.com/BenchRisk/BenchRisk) | 0.07 | 1 | eval_methodology | NeurIPS D&B poster |
| [Towards Evaluating Proactive Risk Awareness of Multimodal Language Models](https://huggingface.co/datasets/Youliang/PaSBench) | 0.0269 | 0 | none | NeurIPS D&B poster |
| [Security Challenges in AI Agent Deployment: Insights from a Large Scale Public Competition](https://github.com/GraySwanAI/agent-red-teaming) | 0.0269 | 0 | agent_interactive | NeurIPS D&B poster |
| [SafeVid: Toward Safety Aligned Video Large Multimodal Models](https://github.com/Archippe-m-arkip/safevideo) | 0.0269 | 0 | multimodal_vision | NeurIPS D&B poster |
| [PUO-Bench: A Panel Understanding and Operation Benchmark with A Privacy-Preserving Framework](https://huggingface.co/datasets/Tele-AI-MAIL/Panel-Understanding-and-Operation) | 0.0269 | 0 | agent_interactive | NeurIPS D&B poster |
| [CARES: Comprehensive Evaluation of Safety and Adversarial Robustness in Medical LLMs](https://github.com/XiaominLi1998/Submission-CARES) | 0.0269 | 0 | medical_health | NeurIPS D&B poster |

### reasoning_math (13)

**Sampled (5 / 13)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [MathArena: Evaluating LLMs on Uncontaminated Math Competitions](https://github.com/eth-sri/matharena) _(config: `multi_domain/reasoning_math/matharena.yaml`)_ | 0.4763 | 242 | none | NeurIPS D&B poster |
| [SuperGPQA: Scaling LLM Evaluation across 285 Graduate Disciplines](https://github.com/SuperGPQA/SuperGPQA) _(config: `multi_domain/reasoning_math/supergpqa.yaml`)_ | 0.4677 | 185 | none | NeurIPS D&B poster |
| [Solving Inequality Proofs with Large Language Models](https://github.com/lupantech/ineqmath) _(config: `multi_domain/reasoning_math/ineqmath.yaml`)_ | 0.4041 | 59 | none | NeurIPS D&B spotlight |
| [OMEGA: Can LLMs Reason Outside the Box in Math? Evaluating Exploratory, Compositional, and Transformative Generalization](https://github.com/sunblaze-ucb/omega) _(config: `multi_domain/reasoning_math/omega.yaml`)_ | 0.3793 | 46 | none | NeurIPS D&B poster |
| [RealMath: A Continuous Benchmark for Evaluating Language Models on Research-Level Mathematics](https://github.com/ethz-spylab/RealMath) _(config: `multi_domain/reasoning_math/realmath.yaml`)_ | 0.2963 | 20 | none | NeurIPS D&B poster |

**Remaining (8 / 13)** — to be configured under `configs/multi_domain_all/reasoning_math/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [Reasoning Gym: Reasoning Environments for Reinforcement Learning with Verifiable Rewards](https://github.com/open-thought/reasoning-gym) | 0.4978 | 1392 | none | NeurIPS D&B spotlight |
| [Ineq-Comp: Benchmarking Human-Intuitive Compositional Reasoning in Automated Theorem Proving of Inequalities](https://github.com/haoyuzhao123/LeanIneqComp) | 0.306 | 22 | none | NeurIPS D&B poster |
| [SolidGeo: Measuring Multimodal Spatial Math Reasoning in Solid Geometry](https://github.com/HarryYancy/SolidGeo) | 0.1929 | 9 | none | NeurIPS D&B poster |
| [LexiCon: a Benchmark for Planning under Temporal Constraints in Natural Language](https://github.com/periklismant/lexicon_neurips) | 0.1487 | 5 | none | NeurIPS D&B poster |
| [ConnectomeBench: Can LLMs proofread the connectome?](https://github.com/jffbrwn2/ConnectomeBench) | 0.1164 | 3 | science_expert_reasoning | NeurIPS D&B spotlight |
| [HARDMath2: A Benchmark for Applied Mathematics Built by Students as Part of a Graduate Class](https://github.com/JamesRoggeveen/hardmath2_eval) | 0.097 | 2 | none | NeurIPS D&B poster |
| [NaturalReasoning: Reasoning in the Wild with 2.8M Challenging Questions](https://huggingface.co/datasets/facebook/natural_reasoning) | 0.0269 | 0 | none | NeurIPS D&B poster |
| [Benchmarking Large Language Models with Integer Sequence Generation Tasks](https://github.com/ceodspspectrum/oeis-sequence-benchmark) | 0.0269 | 0 | none | NeurIPS D&B poster |

### retrieval_rag (8)

**Sampled (5 / 8)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [Mind2Web 2: Evaluating Agentic Search with Agent-as-a-Judge](https://github.com/OSU-NLP-Group/Mind2Web-2) _(config: `multi_domain/retrieval_rag/mind2web.yaml`)_ | 0.4397 | 107 | agent_interactive | NeurIPS D&B poster |
| [FreshStack: Building Realistic Benchmarks for Evaluating Retrieval on Technical Documents](https://github.com/fresh-stack/freshstack) _(config: `multi_domain/retrieval_rag/freshstack.yaml`)_ | 0.3534 | 34 | none | NeurIPS D&B poster |
| [Benchmarking Retrieval-Augmented Multimomal Generation for Document Question Answering](https://github.com/MMDocRAG/MMDocRAG) _(config: `multi_domain/retrieval_rag/mmdocrag.yaml`)_ | 0.2845 | 18 | multimodal_vision | NeurIPS D&B poster |
| [C-SEO Bench: Does Conversational SEO Work?](https://github.com/parameterlab/c-seo-bench) _(config: `multi_domain/retrieval_rag/c_seo_bench.yaml`)_ | 0.2726 | 16 | none | NeurIPS D&B poster |
| [Diagnosing and Addressing Pitfalls in KG-RAG Datasets: Toward More Reliable Benchmarking](https://github.com/liangliang6v6/KGQAGen) _(config: `multi_domain/retrieval_rag/kgqagen.yaml`)_ | 0.1778 | 8 | nlp_text | NeurIPS D&B poster |

**Remaining (3 / 8)** — to be configured under `configs/multi_domain_all/retrieval_rag/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [MS-Bench: Evaluating LMMs in Ancient Manuscript Study through a Dunhuang Case Study](https://github.com/ianeong/MS-Bench) | 0.1164 | 3 | none | NeurIPS D&B poster |
| [Worse than Zero-shot? A Fact-Checking Dataset for Evaluating the Robustness of RAG Against Misleading Retrievals](https://huggingface.co/datasets/UCSC-IRKM/RAGuard) | 0.0269 | 0 | none | NeurIPS D&B poster |
| [HawkBench: Investigating Resilience of RAG Methods on Stratified Information-Seeking Tasks](https://github.com/qhjqhj00/HawkBench) | 0.0269 | 0 | none | NeurIPS D&B spotlight |

### multimodal_vision (34)

**Sampled (2 / 34)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [OCRBench v2: An Improved Benchmark for Evaluating Large Multimodal Models on Visual Text Localization and Reasoning](https://github.com/Yuliang-Liu/MultimodalOCR) _(config: `multi_domain/multimodal_vision/ocrbench_v2.yaml`)_ | 0.4914 | 817 | none | NeurIPS D&B poster |
| [From Flatland to Space: Teaching Vision-Language Models to Perceive and Reason in 3D](https://github.com/LogosRoboticsGroup/SPAR) _(config: `multi_domain/multimodal_vision/from_flatland_to_space.yaml`)_ | 0.431 | 84 | none | NeurIPS D&B poster |

**Remaining (32 / 34)** — to be configured under `configs/multi_domain_all/multimodal_vision/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [SURDS: Benchmarking Spatial Understanding and Reasoning in Driving Scenarios with Vision Language Models](https://github.com/XiandaGuo/Drive-MLLM) | 0.4246 | 80 | remote_sensing | NeurIPS D&B poster |
| [The Curse of Multi-Modalities: Evaluating Hallucinations of Large Multimodal Models across Language, Visual, and Audio](https://github.com/DAMO-NLP-SG/CMM) | 0.3944 | 52 | audio_speech | NeurIPS D&B poster |
| [SeePhys:  Does Seeing Help Thinking? – Benchmarking Vision-Based Physics Reasoning](https://github.com/SeePhys/seephys-project) | 0.3869 | 49 | science_expert_reasoning | NeurIPS D&B poster |
| [IR3D-Bench: Evaluating Vision-Language Model Scene Understanding as Agentic Inverse Rendering](https://github.com/LiuHengyu321/IR3D-Bench) | 0.3793 | 46 | agent_interactive | NeurIPS D&B poster |
| [MME-VideoOCR: Evaluating OCR-Based Capabilities of Multimodal LLMs in Video Scenarios](https://github.com/FrankYang-17/MME-VideoOCR) | 0.3653 | 38 | video_understanding | NeurIPS D&B poster |
| [ColorBench: Can VLMs See and Understand the Colorful World? A Comprehensive Benchmark for Color Perception, Reasoning, and Robustness](https://github.com/tianyi-lab/ColorBench) | 0.3653 | 38 | none | NeurIPS D&B poster |
| [Can Large Language Models Help Multimodal Language Analysis? MMLA: A Comprehensive Benchmark](https://github.com/thuiar/MMLA) | 0.3416 | 30 | audio_speech | NeurIPS D&B poster |
| [CAPability: A Comprehensive Visual Caption Benchmark for Evaluating Both Correctness and Thoroughness](https://github.com/ali-vilab/CAPability) | 0.3341 | 27 | none | NeurIPS D&B poster |
| [Robo2VLM: Improving Visual Question Answering using Large-Scale Robot Manipulation Data](https://github.com/KeplerC/robo2VLM) | 0.3244 | 25 | embodied_3d | NeurIPS D&B spotlight |
| [ChartMuseum: Testing Visual Reasoning Capabilities of Large Vision-Language Models](https://github.com/Liyan06/ChartMuseum) | 0.3006 | 21 | none | NeurIPS D&B poster |
| [BMMR: A Large-Scale Bilingual Multimodal Multi-Discipline Reasoning Dataset](https://github.com/WooooDyy/BMMR) | 0.2909 | 19 | none | NeurIPS D&B poster |
| [AgMMU: A Comprehensive Agricultural Multimodal Understanding Benchmark](https://github.com/AgMMU/AgMMU) | 0.2726 | 16 | remote_sensing | NeurIPS D&B poster |
| [MMPerspective: Do MLLMs Understand Perspective? A Comprehensive Benchmark for Perspective Perception, Reasoning, and Robustness](https://github.com/yunlong10/MMPerspective) | 0.2414 | 12 | none | NeurIPS D&B poster |
| [CHOICE: Benchmarking the Remote Sensing Capabilities of Large Vision-Language Models](https://github.com/ShawnAn-WHU/CHOICE) | 0.2414 | 12 | remote_sensing | NeurIPS D&B poster |
| [UVE: Are MLLMs Unified Evaluators for AI-Generated Videos?](https://github.com/bytedance/UVE) | 0.2263 | 11 | none | NeurIPS D&B poster |
| [RBench-V: A Primary Assessment for Visual Reasoning Models with Multimodal Outputs](https://github.com/CHEN-Xinsheng/VLMEvalKit_RBench-V) | 0.2263 | 11 | none | NeurIPS D&B poster |
| [MLLM-ISU: The First-Ever Comprehensive Benchmark for Multimodal Large Language Models based Intrusion Scene Understanding](https://github.com/1012537710/MLLM-ISU) | 0.2263 | 11 | safety_alignment | NeurIPS D&B poster |
| [BLINK-Twice: You see, but do you observe?  A Reasoning Benchmark on Visual Perception](https://github.com/PicoTrex/BLINK-Twice) | 0.2263 | 11 | none | NeurIPS D&B poster |
| [AnomalyCoT: A Multi-Scenario Chain-of-Thought Dataset for Multimodal Large Language Models](https://github.com/Zhaolutuan/AnomalyCoT) | 0.2263 | 11 | none | NeurIPS D&B poster |
| [MMPB: It’s Time for Multi-Modal Personalization](https://github.com/MMPB-Benchmark/MMPB) | 0.1929 | 9 | nlp_text | NeurIPS D&B poster |
| [MMCSBench: A Fine-Grained Benchmark for Large Vision-Language Models in Camouflage Scenes](https://github.com/zhangjinCV/MMCSBench) | 0.1487 | 5 | none | NeurIPS D&B poster |
| [MM-OPERA: Benchmarking Open-ended Association Reasoning for Large Vision-Language Models](https://github.com/MM-OPERA-Bench/MM-OPERA) | 0.1487 | 5 | none | NeurIPS D&B poster |
| [MimeQA: Towards Socially-Intelligent Nonverbal Foundation Models](https://github.com/MIT-MI/MimeQA) | 0.1325 | 4 | nlp_text | NeurIPS D&B poster |
| [InfoChartQA: A Benchmark for Multimodal Question Answering on Infographic Charts](https://github.com/thu-vis/InfoChartQA) | 0.1164 | 3 | none | NeurIPS D&B poster |
| [FineGRAIN: Evaluating Failure Modes of Text-to-Image Models with Vision Language Model Judges](https://github.com/khayes95/FineGRAIN_Eval) | 0.097 | 2 | none | NeurIPS D&B spotlight |
| [Hyperphantasia: A Benchmark for Evaluating the Mental Visualization Capabilities of Multimodal LLMs](https://github.com/AIF4S/Hyperphantasia) | 0.07 | 1 | none | NeurIPS D&B poster |
| [Face-Human-Bench: A Comprehensive Benchmark of Face and Human Understanding for Multi-modal Assistants](https://github.com/lxq1000/Face-Human-Bench) | 0.07 | 1 | none | NeurIPS D&B poster |
| [PAC Bench: Do Foundation Models Understand Prerequisites for Executing Manipulation Policies?](https://github.com/Atharva-Gundawar/pacbench) | 0.0269 | 0 | embodied_3d | NeurIPS D&B poster |
| [MME: A Comprehensive Evaluation Benchmark for Multimodal Large Language Models](https://huggingface.co/datasets/darkyarding/MME) | 0.0269 | 0 | none | NeurIPS D&B spotlight |
| [Fire360: A Benchmark for Robust Perception and Episodic Memory in Degraded 360° Firefighting Video](https://uofi.app.box.com/v/fire360dataset) | 0.0269 | 0 | video_understanding | NeurIPS D&B spotlight |
| [Escaping the SpuriVerse: Can Large Vision-Language Models Generalize Beyond Seen Spurious Correlations?](https://github.com/Anderson-Lee-Git/SpuriVerse) | 0.0269 | 0 | none | NeurIPS D&B poster |
| [CoralVQA: A Large-Scale Visual Question Answering Dataset for Coral Reef Image Understanding](https://huggingface.co/datasets/CoralReefData/CoralVQA/tree/main) | 0.0269 | 0 | science_expert_reasoning | NeurIPS D&B oral |

### science_expert_reasoning (12)

**Sampled (2 / 12)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [PhysGym: Benchmarking LLMs in Interactive Physics Discovery with Controlled Priors](https://github.com/principia-ai/PhysGym) _(config: `multi_domain/science_domain/physgym.yaml`)_ | 0.4364 | 95 | agent_interactive | NeurIPS D&B poster |
| [Beyond Chemical QA: Evaluating LLM's Chemical Reasoning with Modular Chemical Operations](https://github.com/IDEA-XL/ChemCoTBench) _(config: `multi_domain/science_domain/beyond_chemical_qa.yaml`)_ | 0.3869 | 49 | none | NeurIPS D&B poster |

**Remaining (10 / 12)** — to be configured under `configs/multi_domain_all/science_expert_reasoning/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [QCircuitBench: A Large-Scale Dataset for Benchmarking Quantum Algorithm Design](https://github.com/EstelYang/QCircuitBench) | 0.3244 | 25 | none | NeurIPS D&B poster |
| [PHYBench: Holistic Evaluation of Physical Perception and Reasoning in Large Language Models](https://github.com/phybench-official/phybench) | 0.3157 | 24 | embodied_3d | NeurIPS D&B poster |
| [CellVerse: Do Large Language Models Really Understand Cell Biology?](https://github.com/zfkarl/CellVerse) | 0.2683 | 15 | none | NeurIPS D&B poster |
| [Scaling Physical Reasoning with the PHYSICS Dataset](https://github.com/Zhengsh123/PHYSICS) | 0.2619 | 14 | embodied_3d | NeurIPS D&B poster |
| [AstroVisBench: A Code Benchmark for Scientific Computing and Visualization in Astronomy](https://github.com/SebaJoe/AstroVisBench) | 0.2263 | 11 | none | NeurIPS D&B poster |
| [FGBench: A Dataset and Benchmark for Molecular Property Reasoning at Functional Group-Level in Large Language Models](https://github.com/xuanliugit/FGBench) | 0.1929 | 9 | none | NeurIPS D&B poster |
| [AtmosSci-Bench: Evaluating the Recent Advance of Large Language Model for Atmospheric Science](https://github.com/Relaxed-System-Lab/AtmosSci-Bench) | 0.1778 | 8 | none | NeurIPS D&B poster |
| [Scientists' First Exam: Probing Cognitive Abilities of MLLM via Perception, Understanding, and Reasoning](https://github.com/PrismaX-Team/sfe) | 0.1638 | 7 | multimodal_vision | NeurIPS D&B poster |
| [ChemX: A Collection of Chemistry Datasets for Benchmarking Automated Information Extraction](https://github.com/ai-chem/ChemX) | 0.097 | 2 | none | NeurIPS D&B poster |
| [Measuring Scientific Capabilities of Language Models with a Systems Biology Dry Lab](https://github.com/h4duan/scigym-neurips) | 0.07 | 1 | none | NeurIPS D&B poster |

### agent_interactive (20)

**Sampled (3 / 20)** — already in `configs/multi_domain/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [TheAgentCompany: Benchmarking LLM Agents on Consequential Real World Tasks](https://github.com/TheAgentCompany/TheAgentCompany) _(config: `multi_domain/agent_interactive/the_agent_company.yaml`)_ | 0.4892 | 679 | none | NeurIPS D&B poster |
| [ALE-Bench: A Benchmark for Long-Horizon Objective-Driven Algorithm Engineering](https://github.com/SakanaAI/ALE-Bench) _(config: `multi_domain/agent_interactive/ale_bench.yaml`)_ | 0.4655 | 177 | none | NeurIPS D&B poster |
| [WASP: Benchmarking Web Agent Security Against Prompt Injection Attacks](https://github.com/facebookresearch/wasp) _(config: `multi_domain/safety_alignment/wasp.yaml`)_ | 0.4224 | 79 | safety_alignment | NeurIPS D&B poster |

**Remaining (17 / 20)** — to be configured under `configs/multi_domain_all/agent_interactive/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [Factorio Learning Environment](https://github.com/JackHopkins/factorio-learning-environment) | 0.4935 | 954 | none | NeurIPS D&B poster |
| [Scaling Computer-Use Grounding via User Interface Decomposition and Synthesis](https://github.com/xlang-ai/osworld-g) | 0.4547 | 161 | none | NeurIPS D&B spotlight |
| [The Automated LLM Speedrunning Benchmark: Reproducing NanoGPT Improvements](https://github.com/facebookresearch/llm-speedrunner) | 0.4504 | 139 | none | NeurIPS D&B poster |
| [MLE-Dojo: Interactive Environments for Empowering LLM Agents in Machine Learning Engineering](https://github.com/MLE-Dojo/MLE-Dojo) | 0.4332 | 93 | none | NeurIPS D&B poster |
| [Open CaptchaWorld: A Comprehensive Web-based Platform for Testing and Benchmarking Multimodal LLM Agents](https://github.com/MetaAgentX/OpenCaptchaWorld) | 0.4084 | 61 | none | NeurIPS D&B poster |
| [Establishing Best Practices in Building Rigorous Agentic Benchmarks](https://github.com/uiuc-kang-lab/agentic-benchmarks) | 0.3966 | 55 | none | NeurIPS D&B poster |
| [MedAgentBoard: Benchmarking Multi-Agent Collaboration with Conventional Methods for Diverse Medical Tasks](https://github.com/yhzhu99/MedAgentBoard) | 0.3922 | 50 | medical_health | NeurIPS D&B poster |
| [AgentDAM: Privacy Leakage Evaluation for Autonomous Web Agents](https://github.com/facebookresearch/ai-agent-privacy) | 0.3653 | 38 | safety_alignment | NeurIPS D&B poster |
| [Can LLMs Outshine Conventional Recommenders? A Comparative Evaluation](https://github.com/Jyonn/RecBench) | 0.347 | 31 | none | NeurIPS D&B poster |
| [AGENTIF: Benchmarking Large Language Models Instruction Following Ability in Agentic Scenarios](https://github.com/THU-KEG/AgentIF) | 0.3416 | 30 | none | NeurIPS D&B spotlight |
| [MLR-Bench: Evaluating AI Agents on Open-Ended Machine Learning Research](https://github.com/chchenhui/mlrbench) | 0.3319 | 26 | none | NeurIPS D&B poster |
| [MineAnyBuild: Benchmarking Spatial Planning for Open-world AI Agents](https://github.com/MineAnyBuild/MineAnyBuild) | 0.2532 | 13 | embodied_3d | NeurIPS D&B poster |
| [Seeking and Updating with Live Visual Knowledge](https://github.com/fumingyang2004/LIVEVQA) | 0.2263 | 11 | multimodal_vision | NeurIPS D&B poster |
| [MLRC-Bench: Can Language Agents Solve Machine Learning Research Challenges?](https://github.com/yunx-z/MLRC-Bench) | 0.1778 | 8 | science_expert_reasoning | NeurIPS D&B poster |
| [T1: A Tool-Oriented Conversational Dataset for Multi-Turn Agentic Planning](https://github.com/CapitalOne-Research/T1) | 0.1638 | 7 | none | NeurIPS D&B poster |
| [REAL: Benchmarking Autonomous Agents on Deterministic Simulations of Real Websites](https://github.com/agi-inc/REAL) | 0.1487 | 5 | none | NeurIPS D&B poster |
| [AgentRecBench: Benchmarking LLM Agent-based Personalized Recommender Systems](https://github.com/Nghia9211/AgentRecBench) | 0.07 | 1 | none | NeurIPS D&B spotlight |

### code_swe (18)

**Sampled (0 / 18)** — already in `configs/multi_domain/`:

_None yet._

**Remaining (18 / 18)** — to be configured under `configs/multi_domain_all/code_swe/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [Decompile-Bench: Million-Scale Binary-Source Function Pairs for Real-World Binary Decompilation](https://github.com/albertan017/LLM4Decompile) | 0.5 | 6490 | none | NeurIPS D&B poster |
| [Multi-SWE-bench: A Multilingual Benchmark for Issue Resolving](https://github.com/multi-swe-bench/multi-swe-bench) | 0.4849 | 330 | nlp_text | NeurIPS D&B poster |
| [SWE-bench Goes Live!](https://github.com/microsoft/SWE-bench-Live) | 0.4634 | 175 | none | NeurIPS D&B poster |
| [LiveCodeBench Pro: How Do Olympiad Medalists Judge LLMs in Competitive Programming?](https://github.com/GavinZhengOI/LiveCodeBench-Pro) | 0.4601 | 172 | none | NeurIPS D&B poster |
| [AlgoTune: Can Language Models Speed Up General-Purpose Numerical Programs?](https://github.com/oripress/AlgoTune) | 0.4364 | 95 | none | NeurIPS D&B poster |
| [CPRet: A Dataset, Benchmark, and Model for Retrieval in Competitive Programming](https://github.com/coldchair/CPRet) | 0.4278 | 81 | none | NeurIPS D&B poster |
| [GSO: Challenging Software Optimization Tasks for Evaluating SWE-Agents](https://github.com/gso-bench/gso) | 0.4203 | 76 | none | NeurIPS D&B poster |
| [WebGen-Bench: Evaluating LLMs on Generating Interactive and Functional Websites from Scratch](https://github.com/mnluzimu/WebGen-Bench) | 0.375 | 45 | agent_interactive | NeurIPS D&B oral |
| [CLEVER: A Curated Benchmark for Formally Verified Code Generation](https://github.com/trishullab/clever) | 0.3653 | 38 | reasoning_math | NeurIPS D&B poster |
| [SWE-rebench: An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents](https://github.com/SWE-rebench/SWE-bench-fork) | 0.3114 | 23 | none | NeurIPS D&B poster |
| [ICPC-Eval: Probing the Frontiers of LLM Reasoning with Competitive Programming Contests](https://github.com/RUCAIBox/ICPC-Eval) | 0.278 | 17 | none | NeurIPS D&B poster |
| [ResearchCodeBench: Benchmarking LLMs on Implementing Novel Machine Learning Research Code](https://github.com/PatrickHua/ResearchCodeBench) | 0.2532 | 13 | none | NeurIPS D&B spotlight |
| [EffiBench-X: A Multi-Language Benchmark for Measuring Efficiency of LLM-Generated Code](https://github.com/EffiBench/EffiBench-X) | 0.2532 | 13 | none | NeurIPS D&B poster |
| [PARROT: A Benchmark for Evaluating LLMs in Cross-System SQL Translation](https://github.com/weAIDB/PARROT) | 0.2414 | 12 | nlp_text | NeurIPS D&B poster |
| [CoRe: Benchmarking LLMs’ Code Reasoning Capabilities through Static Analysis Tasks](https://github.com/CoReBench/CoRe) | 0.2414 | 12 | none | NeurIPS D&B spotlight |
| [IR-OptSet: An Optimization-Sensitive Dataset for Advancing LLM-Based IR Optimizer](https://github.com/yilingqinghan/IR-OptSet) | 0.1778 | 8 | none | NeurIPS D&B poster |
| [CodeAssistBench (CAB): Dataset & Benchmarking for Multi-turn Chat-Based Code Assistance](https://github.com/amazon-science/CodeAssistBench) | 0.1778 | 8 | agent_interactive | NeurIPS D&B poster |
| [Evaluating Program Semantics Reasoning with Type Inference in System $F$](https://github.com/SecurityLab-UCD/TF-Bench) | 0.1164 | 3 | none | NeurIPS D&B poster |

### professional_economic_work (4)

**Sampled (0 / 4)** — already in `configs/multi_domain/`:

_None yet._

**Remaining (4 / 4)** — to be configured under `configs/multi_domain_all/professional_economic_work/`:

| Benchmark | Score | Stars | Other categories | Venue |
| --- | ---: | ---: | --- | --- |
| [Evaluating Generalization Capabilities of LLM-Based Agents in Mixed-Motive Scenarios Using Concordia](https://github.com/google-deepmind/concordia) | 0.4957 | 1340 | none | NeurIPS D&B poster |
| [Time Travel is Cheating: Going Live with DeepFund for Real-Time Fund Investment Benchmarking](https://github.com/HKUSTDial/DeepFund) | 0.4784 | 262 | none | NeurIPS D&B poster |
| [A Multimodal Benchmark for Framing of Oil & Gas Advertising and Potential Greenwashing Detection](https://github.com/climate-nlp/multimodal-oil-gas-benchmark) | 0.07 | 1 | multimodal_vision | NeurIPS D&B poster |
| [STEER-ME: Assessing the Microeconomic Reasoning of Large Language Models](https://huggingface.co/datasets/narunraman/steer_me) | 0.0269 | 0 | none | NeurIPS D&B poster |

### Sampled configs whose primary domain is not in the priority list

These benchmarks already have configs under `multi_domain/` but their primary `domain_categories[0]` is outside the nine priority domains (e.g. assigned to `nlp_text` or `remote_sensing` in `ranked_benchmarks_popularity.json`). They are kept in their current cross-domain location and not regenerated under `multi_domain_all/`.

| Config | Code URL |
| --- | --- |
| `multi_domain/professional_economic_work/officeqa_pro.yaml` | https://github.com/databricks/officeqa |
| `multi_domain/multimodal_vision/mmlongbench.yaml` | https://github.com/edinburghnlp/mmlongbench |
| `multi_domain/multimodal_vision/disasterm3.yaml` | https://github.com/junjue-wang/disasterm3 |
