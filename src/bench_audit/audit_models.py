from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


BENCHMARK_AUDIT_CATEGORIES = {
    "documentation",
    "contamination",
    "eval_methodology",
    "dataset_quality",
    "reproducibility",
    "eval_infrastructure",
}
BENCHMARK_AUDIT_CATEGORY_ALIASES: dict[str, str] = {
    "docs": "documentation",
    "data_quality": "dataset_quality",
    "methodology": "eval_methodology",
    "data_contamination": "contamination",
    "repro": "reproducibility",
    "infrastructure": "eval_infrastructure",
}
BENCHMARK_AUDIT_JUDGMENTS = {"audit_complete", "insufficient_evidence", "agent_error"}
VERDICT_SEVERITIES = {0, 1, 2}

TASK_AUDIT_CATEGORIES = {"ambiguity", "environment", "test_quality"}
TASK_AUDIT_CATEGORY_ALIASES = {
    "ambiguity_underspecification": "ambiguity",
    "environment_conflict": "environment",
    "tests": "test_quality",
}
TASK_AUDIT_SUBTYPE_PREFIX = {
    "ambiguity": "A",
    "environment": "E",
    "test_quality": "T",
}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
TASK_AUDIT_JUDGMENTS = {"audit_complete", "insufficient_evidence", "agent_error"}

@dataclass(slots=True)
class EvidenceRef:
    path: str
    note: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        record = cls(
            path=str(data.get("path") or ""),
            note=str(data.get("note") or ""),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not self.path:
            raise ValueError("evidence.path must be a non-empty string")
        if not self.note:
            raise ValueError("evidence.note must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(slots=True)
class TaskAuditFinding:
    finding_id: str
    category: str
    subtype: str
    severity: int
    claim: str
    why_it_matters: str
    evidence: list[EvidenceRef] = field(default_factory=list)
    suggested_fix: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskAuditFinding":
        category = str(data.get("category") or "")
        category = TASK_AUDIT_CATEGORY_ALIASES.get(category, category)
        finding = cls(
            finding_id=str(data.get("finding_id") or ""),
            category=category,
            subtype=str(data.get("subtype") or ""),
            severity=int(data.get("severity", -1)),
            claim=str(data.get("claim") or ""),
            why_it_matters=str(data.get("why_it_matters") or ""),
            evidence=[EvidenceRef.from_dict(item) for item in data.get("evidence", [])],
            suggested_fix=str(data.get("suggested_fix") or ""),
        )
        finding.validate()
        return finding

    def validate(self) -> None:
        if not self.finding_id:
            raise ValueError("finding_id must be a non-empty string")
        if self.category not in TASK_AUDIT_CATEGORIES:
            raise ValueError(f"unsupported finding category: {self.category}")
        if not self.subtype:
            raise ValueError("subtype must be a non-empty string")
        if self.severity < 0 or self.severity > 3:
            raise ValueError("finding severity must be between 0 and 3")
        if not self.claim:
            raise ValueError("claim must be a non-empty string")
        if not self.why_it_matters:
            raise ValueError("why_it_matters must be a non-empty string")
        if not self.suggested_fix:
            raise ValueError("suggested_fix must be a non-empty string")
        for evidence_ref in self.evidence:
            evidence_ref.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass(slots=True)
class TaskAuditRecord:
    task_id: str
    benchmark_name: str
    task_status: str
    selected_eval_ids: list[str]
    rubric_path: str | None
    audit_trajectory_path: str | None
    overall_judgment: str
    summary: str
    confidence: str
    findings: list[TaskAuditFinding] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskAuditRecord":
        record = cls(
            task_id=str(data.get("task_id") or ""),
            benchmark_name=str(data.get("benchmark_name") or ""),
            task_status=str(data.get("task_status") or ""),
            selected_eval_ids=[str(item) for item in data.get("selected_eval_ids", [])],
            rubric_path=_optional_str(data.get("rubric_path")),
            audit_trajectory_path=_optional_str(data.get("audit_trajectory_path")),
            overall_judgment=str(data.get("overall_judgment") or ""),
            summary=str(data.get("summary") or ""),
            confidence=str(data.get("confidence") or ""),
            findings=[TaskAuditFinding.from_dict(item) for item in data.get("findings", [])],
        )
        record.validate()
        return record

    @classmethod
    def load_json(cls, path: str | Path) -> "TaskAuditRecord":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def validate(self) -> None:
        if not self.task_id:
            raise ValueError("task_id must be a non-empty string")
        if not self.benchmark_name:
            raise ValueError("benchmark_name must be a non-empty string")
        if self.task_status not in {"passed", "failed", "unscored"}:
            raise ValueError("task_status must be 'passed', 'failed', or 'unscored'")
        if not self.selected_eval_ids and self.task_status != "unscored":
            raise ValueError("selected_eval_ids must contain at least one eval id")
        if self.rubric_path is not None and not self.rubric_path:
            raise ValueError("rubric_path must be a non-empty string when provided")
        if self.audit_trajectory_path is not None and not self.audit_trajectory_path:
            raise ValueError("audit_trajectory_path must be a non-empty string when provided")
        if self.overall_judgment not in TASK_AUDIT_JUDGMENTS:
            raise ValueError(f"unsupported overall_judgment: {self.overall_judgment}")
        if not self.summary:
            raise ValueError("summary must be a non-empty string")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unsupported confidence value: {self.confidence}")
        for finding in self.findings:
            finding.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "task_id": self.task_id,
            "benchmark_name": self.benchmark_name,
            "task_status": self.task_status,
            "selected_eval_ids": list(self.selected_eval_ids),
            "rubric_path": self.rubric_path,
            "audit_trajectory_path": self.audit_trajectory_path,
            "overall_judgment": self.overall_judgment,
            "summary": self.summary,
            "confidence": self.confidence,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def save_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


@dataclass(slots=True)
class BenchmarkAuditFinding:
    category: str
    subtype: str
    severity: int
    claim: str
    why_it_matters: str
    evidence: list[EvidenceRef] = field(default_factory=list)
    suggested_fix: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkAuditFinding":
        category = str(data.get("category") or "")
        category = BENCHMARK_AUDIT_CATEGORY_ALIASES.get(category, category)
        finding = cls(
            category=category,
            subtype=str(data.get("subtype") or ""),
            severity=int(data.get("severity", -1)),
            claim=str(data.get("claim") or ""),
            why_it_matters=str(data.get("why_it_matters") or ""),
            evidence=[EvidenceRef.from_dict(item) for item in data.get("evidence", [])],
            suggested_fix=str(data.get("suggested_fix") or ""),
        )
        finding.validate()
        return finding

    def validate(self) -> None:
        if self.category not in BENCHMARK_AUDIT_CATEGORIES:
            raise ValueError(f"unsupported benchmark finding category: {self.category}")
        if not self.subtype:
            raise ValueError("subtype must be a non-empty string")
        if self.severity < 0 or self.severity > 2:
            raise ValueError("finding severity must be between 0 and 2")
        if not self.claim:
            raise ValueError("claim must be a non-empty string")
        if not self.why_it_matters:
            raise ValueError("why_it_matters must be a non-empty string")
        if not self.suggested_fix:
            raise ValueError("suggested_fix must be a non-empty string")
        for evidence_ref in self.evidence:
            evidence_ref.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass(slots=True)
class CategoryVerdict:
    """Per-category verdict forcing the agent to explicitly assess every category."""
    category: str
    severity: int
    rationale: str
    findings: list[BenchmarkAuditFinding] = field(default_factory=list)

    @classmethod
    def from_dict(cls, category: str, data: dict[str, Any]) -> "CategoryVerdict":
        category = BENCHMARK_AUDIT_CATEGORY_ALIASES.get(category, category)
        findings_data = data.get("findings", [])
        # Inject category into each finding so the agent doesn't need to repeat it
        for fd in findings_data:
            fd.setdefault("category", category)
        verdict = cls(
            category=category,
            severity=int(data.get("severity", -1)),
            rationale=str(data.get("rationale") or ""),
            findings=[BenchmarkAuditFinding.from_dict(fd) for fd in findings_data],
        )
        verdict.validate()
        return verdict

    def validate(self) -> None:
        if self.category not in BENCHMARK_AUDIT_CATEGORIES:
            raise ValueError(f"unsupported category: {self.category}")
        if self.severity not in VERDICT_SEVERITIES:
            raise ValueError(f"verdict severity must be 0-2, got {self.severity}")
        if not self.rationale:
            raise ValueError(f"rationale required for category '{self.category}'")
        for finding in self.findings:
            if finding.category != self.category:
                raise ValueError(
                    f"finding [{finding.subtype}] has category '{finding.category}' "
                    f"but is nested under verdict for '{self.category}'"
                )
            finding.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "severity": self.severity,
            "rationale": self.rationale,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass(slots=True)
class BenchmarkAuditRecord:
    benchmark_name: str
    benchmark_type: str
    domain_categories: list[str]
    rubric_path: str | None
    overall_judgment: str
    summary: str
    confidence: str
    category_verdicts: dict[str, CategoryVerdict] = field(default_factory=dict)

    @property
    def findings(self) -> list[BenchmarkAuditFinding]:
        """Flat list of all findings across categories, for backwards compat."""
        return [f for v in self.category_verdicts.values() for f in v.findings]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkAuditRecord":
        verdicts_raw = data.get("category_verdicts", {})
        verdicts: dict[str, CategoryVerdict] = {}
        for key, val in verdicts_raw.items():
            canon = BENCHMARK_AUDIT_CATEGORY_ALIASES.get(key, key)
            verdicts[canon] = CategoryVerdict.from_dict(canon, val)
        record = cls(
            benchmark_name=str(data.get("benchmark_name") or ""),
            benchmark_type=str(data.get("benchmark_type") or ""),
            domain_categories=[str(c) for c in data.get("domain_categories", [])],
            rubric_path=_optional_str(data.get("rubric_path")),
            overall_judgment=str(data.get("overall_judgment") or ""),
            summary=str(data.get("summary") or ""),
            confidence=str(data.get("confidence") or ""),
            category_verdicts=verdicts,
        )
        record.validate()
        return record

    @classmethod
    def load_json(cls, path: str | Path) -> "BenchmarkAuditRecord":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def validate(self) -> None:
        if not self.benchmark_name:
            raise ValueError("benchmark_name must be a non-empty string")
        if not self.benchmark_type:
            raise ValueError("benchmark_type must be a non-empty string")
        if self.rubric_path is not None and not self.rubric_path:
            raise ValueError("rubric_path must be a non-empty string when provided")
        if self.overall_judgment not in BENCHMARK_AUDIT_JUDGMENTS:
            raise ValueError(f"unsupported overall_judgment: {self.overall_judgment}")
        if not self.summary:
            raise ValueError("summary must be a non-empty string")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unsupported confidence value: {self.confidence}")
        missing = BENCHMARK_AUDIT_CATEGORIES - set(self.category_verdicts.keys())
        if missing:
            raise ValueError(f"missing category verdicts: {sorted(missing)}")
        for verdict in self.category_verdicts.values():
            verdict.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "benchmark_name": self.benchmark_name,
            "benchmark_type": self.benchmark_type,
            "domain_categories": list(self.domain_categories),
            "rubric_path": self.rubric_path,
            "overall_judgment": self.overall_judgment,
            "summary": self.summary,
            "confidence": self.confidence,
            "category_verdicts": {k: v.to_dict() for k, v in self.category_verdicts.items()},
        }

    def save_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


def _finding_json_schema() -> dict[str, Any]:
    """JSON schema for a single BenchmarkAuditFinding."""
    return {
        "type": "object",
        "required": [
            "subtype",
            "severity",
            "claim",
            "why_it_matters",
            "evidence",
            "suggested_fix",
        ],
        "additionalProperties": False,
        "properties": {
            "subtype": {"type": "string"},
            "severity": {"type": "integer", "minimum": 0, "maximum": 2},
            "claim": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["path", "note"],
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string"},
                        "note": {"type": "string"},
                    },
                },
            },
            "suggested_fix": {"type": "string"},
        },
    }


def _verdict_json_schema() -> dict[str, Any]:
    """JSON schema for a single CategoryVerdict."""
    return {
        "type": "object",
        "required": ["severity", "rationale", "findings"],
        "additionalProperties": False,
        "properties": {
            "severity": {"type": "integer", "minimum": 0, "maximum": 2},
            "rationale": {"type": "string"},
            "findings": {"type": "array", "items": _finding_json_schema()},
        },
    }


def benchmark_audit_record_json_schema() -> dict[str, Any]:
    verdict_schema = _verdict_json_schema()
    return {
        "type": "object",
        "required": [
            "overall_judgment",
            "summary",
            "confidence",
            "category_verdicts",
        ],
        "additionalProperties": False,
        "properties": {
            "overall_judgment": {
                "type": "string",
                "enum": sorted(BENCHMARK_AUDIT_JUDGMENTS),
            },
            "rubric_path": {"type": "string"},
            "summary": {"type": "string"},
            "confidence": {"type": "string", "enum": sorted(CONFIDENCE_LEVELS)},
            "category_verdicts": {
                "type": "object",
                "required": sorted(BENCHMARK_AUDIT_CATEGORIES),
                "additionalProperties": False,
                "properties": {
                    cat: verdict_schema for cat in sorted(BENCHMARK_AUDIT_CATEGORIES)
                },
            },
        },
    }


def parse_agent_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1)
        stripped = re.sub(r"\s*```$", "", stripped, count=1)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("agent output must decode to a JSON object")
    return data


def task_audit_record_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "task_id",
            "benchmark_name",
            "task_status",
            "selected_eval_ids",
            "overall_judgment",
            "summary",
            "confidence",
            "findings",
        ],
        "additionalProperties": False,
        "properties": {
            "task_id": {"type": "string"},
            "benchmark_name": {"type": "string"},
            "task_status": {"type": "string", "enum": ["failed", "passed", "unscored"]},
            "selected_eval_ids": {"type": "array", "items": {"type": "string"}},
            "rubric_path": {"type": "string"},
            "overall_judgment": {
                "type": "string",
                "enum": sorted(TASK_AUDIT_JUDGMENTS),
            },
            "summary": {"type": "string"},
            "confidence": {"type": "string", "enum": sorted(CONFIDENCE_LEVELS)},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "finding_id",
                        "category",
                        "subtype",
                        "severity",
                        "claim",
                        "why_it_matters",
                        "evidence",
                        "suggested_fix",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "finding_id": {"type": "string"},
                        "category": {"type": "string", "enum": sorted(TASK_AUDIT_CATEGORIES)},
                        "subtype": {"type": "string"},
                        "severity": {"type": "integer", "minimum": 0, "maximum": 3},
                        "claim": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                        "evidence": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["path", "note"],
                                "additionalProperties": False,
                                "properties": {
                                    "path": {"type": "string"},
                                    "note": {"type": "string"},
                                },
                            },
                        },
                        "suggested_fix": {"type": "string"},
                    },
                },
            },
        },
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
