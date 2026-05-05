"""Convert bench_audit static task audits into BenchGuard's normalized findings JSON.

Output schema mirrors BenchGuard/eval/normalize.py:219-234, so it can be fed
directly into BenchGuard/eval/match.py without running normalize.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CATEGORY_MAP = {
    "ambiguity": "INST",
    "test_quality": "EVAL",
    "environment": "ENV",
}

SEVERITY_MAP = {
    3: "CRITICAL",
    2: "HIGH",
    1: "MEDIUM",
    0: "LOW",
}

CONFIDENCE_NUMERIC = {"low": 0.3, "medium": 0.7, "high": 0.9}
CONFIDENCE_LEVEL = {"low": "POSSIBLE", "medium": "LIKELY", "high": "CONFIRMED"}

BENCHMARK_DISPLAY = {
    "bixbench": "BIXBench-V50",
    "sab": "ScienceAgentBench",
}


def normalize_task_id(raw_task_id: str, benchmark: str) -> str:
    """Map an audit's task_id onto the convention used by the gold standard."""
    if benchmark == "sab":
        # task_009__FACTORS_correlations -> "9"
        # instance_009 -> "9"
        # sab_009_FACTORS_correlations -> "9"
        # 009__FACTORS_correlations -> "9"
        for prefix in ("task_", "instance_", "sab_"):
            if raw_task_id.startswith(prefix):
                stripped = raw_task_id[len(prefix):]
                num_str = stripped.split("__", 1)[0].split("_", 1)[0]
                return str(int(num_str))
        if raw_task_id[:1].isdigit():
            num_str = raw_task_id.split("__", 1)[0]
            return str(int(num_str))
        raise ValueError(f"Unexpected SAB task_id: {raw_task_id!r}")
    return raw_task_id


def format_evidence(evidence: list) -> str:
    """Render evidence list as a compact multiline block for the judge prompt."""
    if not evidence:
        return ""
    lines = []
    for item in evidence:
        if isinstance(item, dict):
            note = item.get("note", "").strip()
            path = item.get("path", "").strip()
            if note and path:
                lines.append(f"- [{path}] {note}")
            elif note:
                lines.append(f"- {note}")
            elif path:
                lines.append(f"- {path}")
        elif isinstance(item, str) and item.strip():
            lines.append(f"- {item.strip()}")
    return "\n".join(lines)


def convert_finding(audit_finding: dict, task_id: str, idx: int, audit_confidence: str) -> dict:
    raw_cat = audit_finding.get("category", "")
    raw_sev = audit_finding.get("severity", 0)
    claim = audit_finding.get("claim", "")
    why = audit_finding.get("why_it_matters", "")
    evidence_block = format_evidence(audit_finding.get("evidence", []))

    base_description = why or claim
    if evidence_block:
        description = f"{base_description}\n\nEvidence:\n{evidence_block}"
    else:
        description = base_description

    return {
        "finding_id": f"{task_id}__static_audit__{idx}",
        "model": "static_audit",
        "task_id": task_id,
        "title": claim,
        "description": description,
        "category": CATEGORY_MAP.get(raw_cat, raw_cat.upper() or "OTHER"),
        "subcategory": audit_finding.get("subtype", ""),
        "severity": SEVERITY_MAP.get(int(raw_sev), "LOW"),
        "confidence": CONFIDENCE_NUMERIC.get(audit_confidence, 0.5),
        "confidence_level": CONFIDENCE_LEVEL.get(audit_confidence, "POSSIBLE"),
        "protocol": "",
    }


def convert(audits_dir: Path, gold_path: Path, benchmark: str) -> dict:
    with open(gold_path) as f:
        gold = json.load(f)
    revised_ids = set(gold["tasks"].keys())

    audit_files = sorted(p for p in audits_dir.glob("*.json") if p.is_file())
    if not audit_files:
        raise SystemExit(f"No audit JSON files in {audits_dir}")

    tasks: dict[str, dict] = {}
    total_findings = 0

    for audit_file in audit_files:
        with open(audit_file) as f:
            record = json.load(f)
        raw_task_id = record.get("task_id") or audit_file.stem
        task_id = normalize_task_id(raw_task_id, benchmark)
        audit_confidence = (record.get("confidence") or "medium").lower()

        converted = [
            convert_finding(fnd, task_id, idx, audit_confidence)
            for idx, fnd in enumerate(record.get("findings", []))
        ]
        total_findings += len(converted)

        tasks[task_id] = {
            "task_id": task_id,
            "is_revised": task_id in revised_ids,
            "findings": converted,
        }

    missing = revised_ids - set(tasks.keys())
    if missing:
        raise SystemExit(
            f"ERROR: gold has {len(missing)} task(s) with no matching audit: "
            f"{sorted(missing)}"
        )

    return {
        "benchmark": BENCHMARK_DISPLAY[benchmark],
        "source_dir": str(audits_dir),
        "models": ["static_audit"],
        "filters_applied": {"exclude_protocols": [], "min_confidence": 0.0},
        "tasks": tasks,
        "filter_stats": {
            "total_raw": total_findings,
            "filtered_boilerplate": 0,
            "total_kept": total_findings,
            "findings_per_model": {"static_audit": total_findings},
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", required=True, choices=["bixbench", "sab"])
    ap.add_argument("--audits-dir", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    out = convert(args.audits_dir, args.gold, args.benchmark)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(out, f, indent=2)

    print(
        f"Wrote {args.output} | tasks={len(out['tasks'])} "
        f"findings={out['filter_stats']['total_kept']} "
        f"revised={sum(1 for t in out['tasks'].values() if t['is_revised'])}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
