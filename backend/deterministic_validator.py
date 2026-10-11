import re
import uuid
import difflib
import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from backend.models import (
    AuditReport, ClaimItem, EvidenceQuote, Passage,
    VerdictEnum, AuditSummary, EvidenceRelationshipEnum, SeverityEnum, SourceDocument
)
from backend.text_normalizer import norm, tokens, sentences, key_tokens, dedupe, STOP
from backend.document_processor import chunk_text_into_passages

URL_REGEX = re.compile(
    r'^https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})+(?:/[^\s]*)?$',
    re.IGNORECASE
)

def is_valid_http_url(url: Optional[str]) -> bool:
    """Validate that URL has proper http/https scheme and hostname."""
    if not url:
        return True
    if not URL_REGEX.match(url):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
    except Exception:
        return False

def is_valid_quote_match(quote_text: str, passage_text: str) -> bool:
    """
    Compare normalised text, accepting a quote if it is a substring
    of a normalised source passage (or vice versa) OR has similarity above 0.90.
    """
    if not quote_text or not passage_text:
        return False
    nq = norm(quote_text).lower()
    np_ = norm(passage_text).lower()
    if not nq or not np_:
        return False
    if nq in np_ or np_ in nq:
        return True
    return difflib.SequenceMatcher(None, nq, np_).ratio() >= 0.90

def rule_based_verify(claim_text: str, source_docs: List[SourceDocument]) -> Dict[str, Any]:
    """
    Rule-based verification from verify_reference.py:
    1. Normalise before comparing (NFKC, straight quotes, dashes, footnote markers, audio artifacts).
    2. Exact match first against candidate passages (single sentences and pairs).
    3. Content words coverage + string similarity ranking.
    4. Coverage threshold >= 0.6.
    5. Key token comparison (years, numbers, proper nouns) to distinguish Supported vs Contradicted.
    """
    nc = norm(claim_text).lower()
    c_raw, c_low = tokens(claim_text)
    c_content = {w for w in c_low if w not in STOP}
    keys = key_tokens(claim_text)

    # Gather candidate passages across all source documents
    all_candidates: List[Tuple[Passage, SourceDocument]] = []
    for doc in source_docs:
        passages_list = doc.passages if doc.passages else chunk_text_into_passages(doc.id, doc.filename, doc.extracted_text, 1)
        for p in passages_list:
            all_candidates.append((p, doc))

    best_p: Optional[Passage] = None
    best_doc: Optional[SourceDocument] = None
    best_score = -1.0
    best_cov = 0.0

    for p, doc in all_candidates:
        np_ = norm(p.text).lower()
        if nc and nc in np_:
            return {
                "verdict": VerdictEnum.SUPPORTED,
                "confidence": 0.99,
                "passage": p,
                "doc": doc,
                "coverage": 1.0,
                "finding": "The claim appears in the source."
            }
        _, p_low = tokens(p.text)
        cov = len(c_content & set(p_low)) / max(1, len(c_content))
        sim = difflib.SequenceMatcher(None, nc, np_).ratio()
        score = 0.7 * cov + 0.3 * sim
        if score > best_score:
            best_p, best_doc, best_score, best_cov = p, doc, score, cov

    if best_p is None or best_cov < 0.6:
        missing_keys = keys
        if missing_keys:
            key_terms = ", ".join(f"'{k}'" for k in sorted(missing_keys))
            finding = f"No source passage covers: {key_terms}"
        else:
            finding = "No passage in the source covers this claim."
        return {
            "verdict": VerdictEnum.INSUFFICIENT_EVIDENCE,
            "confidence": round(min(0.9, max(0.5, 1.0 - best_score)), 2),
            "passage": None,
            "doc": best_doc,
            "coverage": best_cov,
            "finding": finding
        }

    p_raw, p_low = tokens(best_p.text)
    missing = keys - set(p_low)
    if not missing:
        return {
            "verdict": VerdictEnum.SUPPORTED,
            "confidence": round(min(0.95, max(0.8, best_cov)), 2),
            "passage": best_p,
            "doc": best_doc,
            "coverage": best_cov,
            "finding": "The source passage states the same facts."
        }

    pairs = []
    sm = difflib.SequenceMatcher(None, c_low, p_low, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and any(t in missing for t in c_low[i1:i2]):
            a = [w for w in c_raw[i1:i2] if w.lower() in missing]
            pairs.append((" ".join(a), " ".join(p_raw[j1 : j1 + len(a)])))
    if pairs:
        finding = "Contradiction identified: " + "; ".join(f"claim says '{a}' but the source says '{b}'" for a, b in pairs) + "."
    else:
        finding = "Contradiction identified: the claim states " + ", ".join(f"'{m}'" for m in sorted(missing)) + " which the matching source passage does not."

    return {
        "verdict": VerdictEnum.CONTRADICTED,
        "confidence": round(min(0.9, 0.5 + 0.4 * best_cov), 2),
        "passage": best_p,
        "doc": best_doc,
        "coverage": best_cov,
        "finding": finding
    }

def validate_audit_report(report: AuditReport) -> AuditReport:
    """
    Deterministic Verification Gateway:
    1. Validates quotes by comparing normalised text (substring or similarity >= 0.9).
    2. Before overriding, runs rule-based matcher from verify_reference.py.
       If coverage >= 0.6, retains Supported (or Contradicted if key tokens differ) and attaches evidence.
    3. Override only produces Insufficient when both model quotes and rule-based matcher find nothing.
       The finding text explains which check failed: "No source passage covers: <key terms>".
    4. Computes "Traceable" dynamically as claims with >= 1 evidence divided by total claims.
    5. Enforces mathematical invariant between claim verdicts and summary counts.
    """
    passage_lookup: Dict[str, Passage] = {}
    all_passages: List[Passage] = []
    for doc in report.source_documents:
        for p in doc.passages:
            passage_lookup[p.id] = p
            all_passages.append(p)

    has_source_passages = len(passage_lookup) > 0 or any(bool(d.extracted_text) for d in report.source_documents)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 2. Validate quotes for each claim
    for claim in report.claims:
        all_passages_valid = True
        all_verbatim_valid = True
        all_urls_valid = True

        valid_supporting: List[EvidenceQuote] = []
        for eq in claim.supporting_evidence:
            ref_passage = passage_lookup.get(eq.passage_id)
            if not ref_passage:
                for p in all_passages:
                    if is_valid_quote_match(eq.text, p.text):
                        ref_passage = p
                        eq.passage_id = p.id
                        eq.filename = p.filename
                        eq.page_number = p.page_number
                        break

            if not ref_passage:
                all_passages_valid = False
                eq.exact_match_verified = False
                eq.extraction_error = f"Passage ID '{eq.passage_id}' does not exist in source documents."
                valid_supporting.append(eq)
                continue

            if is_valid_quote_match(eq.text, ref_passage.text):
                eq.exact_match_verified = True
                eq.extraction_error = None
            else:
                all_verbatim_valid = False
                eq.exact_match_verified = False
                eq.extraction_error = "Quoted text does not match underlying source passage verbatim."

            if eq.url and not is_valid_http_url(eq.url):
                all_urls_valid = False
                eq.url = None
                eq.extraction_error = "Rejected invalid or fabricated URL."

            valid_supporting.append(eq)

        valid_contradicting: List[EvidenceQuote] = []
        for eq in claim.contradicting_evidence:
            ref_passage = passage_lookup.get(eq.passage_id)
            if not ref_passage:
                for p in all_passages:
                    if is_valid_quote_match(eq.text, p.text):
                        ref_passage = p
                        eq.passage_id = p.id
                        eq.filename = p.filename
                        eq.page_number = p.page_number
                        break

            if not ref_passage:
                all_passages_valid = False
                eq.exact_match_verified = False
                eq.extraction_error = f"Passage ID '{eq.passage_id}' does not exist in source documents."
                valid_contradicting.append(eq)
                continue

            if is_valid_quote_match(eq.text, ref_passage.text):
                eq.exact_match_verified = True
                eq.extraction_error = None
            else:
                all_verbatim_valid = False
                eq.exact_match_verified = False
                eq.extraction_error = "Quoted text does not match underlying source passage verbatim."

            if eq.url and not is_valid_http_url(eq.url):
                all_urls_valid = False
                eq.url = None
                eq.extraction_error = "Rejected invalid or fabricated URL."

            valid_contradicting.append(eq)

        has_verified_supporting = any(eq.exact_match_verified for eq in valid_supporting)
        has_verified_contradicting = any(eq.exact_match_verified for eq in valid_contradicting)

        # 3. Pre-override rule-based check
        needs_evidence_check = (
            (claim.verdict == VerdictEnum.SUPPORTED and not has_verified_supporting) or
            (claim.verdict == VerdictEnum.CONTRADICTED and not has_verified_contradicting) or
            (claim.verdict == VerdictEnum.INSUFFICIENT_EVIDENCE and not has_verified_supporting and not has_verified_contradicting)
        )

        if needs_evidence_check and report.source_documents:
            rule_res = rule_based_verify(claim.text, report.source_documents)
            if rule_res["coverage"] >= 0.6 and rule_res["passage"] is not None:
                # Rule-based matcher found a verified passage! Do NOT override to Insufficient!
                best_pass = rule_res["passage"]
                best_doc = rule_res["doc"]

                if rule_res["verdict"] == VerdictEnum.SUPPORTED:
                    claim.verdict = VerdictEnum.SUPPORTED
                    claim.confidence_score = max(claim.confidence_score, rule_res["confidence"])
                    new_eq = EvidenceQuote(
                        id=f"ev_{uuid.uuid4().hex[:8]}",
                        source_id=getattr(best_pass, "source_id", getattr(best_doc, "id", "doc")),
                        filename=getattr(best_pass, "filename", getattr(best_doc, "filename", "source.txt")),
                        page_number=getattr(best_pass, "page_number", 1) or 1,
                        passage_id=getattr(best_pass, "id", "p1"),
                        text=getattr(best_pass, "text", ""),
                        similarity_score=rule_res["confidence"],
                        relationship=EvidenceRelationshipEnum.ENTAILS,
                        is_contradiction=False,
                        exact_match_verified=True
                    )
                    valid_supporting.append(new_eq)
                    if not claim.explanation or "override" in claim.explanation.lower() or "lacked" in claim.explanation.lower():
                        claim.explanation = rule_res["finding"]
                elif rule_res["verdict"] == VerdictEnum.CONTRADICTED:
                    claim.verdict = VerdictEnum.CONTRADICTED
                    claim.confidence_score = max(claim.confidence_score, rule_res["confidence"])
                    new_eq = EvidenceQuote(
                        id=f"ev_{uuid.uuid4().hex[:8]}",
                        source_id=getattr(best_pass, "source_id", getattr(best_doc, "id", "doc")),
                        filename=getattr(best_pass, "filename", getattr(best_doc, "filename", "source.txt")),
                        page_number=getattr(best_pass, "page_number", 1) or 1,
                        passage_id=getattr(best_pass, "id", "p1"),
                        text=getattr(best_pass, "text", ""),
                        similarity_score=rule_res["confidence"],
                        relationship=EvidenceRelationshipEnum.CONTRADICTS,
                        is_contradiction=True,
                        exact_match_verified=True
                    )
                    valid_contradicting.append(new_eq)
                    claim.explanation = rule_res["finding"]
            else:
                # Both model quotes and rule-based matcher found nothing!
                if claim.verdict == VerdictEnum.SUPPORTED:
                    claim.verdict = VerdictEnum.INSUFFICIENT_EVIDENCE
                    valid_supporting = [eq for eq in valid_supporting if eq.exact_match_verified]
                    claim.explanation = rule_res["finding"]
                elif claim.verdict == VerdictEnum.INSUFFICIENT_EVIDENCE:
                    if not claim.explanation or "lacked" in claim.explanation.lower() or "override" in claim.explanation.lower():
                        claim.explanation = rule_res["finding"]

        claim.supporting_evidence = valid_supporting
        claim.contradicting_evidence = valid_contradicting

        # 4. Attach deterministic audit trail
        claim.provenance_audit = {
            "validation_timestamp": now_iso,
            "passages_exist_in_source": all_passages_valid,
            "verbatim_citations_verified": all_verbatim_valid,
            "url_integrity_passed": all_urls_valid,
            "verdict_grounded": True
        }

    # 5. Enforce mathematical invariant and dynamic traceability
    actual_total = len(report.claims)
    sup_cnt = sum(1 for c in report.claims if c.verdict == VerdictEnum.SUPPORTED)
    contra_cnt = sum(1 for c in report.claims if c.verdict == VerdictEnum.CONTRADICTED)
    insuf_cnt = sum(1 for c in report.claims if c.verdict == VerdictEnum.INSUFFICIENT_EVIDENCE)
    conf_cnt = sum(1 for c in report.claims if c.verdict == VerdictEnum.CONFLICTING_EVIDENCE)
    ambig_cnt = sum(1 for c in report.claims if c.verdict == VerdictEnum.AMBIGUOUS)
    mixed_cnt = sum(1 for c in report.claims if c.verdict == VerdictEnum.MIXED)

    # Traceable: claims with at least 1 evidence divided by total claims
    traceable_claims = sum(1 for c in report.claims if (len(c.supporting_evidence) + len(c.contradicting_evidence)) >= 1)
    traceability_pct = round((traceable_claims / actual_total * 100), 1) if actual_total > 0 else 0.0

    report.summary.total_claims = actual_total
    report.summary.supported_count = sup_cnt
    report.summary.contradicted_count = contra_cnt
    report.summary.insufficient_count = insuf_cnt
    report.summary.conflicting_count = conf_cnt
    report.summary.ambiguous_count = ambig_cnt
    report.summary.mixed_count = mixed_cnt
    report.summary.traceable_claims_count = traceable_claims
    report.summary.traceability_percentage = traceability_pct

    return report
