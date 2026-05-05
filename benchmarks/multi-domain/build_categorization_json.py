"""Build benchmark_categorization.json from benchmark_categorization.md.

Output is the single source of truth for paper-facing domain labels consumed
by the visualizer (visualizer/src/lib/domains.ts) via build-data.ts.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "benchmark_categorization.md"
OUT_PATH = ROOT / "benchmark_categorization.json"

# Section 2 uses snake_case keys (matches `domain_categories` in audit JSONs);
# Section 1 uses paper-facing labels. These nine pairs are aligned 1-1.
DOMAIN_KEY_TO_LABEL = {
    "science_expert_reasoning": "Science / expert reasoning",
    "multimodal_vision": "Multimodal / academic / document / visual reasoning",
    "professional_economic_work": "Professional / economic work",
    "agent_interactive": "Interactive / agentic / tool-use",
    "code_swe": "Coding / SWE / terminal",
    "medical_health": "Medical / clinical",
    "reasoning_math": "Math / formal reasoning",
    "retrieval_rag": "Retrieval / RAG / search",
    "safety_alignment": "Safety / alignment",
}
LABEL_TO_KEY = {v: k for k, v in DOMAIN_KEY_TO_LABEL.items()}

# Paper-portfolio externals listed only in Section 1 (no Section 2 entry).
# These map a Section 1 title to the slug(s) that show up as `benchmarkName`
# in the visualizer (the audit dir's `benchmark_name`). Aliases let us match
# variants like `swe_bench` vs `swe_bench_verified`.
PAPER_EXTERNAL_SLUGS: dict[str, list[str]] = {
    "HLE (Humanity's Last Exam)": ["humanitys_last_exam", "hle", "humanitys_last_exam_hle"],
    "GPQA Diamond": ["gpqa_diamond", "gpqa", "gpqa-diamond"],
    "MMMU-Pro": ["mmmu_pro", "mmmu"],
    "GDPval AA": ["gdpval_aa", "gdpval"],
    "Vals Finance Agent": ["finance_agent"],
    "DABstep": ["dabstep"],
    "OSWorld Verified": ["osworld_verified", "osworld"],
    "Toolathlon": ["toolathlon"],
    "Tau2-Bench Telecom": ["tau2_bench_telecom", "tau2_bench"],
    "SWE-Bench Verified": ["swe_bench_verified", "swe_bench"],
    "SWE-Bench Pro": ["swe_bench_pro", "swe-bench-pro"],
    "SWE-Bench Multilingual": ["swe_bench_multilingual"],
    "Frontier SWE": ["frontier_swe"],
    "Terminal-Bench v2": ["tb2", "terminal_bench_v2"],
    "Aider Polyglot": ["aider_polyglot", "aider-polyglot"],
    "AIME 2024 + 2025": ["aime", "aime_fix"],
    "IMOAnswerBench": ["imoanswerbench"],
}

# Section 1 titles whose Section 2 / Section 3 entry's slug isn't recoverable
# by the title-slug fallback (e.g. parenthetical subtitles, abbreviations).
SECTION1_TITLE_TO_SLUG: dict[str, str] = {
    "Beyond Chemical QA (ChemCoTBench)": "beyond_chemical_qa",
    "TheAgentCompany": "the_agent_company",
    "OralGPT (Dental AI)": "oralgpt",
    "IneqMath (Solving Inequality Proofs)": "ineqmath",
    "Mind2Web 2": "mind2web",
    "OpenUnlearning": "open_unlearning",
    "WASP (Web Agent Security)": "wasp",
    "OS-Harm (Computer-Use Agents)": "os_harm",
}

# Section 3 (Sampled configs whose primary domain is not in the priority
# list) — the config path's directory dictates the paper-facing domain.
SECTION3_RE = re.compile(
    r"^\|\s*`multi_domain/([^/]+)/([^.]+)\.yaml`\s*\|\s*(\S+)\s*\|\s*$",
    re.M,
)


def slug_from_url(url: str) -> str:
    u = url.split("#")[0].split("?")[0].rstrip("/")
    if "huggingface.co" in u:
        parts = u.split("/")
        try:
            i = parts.index("datasets")
            name = parts[i + 2]
        except (ValueError, IndexError):
            name = parts[-1]
    elif "github.com" in u:
        name = u.split("/")[-1]
    else:
        name = u.rstrip("/").split("/")[-1]
    return name.lower().replace("-", "_")


def normalize_audit_status(s: str) -> str:
    s = s.strip()
    if s == "Audited":
        return "audited"
    if s == "Audited (external)":
        return "audited_external"
    if s == "Pending":
        return "pending"
    return s.lower()


def parse_int(s: str) -> int | None:
    s = s.strip().replace(",", "")
    if s.isdigit():
        return int(s)
    return None


def parse_float(s: str) -> float | None:
    try:
        return float(s.strip())
    except ValueError:
        return None


def parse_section1(md: str) -> list[dict]:
    """Paper Benchmark Portfolio: tables under ### <paper-facing-domain> headers."""
    section = md.split("### Excluded from the paper portfolio")[0]
    domain_re = re.compile(r"^### (.+)$", re.M)
    matches = list(domain_re.finditer(section))
    out = []
    for i, m in enumerate(matches):
        domain = m.group(1).strip()
        if domain not in LABEL_TO_KEY:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        block = section[start:end]
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            if line.startswith("| ---") or line.startswith("| Benchmark"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 4:
                continue
            title, status, tasks, findings = cells[:4]
            out.append({
                "title": title,
                "audit_status": normalize_audit_status(status),
                "tasks_md": parse_int(tasks),
                "findings_md": parse_int(findings),
                "domain_key": LABEL_TO_KEY[domain],
                "domain_label": domain,
                "in_paper_portfolio": True,
            })
    return out


def parse_section2(md: str) -> list[dict]:
    """Priority Static-Audit Domains: tables under ### <key> (count) headers."""
    body = md.split("## Priority Static-Audit Domains", 1)[1]
    body = body.split(
        "### Sampled configs whose primary domain is not in the priority list"
    )[0]
    header_re = re.compile(
        r"^### (\w+)\s*(?:\(includes [^)]+\))?\s*\((\d+)\)\s*$",
        re.M,
    )
    matches = list(header_re.finditer(body))
    rows: list[dict] = []
    for i, m in enumerate(matches):
        key = m.group(1).strip()
        if key not in DOMAIN_KEY_TO_LABEL:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end]
        bucket = None
        for line in block.splitlines():
            ls = line.strip()
            if ls.startswith("**Sampled"):
                bucket = "sampled"
                continue
            if ls.startswith("**Remaining"):
                bucket = "remaining"
                continue
            if not ls.startswith("|") or ls.startswith("| ---") or ls.startswith("| Benchmark"):
                continue
            cells = [c.strip() for c in ls.strip("|").split("|")]
            if len(cells) < 5:
                continue
            name_cell, score, stars, other_cats, venue = cells[:5]
            mm = re.match(
                r"\[(.+?)\]\((.+?)\)(?:\s*_\(config:\s*`(.+?)`\)_)?",
                name_cell,
            )
            if not mm:
                continue
            title, url, cfg = mm.group(1), mm.group(2), mm.group(3)
            slug = (
                os.path.splitext(os.path.basename(cfg))[0]
                if cfg
                else slug_from_url(url)
            )
            secondary = (
                []
                if other_cats == "none"
                else [s.strip() for s in other_cats.split(",")]
            )
            rows.append({
                "slug": slug,
                "title": title,
                "url": url,
                "domain_key": key,
                "domain_label": DOMAIN_KEY_TO_LABEL[key],
                "secondary_domain_keys": secondary,
                "audit_status_section": bucket,
                "score": parse_float(score),
                "stars": parse_int(stars) if isinstance(stars, str) else stars,
                "venue": venue,
                "config_path": cfg,
            })
    return rows


def parse_section3(md: str) -> list[dict]:
    """Sampled configs whose primary domain falls outside the nine priority
    domains. The config path tells us the paper-facing domain to use."""
    body = md.split("### Sampled configs whose primary domain is not in the priority list", 1)
    if len(body) < 2:
        return []
    tail = body[1]
    rows = []
    for m in SECTION3_RE.finditer(tail):
        domain_dir, slug, url = m.group(1), m.group(2), m.group(3)
        if domain_dir not in DOMAIN_KEY_TO_LABEL:
            continue
        rows.append({
            "slug": slug,
            "url": url,
            "domain_key": domain_dir,
            "domain_label": DOMAIN_KEY_TO_LABEL[domain_dir],
            "config_path": f"multi_domain/{domain_dir}/{slug}.yaml",
            "audit_status_section": "sampled",
            "out_of_priority_primary": True,
        })
    return rows


def title_to_slug_section1(title: str) -> tuple[str, list[str]]:
    """For Section 1 entries, prefer the manual mapping for paper-portfolio
    externals; fall back to a deterministic slug derived from the title."""
    if title in PAPER_EXTERNAL_SLUGS:
        slugs = PAPER_EXTERNAL_SLUGS[title]
        return slugs[0], slugs[1:]
    if title in SECTION1_TITLE_TO_SLUG:
        return SECTION1_TITLE_TO_SLUG[title], []
    fallback = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")
    return fallback, []


def main() -> None:
    md = MD_PATH.read_text()
    s1 = parse_section1(md)
    s2 = parse_section2(md)
    s3 = parse_section3(md)

    # Index Section 1 by title and by derived slug for merging.
    s1_by_title = {row["title"]: row for row in s1}
    s1_by_slug: dict[str, dict] = {}
    for title, row in s1_by_title.items():
        primary, _ = title_to_slug_section1(title)
        s1_by_slug.setdefault(primary, row)

    benchmarks: list[dict] = []
    seen_slugs: set[str] = set()

    # Start from Section 2 (canonical slugs).
    for row in s2:
        s1_match = s1_by_title.get(row["title"]) or s1_by_slug.get(row["slug"])
        merged = {
            "slug": row["slug"],
            "aliases": [],
            "title": row["title"],
            "url": row["url"],
            "domain_key": row["domain_key"],
            "domain_label": row["domain_label"],
            "secondary_domain_keys": row["secondary_domain_keys"],
            "audit_status": (
                s1_match["audit_status"] if s1_match else row["audit_status_section"]
            ),
            "audit_status_section": row["audit_status_section"],
            "in_paper_portfolio": bool(s1_match),
            "score": row["score"],
            "stars": row["stars"],
            "venue": row["venue"],
            "config_path": row["config_path"],
            "tasks_md": s1_match["tasks_md"] if s1_match else None,
            "findings_md": s1_match["findings_md"] if s1_match else None,
        }
        benchmarks.append(merged)
        seen_slugs.add(row["slug"])

    # Add Section 3 entries (paper portfolio configs whose primary is not in
    # the nine priority domains — domain comes from config dir).
    for row in s3:
        s1_match = s1_by_slug.get(row["slug"])
        merged = {
            "slug": row["slug"],
            "aliases": [],
            "title": (s1_match or {}).get("title", row["slug"]),
            "url": row["url"],
            "domain_key": row["domain_key"],
            "domain_label": row["domain_label"],
            "secondary_domain_keys": [],
            "audit_status": (s1_match or {}).get("audit_status", "sampled"),
            "audit_status_section": "sampled",
            "in_paper_portfolio": bool(s1_match),
            "score": None,
            "stars": None,
            "venue": None,
            "config_path": row["config_path"],
            "tasks_md": (s1_match or {}).get("tasks_md"),
            "findings_md": (s1_match or {}).get("findings_md"),
            "out_of_priority_primary": True,
        }
        if row["slug"] in seen_slugs:
            continue
        benchmarks.append(merged)
        seen_slugs.add(row["slug"])

    # Add Section 1 paper-portfolio externals (no matching Section 2 entry).
    for title, row in s1_by_title.items():
        primary, aliases = title_to_slug_section1(title)
        if primary in seen_slugs:
            continue
        # Only add if it's a known paper-portfolio external; otherwise it's
        # presumably a Section 2 entry we couldn't auto-match (rare — log it).
        if title not in PAPER_EXTERNAL_SLUGS:
            print(f"NOTE: Section 1 entry without Section 2 / 3 match: {title!r}")
        benchmarks.append({
            "slug": primary,
            "aliases": aliases,
            "title": title,
            "url": None,
            "domain_key": row["domain_key"],
            "domain_label": row["domain_label"],
            "secondary_domain_keys": [],
            "audit_status": row["audit_status"],
            "audit_status_section": None,
            "in_paper_portfolio": True,
            "score": None,
            "stars": None,
            "venue": None,
            "config_path": None,
            "tasks_md": row["tasks_md"],
            "findings_md": row["findings_md"],
        })
        seen_slugs.add(primary)

    # Stable sort: by domain_key then slug.
    domain_order = list(DOMAIN_KEY_TO_LABEL.keys())
    benchmarks.sort(
        key=lambda b: (domain_order.index(b["domain_key"]), b["slug"])
    )

    out = {
        "version": 1,
        "generated_from": "benchmark_categorization.md",
        "note": (
            "Single source of truth for paper-facing domain labels consumed by "
            "visualizer/src/lib/domains.ts via build-data.ts. Edit the .md and "
            "rerun build_categorization_json.py to regenerate."
        ),
        "domains": [
            {"key": k, "label": v} for k, v in DOMAIN_KEY_TO_LABEL.items()
        ],
        "benchmarks": benchmarks,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {len(benchmarks)} benchmarks to {OUT_PATH}")


if __name__ == "__main__":
    main()
