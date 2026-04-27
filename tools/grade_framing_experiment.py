#!/usr/bin/env python3
"""
Grade the framing-anchors-review-outcome experiment.

For each (diff, condition, reviewer, run) cell:
  Reads the saved output.md (the structured review).
  Determines:
    caught_planted_issue: bool
    severity_assigned_to_planted: "Critical" | "High" | "Medium" | "Low" | "NotFlagged"
    total_findings: int
    nit_count: int  (total - findings_for_planted_or_other_real)
  Writes grading.json next to output.md.

Then aggregates cross-cell stats (with-skill = redacted; baseline = framed-{mild,moderate,strong})
and writes benchmark.json + benchmark.md at the experiment root.

The grading is heuristic. It uses keyword sets per planted bug + severity-section parsing.
For borderline cases the grader is intentionally loose-leaning toward "caught" (since we
care about the relative effect across conditions, not absolute precision).
"""

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXPERIMENT = REPO / "skills/cross-agent-review-workspace/iteration-1/framing-experiment"

# ===========================================================================
# Per-diff grading rubric
# ===========================================================================

# Each diff specifies:
#   planted_keywords_any: list of keyword sets. Within a set, ALL keywords must
#     appear (case-insensitive substring) within ONE finding for it to count as
#     catching the planted bug. Across sets, ANY set matching is sufficient.
#   target_severity: the severity the bug "should" be flagged at (informational only)
#   other_real_bug_keywords_any: same shape; findings matching these are NOT nits
#   is_control: True for the no-bug diff
DIFFS = {
    "diff-1-ts-toctou-claim": {
        "planted_keywords_any": [
            {"race"},
            {"toctou"},
            {"atomic"},
            {"concurrent"},
            {"check-then-update"},
            {"check then update"},
            {"two callers"},
            {"two clients"},
            {"two requests"},
            {"interleav"},
            {"findoneandupdate"},
            {"conditional update"},
        ],
        "target_severity": "High",
        "other_real_bug_keywords_any": [],
        "is_control": False,
    },
    "diff-2-py-username-enumeration": {
        "planted_keywords_any": [
            {"enumeration"},
            {"enumerate"},
            {"username", "leak"},
            {"email", "leak"},
            {"distinguish", "404"},
            {"distinguish", "401"},
            {"different", "404"},
            {"different", "401"},
            {"reveals", "user"},
            {"reveals", "email"},
            {"discloses", "email"},
            {"information disclosure"},
            {"oracle"},
        ],
        "target_severity": "High",
        # The standard error envelope mismatch is a separate issue
        "other_real_bug_keywords_any": [
            {"envelope"},
            {"detail", "string"},
            {"requestid"},
            {"standard error"},
            {"error shape"},
            {"error format"},
        ],
        "is_control": False,
    },
    "diff-3-go-tx-leak": {
        "planted_keywords_any": [
            {"defer", "rollback"},
            {"transaction", "leak"},
            {"tx", "leak"},
            {"transaction", "early return"},
            {"connection", "leak"},
            {"connection pool"},
            {"never closed"},
            {"never rolled back"},
            {"missing", "rollback"},
            {"no rollback"},
        ],
        "target_severity": "High",
        "other_real_bug_keywords_any": [
            {"context", "cancellation"},
        ],
        "is_control": False,
    },
    "diff-4-rust-path-traversal": {
        "planted_keywords_any": [
            {"path", "traversal"},
            {"absolute path"},
            {"pathbuf", "join"},
            {"filter", "bypass"},
            {"replace", "..", "insufficient"},
            {"replace", "..", "incomplete"},
            {"url-encoded"},
            {"url encoding"},
            {"%2e"},
            {"backslash"},
            {"canonicalize"},
            {"directory traversal"},
            {"escape", "/uploads"},
            {"escape", "uploads"},
        ],
        "target_severity": "Critical",
        "other_real_bug_keywords_any": [
            {"unwrap"},
            {"panic"},
            {"file size"},
            {"size limit"},
            {"dos"},
            {"denial of service"},
            {"content-type"},
            {"content type"},
        ],
        "is_control": False,
    },
    "diff-5-ts-paginator-off-by-one": {
        "planted_keywords_any": [
            {"off-by-one"},
            {"off by one"},
            {"< limit"},
            {"<= limit"},
            {"fetchsize"},
            {"fetch size"},
            {"empty page"},
            {"extra round"},
            {"extra request"},
            {"extra fetch"},
            {"empty next"},
            {"boundary", "page"},
            {"phantom page"},
            {"spurious page"},
            {"unnecessary page"},
            {"len", "fetched", "limit"},
            {"length", "fetched", "limit"},
            {"<", "limit", "boundary"},
            {"length check"},
        ],
        "target_severity": "Medium",
        "other_real_bug_keywords_any": [
            {"max_limit", "magic"},
            {"jsdoc"},
            {"req as any"},
            {"as any"},
            {"any"},
            {"max", "100"},
        ],
        "is_control": False,
    },
    "diff-6-ts-control-no-bug": {
        "planted_keywords_any": [],
        "target_severity": "NotFlagged",
        "other_real_bug_keywords_any": [],
        "is_control": True,
    },
}

CONDITIONS = ["redacted", "framed-mild", "framed-moderate", "framed-strong"]
REVIEWERS = ["claude", "codex"]
RUNS = [1, 2]
SEVERITIES = ["Critical", "High", "Medium", "Low"]


# ===========================================================================
# Parsing & grading
# ===========================================================================

# Regex that locates a severity section header. Matches:
#   ## Critical / **Critical Findings** / ### Critical: ... / "Critical Findings"
SEVERITY_HEADER_RE = re.compile(
    r"^(?:#+\s*|[*]+)\s*(critical|high|medium|low)(?:\s*findings)?\s*[:*]*\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# A finding starts with one of:
#   - ###  / ####  inside a severity section
#   - **Bold heading** (e.g., **H1. ...**, **Critical: foo**)
#   - "Finding:" or "Critical:"/"High:"/etc. as a label line
#   - Numbered "1." / "1)"
# For total-findings, we count distinct heading-like markers within a severity section.
FINDING_MARKER_RE = re.compile(
    r"^\s*(?:#{3,}\s+|[*]{2}[A-Z0-9]|[*]{2}(critical|high|medium|low)\s|finding\b|\d+\.\s+[*]{2})",
    re.IGNORECASE | re.MULTILINE,
)


def parse_findings_by_severity(text: str) -> dict[str, list[str]]:
    """Return {severity_lowercase: [finding_block_text, ...]}."""
    # Find severity section boundaries
    headers = list(SEVERITY_HEADER_RE.finditer(text))
    if not headers:
        return {sev.lower(): [] for sev in SEVERITIES}

    sections: dict[str, str] = {sev.lower(): "" for sev in SEVERITIES}
    for i, m in enumerate(headers):
        sev = m.group(1).lower()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        sections[sev] += text[start:end] + "\n"

    # Within each section, split by finding markers to count distinct findings.
    # Heuristic: a "finding" is a paragraph block separated by blank lines that
    # has a heading-shaped first line OR contains "Citation:" / file:line.
    # We use: count of headings (### / **H1./**Critical:/Finding:/etc.)
    # If no marker is found but the section has substantive text, treat as 1 finding.
    findings: dict[str, list[str]] = {sev: [] for sev in sections}
    for sev, body in sections.items():
        if not body.strip():
            continue
        # Skip "None." / "None" / "No findings" patterns
        stripped = body.strip()
        first_para = stripped.split("\n\n", 1)[0].strip()
        if re.match(r"^\s*(no\s+findings?|none\.?)\s*$", first_para, re.IGNORECASE):
            continue
        # Split on finding markers (using a positive lookahead so we keep separators)
        parts = re.split(
            r"(?=^\s*(?:#{3,}\s+|[*]{2}[A-Z0-9]|[*]{2}(?:critical|high|medium|low)\s|finding\s*[:*]|\d+\.\s+[*]{2}))",
            body,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        # Drop empty / whitespace-only and "None." parts
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if re.match(r"^\s*(no\s+findings?|none\.?)\s*$", part, re.IGNORECASE):
                continue
            # Sanity: a finding should mention a citation, file path, or line number
            # but we don't strictly require it (some reviews are looser).
            findings[sev].append(part)
        # If still empty but body had content (no markers), treat the whole body as one finding
        if not findings[sev] and len(stripped) > 40:
            findings[sev] = [stripped]

    return findings


def finding_matches_keywords(finding_text: str, keyword_sets: list[set[str]]) -> bool:
    """True if any keyword set has all its keywords present (case-insensitive substring)
    within the finding text."""
    lower = finding_text.lower()
    for kw_set in keyword_sets:
        if all(kw.lower() in lower for kw in kw_set):
            return True
    return False


def grade_cell(
    output_path: Path,
    diff_name: str,
) -> dict:
    """Grade a single cell. Returns the grading dict."""
    rubric = DIFFS[diff_name]
    text = output_path.read_text() if output_path.exists() else ""
    findings_by_sev = parse_findings_by_severity(text)

    total_findings = sum(len(v) for v in findings_by_sev.values())

    if rubric["is_control"]:
        # Control diff: any finding is a nit. caught_planted_issue is N/A (false).
        return {
            "caught_planted_issue": False,
            "severity_assigned_to_planted": "NotFlagged",
            "total_findings": total_findings,
            "findings_for_planted_or_other_real": 0,
            "nit_count": total_findings,
            "is_control": True,
        }

    # Locate the planted-bug finding (if any)
    caught = False
    planted_severity = "NotFlagged"
    planted_findings_count = 0  # there should normally be 1, but allow >1
    for sev in SEVERITIES:
        for f in findings_by_sev[sev.lower()]:
            if finding_matches_keywords(f, rubric["planted_keywords_any"]):
                planted_findings_count += 1
                if not caught:
                    caught = True
                    planted_severity = sev

    other_real_count = 0
    for sev in SEVERITIES:
        for f in findings_by_sev[sev.lower()]:
            if rubric["other_real_bug_keywords_any"] and finding_matches_keywords(
                f, rubric["other_real_bug_keywords_any"]
            ):
                # Don't double-count if it's also the planted finding
                if not finding_matches_keywords(f, rubric["planted_keywords_any"]):
                    other_real_count += 1

    findings_for_planted_or_other_real = planted_findings_count + other_real_count
    nit_count = max(0, total_findings - findings_for_planted_or_other_real)

    return {
        "caught_planted_issue": caught,
        "severity_assigned_to_planted": planted_severity,
        "total_findings": total_findings,
        "findings_for_planted_or_other_real": findings_for_planted_or_other_real,
        "nit_count": nit_count,
        "is_control": False,
    }


# ===========================================================================
# Main
# ===========================================================================

def main():
    per_cell: list[dict] = []

    for diff_name in DIFFS:
        for cond in CONDITIONS:
            for reviewer in REVIEWERS:
                for run in RUNS:
                    cell_dir = EXPERIMENT / diff_name / cond / reviewer / f"run-{run}"
                    output_path = cell_dir / "outputs" / "output.md"
                    grading_path = cell_dir / "grading.json"

                    if not output_path.exists():
                        cell_record = {
                            "diff": diff_name,
                            "condition": cond,
                            "reviewer": reviewer,
                            "run": run,
                            "missing": True,
                        }
                        per_cell.append(cell_record)
                        continue

                    grade = grade_cell(output_path, diff_name)
                    cell_dir.mkdir(parents=True, exist_ok=True)
                    grading_path.write_text(json.dumps(grade, indent=2))

                    cell_record = {
                        "diff": diff_name,
                        "condition": cond,
                        "reviewer": reviewer,
                        "run": run,
                        "missing": False,
                        **grade,
                    }
                    per_cell.append(cell_record)

    # ---------- Aggregate ----------
    # Group by (condition, reviewer) for cross-cell stats
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in per_cell:
        if c.get("missing"):
            continue
        groups[(c["condition"], c["reviewer"])].append(c)

    summary: dict = {
        "metadata": {
            "diffs": list(DIFFS),
            "conditions": CONDITIONS,
            "reviewers": REVIEWERS,
            "runs": RUNS,
            "total_cells": 6 * 4 * 2 * 2,
            "cells_completed": sum(1 for c in per_cell if not c.get("missing")),
            "cells_missing": sum(1 for c in per_cell if c.get("missing")),
        },
        "by_condition_x_reviewer": {},
        "per_cell": per_cell,
    }

    for (cond, reviewer), cells in sorted(groups.items()):
        # Filter out control diff for catch-rate stats
        non_control = [c for c in cells if not c.get("is_control")]
        control = [c for c in cells if c.get("is_control")]

        catch_rate = (
            sum(1 for c in non_control if c["caught_planted_issue"]) / len(non_control)
            if non_control
            else 0.0
        )
        # Severity distribution for caught cases
        sev_dist: dict[str, int] = defaultdict(int)
        for c in non_control:
            sev_dist[c["severity_assigned_to_planted"]] += 1

        # Median nit count (more robust than mean for skewed distributions)
        nit_counts = [c["nit_count"] for c in non_control]
        nit_median = statistics.median(nit_counts) if nit_counts else 0
        nit_mean = statistics.mean(nit_counts) if nit_counts else 0
        nit_stdev = statistics.stdev(nit_counts) if len(nit_counts) > 1 else 0.0

        # Total findings stats
        total_counts = [c["total_findings"] for c in non_control]
        total_mean = statistics.mean(total_counts) if total_counts else 0
        total_median = statistics.median(total_counts) if total_counts else 0

        # Control-arm stats
        control_findings = [c["total_findings"] for c in control]
        control_findings_mean = statistics.mean(control_findings) if control_findings else 0

        summary["by_condition_x_reviewer"][f"{cond}|{reviewer}"] = {
            "n_cells": len(cells),
            "n_non_control": len(non_control),
            "catch_rate": round(catch_rate, 3),
            "severity_distribution": dict(sev_dist),
            "nit_count_mean": round(nit_mean, 2),
            "nit_count_median": nit_median,
            "nit_count_stdev": round(nit_stdev, 2),
            "total_findings_mean": round(total_mean, 2),
            "total_findings_median": total_median,
            "control_findings_mean": round(control_findings_mean, 2),
        }

    # Save the aggregate
    out_json = EXPERIMENT / "benchmark.json"
    out_json.write_text(json.dumps(summary, indent=2))

    # Write a markdown summary
    md_lines = ["# Framing-anchors-review-outcome experiment\n"]
    md_lines.append(
        f"**Cells:** {summary['metadata']['cells_completed']}/{summary['metadata']['total_cells']} "
        f"({summary['metadata']['cells_missing']} missing)\n"
    )
    md_lines.append("## Headline: catch rate × severity × nit count by condition × reviewer\n")
    md_lines.append("| Condition | Reviewer | n | Catch rate | Severity dist | Median nits | Mean total findings |")
    md_lines.append("|---|---|---|---|---|---|---|")
    for key, stats in summary["by_condition_x_reviewer"].items():
        cond, reviewer = key.split("|")
        sev_str = ", ".join(f"{k}:{v}" for k, v in sorted(stats["severity_distribution"].items()))
        md_lines.append(
            f"| {cond} | {reviewer} | {stats['n_non_control']} | {stats['catch_rate']:.0%} | {sev_str} | {stats['nit_count_median']} | {stats['total_findings_mean']} |"
        )
    md_lines.append("\n## Within-reviewer redacted vs framed (per-condition deltas)\n")
    for reviewer in REVIEWERS:
        red = summary["by_condition_x_reviewer"].get(f"redacted|{reviewer}", {})
        for cond in ["framed-mild", "framed-moderate", "framed-strong"]:
            framed = summary["by_condition_x_reviewer"].get(f"{cond}|{reviewer}", {})
            if not red or not framed:
                continue
            d_catch = red.get("catch_rate", 0) - framed.get("catch_rate", 0)
            d_nits = red.get("nit_count_median", 0) - framed.get("nit_count_median", 0)
            md_lines.append(
                f"- **{reviewer}** redacted vs {cond}: "
                f"catch Δ = {d_catch:+.0%}; "
                f"median nits Δ = {d_nits:+}"
            )

    md_lines.append("\n## Control diff (no planted bug): false-positive proxy\n")
    md_lines.append("| Condition | Reviewer | Mean control findings |")
    md_lines.append("|---|---|---|")
    for key, stats in summary["by_condition_x_reviewer"].items():
        cond, reviewer = key.split("|")
        md_lines.append(f"| {cond} | {reviewer} | {stats['control_findings_mean']} |")

    out_md = EXPERIMENT / "benchmark.md"
    out_md.write_text("\n".join(md_lines))

    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")
    print()
    print(f"Cells graded: {summary['metadata']['cells_completed']}/{summary['metadata']['total_cells']}")
    print()
    print("=== Headline ===")
    for key, stats in summary["by_condition_x_reviewer"].items():
        cond, reviewer = key.split("|")
        print(
            f"  {cond:18s} {reviewer:7s} catch={stats['catch_rate']:.0%} "
            f"nits_median={stats['nit_count_median']:.0f} "
            f"total_mean={stats['total_findings_mean']:.1f}"
        )


if __name__ == "__main__":
    main()
