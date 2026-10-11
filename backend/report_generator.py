from typing import List
from backend.models import AuditReport, AuditSummary, ClaimItem, VerdictEnum

def generate_audit_summary(claims: List[ClaimItem], source_doc_count: int) -> AuditSummary:
    """
    Generate an evidentiary summary derived strictly from actual claim findings.
    Does not produce fabricated accuracy percentages.
    """
    total = len(claims)
    supported = sum(1 for c in claims if c.verdict == VerdictEnum.SUPPORTED)
    contradicted = sum(1 for c in claims if c.verdict == VerdictEnum.CONTRADICTED)
    insufficient = sum(1 for c in claims if c.verdict == VerdictEnum.INSUFFICIENT_EVIDENCE)
    conflicting = sum(1 for c in claims if c.verdict == VerdictEnum.CONFLICTING_EVIDENCE)
    ambiguous = sum(1 for c in claims if c.verdict == VerdictEnum.AMBIGUOUS)
    mixed = sum(1 for c in claims if c.verdict == VerdictEnum.MIXED)

    reasoning_count = sum(len(c.reasoning_issues) for c in claims)
    safety_count = sum(len(c.safety_issues) for c in claims)

    # Formulate truthful assessment
    findings = []
    if contradicted > 0:
        findings.append(f"Identified {contradicted} direct contradiction(s) or numerical discrepancy(s) against source material.")
    if conflicting > 0:
        findings.append(f"Identified {conflicting} claim(s) with conflicting evidence across different source documents.")
    if safety_count > 0:
        findings.append(f"Flagged {safety_count} safety consideration(s) or unverified directive(s).")
    if insufficient > 0:
        findings.append(f"Found {insufficient} claim(s) lacking supporting evidence in provided sources.")
    if supported > 0:
        findings.append(f"Corroborated {supported} claim(s) directly against primary source passages.")
    if mixed > 0:
        findings.append(f"Identified {mixed} partially corroborated or mixed claim(s).")

    if contradicted > 0 and safety_count > 0:
        assessment = f"Critical evidentiary and safety issues detected: {contradicted} contradictory claim(s) and {safety_count} unverified high-risk directive(s)."
    elif contradicted > 0:
        assessment = f"Auditing revealed {contradicted} factual contradiction(s) between the AI output and primary source documents."
    elif conflicting > 0:
        assessment = f"Divergent source accounts detected: {conflicting} claim(s) have conflicting evidence between source documents."
    elif insufficient == total and total > 0:
        assessment = "None of the audited claims could be corroborated by the supplied source documents."
    elif supported == total and total > 0:
        assessment = "All discrete claims are substantiated by traceable evidence in the provided source documents."
    elif supported > 0 and insufficient > 0:
        assessment = f"Partial grounding: {supported} claim(s) verified, but {insufficient} claim(s) remain ungrounded in the source material."
    else:
        assessment = f"Audit complete: {total} claims reviewed across {source_doc_count} source document(s)."

    # Dynamic traceability computation: claims with at least 1 evidence divided by total claims
    traceable_count = sum(1 for c in claims if (len(c.supporting_evidence) + len(c.contradicting_evidence)) >= 1)
    traceability_pct = round((traceable_count / total * 100), 1) if total > 0 else 0.0

    return AuditSummary(
        total_claims=total,
        supported_count=supported,
        contradicted_count=contradicted,
        insufficient_count=insufficient,
        conflicting_count=conflicting,
        ambiguous_count=ambiguous,
        mixed_count=mixed,
        reasoning_issue_count=reasoning_count,
        safety_issue_count=safety_count,
        overall_assessment=assessment,
        key_findings=findings,
        traceable_claims_count=traceable_count,
        traceability_percentage=traceability_pct
    )

def export_audit_to_markdown(report: AuditReport) -> str:
    """Generate professional Markdown audit report."""
    lines = [
        f"# Second Opinion — Audit Report: {report.title}",
        f"**Audit ID:** `{report.id}`  ",
        f"**Date:** {report.created_at}  ",
        f"**Status:** {report.status.value}  ",
        "",
        "## Executive Summary",
        f"> {report.summary.overall_assessment}",
        "",
        "### Evidentiary Metrics",
        f"- **Total Claims Reviewed:** {report.summary.total_claims}",
        f"- **Supported by Sources:** {report.summary.supported_count}",
        f"- **Contradicted by Sources:** {report.summary.contradicted_count}",
        f"- **Conflicting Evidence:** {getattr(report.summary, 'conflicting_count', 0)}",
        f"- **Insufficient Evidence:** {report.summary.insufficient_count}",
        f"- **Ambiguous / Mixed:** {report.summary.ambiguous_count + report.summary.mixed_count}",
        f"- **Safety Flags:** {report.summary.safety_issue_count}",
        f"- **Reasoning Issues:** {report.summary.reasoning_issue_count}",
        "",
        "## Key Findings",
    ]
    for kf in report.summary.key_findings:
        lines.append(f"- {kf}")

    lines.extend([
        "",
        "## Source Documents Reviewed",
    ])
    for doc in report.source_documents:
        lines.append(f"- **{doc.filename}** ({doc.page_count} page(s), {doc.passage_count} passages, {doc.size_bytes} bytes)")

    lines.extend([
        "",
        "## Claim-by-Claim Verification Ledger",
    ])

    for c in report.claims:
        lines.extend([
            f"### Claim #{c.claim_number}: [{c.verdict.value}] ({c.category.value})",
            f"**Text:** *\"{c.text}\"*  ",
            f"**Evidentiary Finding:** {c.explanation}  ",
            f"**Confidence:** {int(c.confidence_score * 100)}% ({c.confidence_basis})  ",
        ])

        if c.suggested_correction:
            lines.append(f"**Suggested Correction:** {c.suggested_correction}  ")

        if c.contradicting_evidence:
            lines.append("**Contradicting Evidence:**")
            for ev in c.contradicting_evidence:
                lines.append(f"> \"{ev.text}\"  \n> — *{ev.filename}*, Page {ev.page_number or 1} [Passage `{ev.passage_id}`]")

        if c.supporting_evidence:
            lines.append("**Supporting Evidence:**")
            for ev in c.supporting_evidence:
                lines.append(f"> \"{ev.text}\"  \n> — *{ev.filename}*, Page {ev.page_number or 1} [Passage `{ev.passage_id}`]")

        if c.safety_issues:
            lines.append("**Safety Alerts:**")
            for s in c.safety_issues:
                lines.append(f"- [{s.severity.value}] **{s.issue_type}**: {s.description} *(Action: {s.recommendation})*")

        lines.append("")

    lines.extend([
        "---",
        "*Report generated by Second Opinion AI Auditing Platform. All findings grounded strictly in verified source material.*"
    ])

    return "\n".join(lines)
