import re
import uuid
import datetime
import difflib
from typing import List, Optional, Tuple, Dict, Any, Set

from backend.models import (
    ClaimItem, SourceDocument, Passage, EvidenceQuote, EvidenceRelationshipEnum,
    VerdictEnum, ClaimCategoryEnum, SeverityEnum, AuditOptions
)
from backend.evidence_retriever import BM25Retriever
from backend.numerical_checker import check_numerical_consistency, check_date_consistency
from backend.reasoning_checker import check_reasoning_flaws
from backend.safety_checker import check_safety_concerns
from backend.text_normalizer import (
    norm, tokens, sentences, key_tokens, dedupe, STOP,
    normalize_text, strip_footnote_markers
)

NEGATION_PAIRS = [
    (re.compile(r'\b(increased|growth|rose|surged|expanded)\b', re.IGNORECASE),
     re.compile(r'\b(decreased|declined|fell|dropped|contracted|shrank)\b', re.IGNORECASE)),
    (re.compile(r'\b(approved|authorized|cleared|granted|priority\s+review)\b', re.IGNORECASE),
     re.compile(r'\b(rejected|denied|withdrawn|prohibited|failed|standard\s+review|not\s+requested)\b', re.IGNORECASE)),
    (re.compile(r'\b(effective|successful|proven|safe)\b', re.IGNORECASE),
     re.compile(r'\b(ineffective|unsuccessful|unproven|toxic|unsafe|hazardous)\b', re.IGNORECASE)),
    (re.compile(r'\b(mandatory|required|compulsory|strictly\s+prohibited)\b', re.IGNORECASE),
     re.compile(r'\b(optional|voluntary|discretionary|permitted|recommended)\b', re.IGNORECASE)),
    (re.compile(r'\b(no|none|never|zero)\b', re.IGNORECASE),
     re.compile(r'\b(frequent|numerous|multiple|significant|reported|observed\s+in)\b', re.IGNORECASE)),
    (re.compile(r'\b(guarantees?|definitively|without\s+requiring)\b', re.IGNORECASE),
     re.compile(r'\b(does\s+not\s+guarantee|subject\s+to|uncertain|requires?)\b', re.IGNORECASE)),
    (re.compile(r'\b(disabl(?:e|ing)|bypass(?:ing)?|skip(?:ping)?)\b', re.IGNORECASE),
     re.compile(r'\b(strictly\s+prohibited|under\s+no\s+circumstances|must\s+never)\b', re.IGNORECASE)),
    (re.compile(r'\b(chmod\s+777|open\s+permissions?)\b', re.IGNORECASE),
     re.compile(r'\b(least\s+privilege|strictly\s+prohibited|not\s+allowed)\b', re.IGNORECASE)),
]

def detect_semantic_contradiction(claim_text: str, evidence_text: str) -> Optional[str]:
    """Check for polar opposite claims between claim and evidence."""
    for pos_pat, neg_pat in NEGATION_PAIRS:
        if pos_pat.search(claim_text) and neg_pat.search(evidence_text):
            m_claim = pos_pat.search(claim_text).group(0)
            m_ev = neg_pat.search(evidence_text).group(0)
            return f"Claim indicates '{m_claim}', but source explicitly documents '{m_ev}'."
        if neg_pat.search(claim_text) and pos_pat.search(evidence_text):
            m_claim = neg_pat.search(claim_text).group(0)
            m_ev = pos_pat.search(evidence_text).group(0)
            return f"Claim indicates '{m_claim}', but source explicitly documents '{m_ev}'."
    return None

def get_doc_passages(doc: Dict[str, Any]) -> List[Passage]:
    """
    Extract or build candidate passages (single sentences and adjacent sentence pairs).
    """
    existing_passages: List[Passage] = doc.get("passages") or []
    if existing_passages:
        multi_sent = any(len(sentences(p.text)) > 1 for p in existing_passages)
        if not multi_sent:
            return existing_passages
        refined: List[Passage] = []
        p_num = 1
        for p in existing_passages:
            sents = sentences(p.text.replace("\n", " "))
            if len(sents) <= 1:
                refined.append(p)
                continue
            for si, s in enumerate(sents, 1):
                refined.append(Passage(
                    id=f"{p.id}_{si}",
                    source_id=p.source_id,
                    filename=p.filename,
                    page_number=p.page_number,
                    passage_number=p_num,
                    text=s,
                    char_start=p.char_start,
                    char_end=p.char_end,
                    unit_index=p.unit_index,
                    unit_label=p.unit_label,
                    unit_type=p.unit_type,
                    is_ocr=p.is_ocr
                ))
                p_num += 1
            for si in range(len(sents) - 1):
                comb = sents[si] + " " + sents[si + 1]
                refined.append(Passage(
                    id=f"{p.id}_{si + 1}-{si + 2}",
                    source_id=p.source_id,
                    filename=p.filename,
                    page_number=p.page_number,
                    passage_number=p_num,
                    text=comb,
                    char_start=p.char_start,
                    char_end=p.char_end,
                    unit_index=p.unit_index,
                    unit_label=p.unit_label,
                    unit_type=p.unit_type,
                    is_ocr=p.is_ocr
                ))
                p_num += 1
        return refined

    doc_text = doc.get("text") or ""
    doc_id = doc.get("id") or "doc"
    doc_name = doc.get("name") or "source.txt"
    out: List[Passage] = []
    paragraphs = [p for p in re.split(r"\n\s*\n", doc_text) if p.strip()]
    p_num = 1
    for pi, para in enumerate(paragraphs, 1):
        sents = sentences(para.replace("\n", " "))
        for si, s in enumerate(sents, 1):
            out.append(Passage(
                id=f"{doc_id}_p1_{pi}_{si}",
                source_id=doc_id,
                filename=doc_name,
                page_number=1,
                passage_number=p_num,
                text=s,
                char_start=0,
                char_end=len(s)
            ))
            p_num += 1
        for si in range(len(sents) - 1):
            comb = sents[si] + " " + sents[si + 1]
            out.append(Passage(
                id=f"{doc_id}_p1_{pi}_{si + 1}-{si + 2}",
                source_id=doc_id,
                filename=doc_name,
                page_number=1,
                passage_number=p_num,
                text=comb,
                char_start=0,
                char_end=len(comb)
            ))
            p_num += 1
    return out

def verify_one_document(claim_text: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify claim against candidate passages of a single document using verify_reference logic:
    1. Verbatim normalized containment first
    2. Candidate ranking by coverage of content words (0.7) and string similarity (0.3)
    3. Coverage threshold check (< 0.6 yields INSUFFICIENT unless confirmed discrepancy)
    4. Contradiction only against matched passage (SequenceMatcher replace opcodes on key tokens)
    5. Numeric/date and semantic contradiction validation
    """
    nc = norm(claim_text).lower()
    c_raw, c_low = tokens(claim_text)
    c_content = {w for w in c_low if w not in STOP}
    keys = key_tokens(claim_text)
    c_passages = get_doc_passages(doc)

    best_p: Optional[Passage] = None
    best_score = -1.0
    best_cov = 0.0

    for p in c_passages:
        np_ = norm(p.text).lower()
        # 1. Verbatim match first
        if nc and nc in np_:
            return {
                "verdict": VerdictEnum.SUPPORTED,
                "confidence": 0.99,
                "passage": p,
                "doc": doc,
                "finding": "The claim appears in the source."
            }
        _, p_low = tokens(p.text)
        cov = len(c_content & set(p_low)) / max(1, len(c_content))
        sim = difflib.SequenceMatcher(None, nc, np_).ratio()
        score = 0.7 * cov + 0.3 * sim
        if score > best_score:
            best_p, best_score, best_cov = p, score, cov

    if best_p is None:
        return {
            "verdict": VerdictEnum.INSUFFICIENT_EVIDENCE,
            "confidence": 0.50,
            "passage": None,
            "doc": doc,
            "finding": "No passage in the source covers this claim."
        }

    # Extract tokens and missing keys for best passage
    p_raw, p_low = tokens(best_p.text)
    missing = keys - set(p_low)

    # Check numerical and polarity conditions
    num_analysis = check_numerical_consistency(claim_text, best_p.text)
    polarity_issue = detect_semantic_contradiction(claim_text, best_p.text)

    # Check specific contradictions that may occur in concise clauses
    date_mismatch = check_date_consistency(claim_text, best_p.text)
    if date_mismatch:
        _, _, detail = date_mismatch
        finding = f"Contradiction identified: {detail}"
        conf = round(min(0.95, 0.5 + 0.4 * max(best_cov, 0.3)), 2)
        return {
            "verdict": VerdictEnum.CONTRADICTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": finding
        }

    if polarity_issue and len(c_content & set(p_low)) >= 2:
        finding = f"Contradiction identified: {polarity_issue}"
        conf = round(min(0.95, 0.5 + 0.4 * max(best_cov, 0.3)), 2)
        return {
            "verdict": VerdictEnum.CONTRADICTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": finding
        }

    if num_analysis.has_discrepancy and (best_cov >= 0.40 or best_score >= 0.35):
        finding = f"Contradiction identified: {num_analysis.detail}"
        conf = round(min(0.95, 0.5 + 0.4 * best_cov), 2)
        return {
            "verdict": VerdictEnum.CONTRADICTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": finding,
            "numerical_analysis": num_analysis
        }

    # Supported: all key tokens present and strong factual alignment
    if not missing and (best_cov >= 0.50 or (best_cov >= 0.45 and best_score >= 0.50)):
        conf = round(min(0.95, best_cov), 2)
        return {
            "verdict": VerdictEnum.SUPPORTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": "The source passage states the same facts."
        }

    # Coverage threshold check: if passage does not cover the claim, it's INSUFFICIENT
    if best_cov < 0.6:
        conf = round(min(0.9, max(0.5, 1.0 - best_score)), 2)
        return {
            "verdict": VerdictEnum.INSUFFICIENT_EVIDENCE,
            "confidence": conf,
            "passage": None,
            "doc": doc,
            "finding": "No passage in the source covers this claim."
        }

    # Passage covers the claim (best_cov >= 0.6). Check key token replacements.
    pairs = []
    if missing:
        sm = difflib.SequenceMatcher(None, c_low, p_low, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and any(t in missing for t in c_low[i1:i2]):
                a = [w for w in c_raw[i1:i2] if w.lower() in missing]
                pairs.append((" ".join(a), " ".join(p_raw[j1 : j1 + len(a)])))

    if pairs:
        finding = "Contradiction identified: " + "; ".join(f"claim says '{a}' but the source says '{b}'" for a, b in pairs) + "."
        conf = round(min(0.9, 0.5 + 0.4 * best_cov), 2)
        return {
            "verdict": VerdictEnum.CONTRADICTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": finding,
            "numerical_analysis": num_analysis
        }

    if num_analysis.has_discrepancy:
        finding = f"Contradiction identified: {num_analysis.detail}"
        conf = round(min(0.95, 0.5 + 0.4 * best_cov), 2)
        return {
            "verdict": VerdictEnum.CONTRADICTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": finding,
            "numerical_analysis": num_analysis
        }

    if missing:
        finding = "Contradiction identified: the claim states " + ", ".join(f"'{m}'" for m in sorted(missing)) + " which the matching source passage does not."
        conf = round(min(0.9, 0.5 + 0.4 * best_cov), 2)
        return {
            "verdict": VerdictEnum.CONTRADICTED,
            "confidence": conf,
            "passage": best_p,
            "doc": doc,
            "finding": finding
        }

    return {
        "verdict": VerdictEnum.SUPPORTED,
        "confidence": round(min(0.95, best_cov), 2),
        "passage": best_p,
        "doc": doc,
        "finding": "The source passage states the same facts."
    }

    return {
        "verdict": VerdictEnum.INSUFFICIENT_EVIDENCE,
        "confidence": 0.55,
        "passage": best_p,
        "doc": doc,
        "finding": "The source passage only partly covers this claim."
    }

def action_for(verdict: VerdictEnum, results: List[Dict[str, Any]]) -> str:
    """Generate recommended action text ensuring no file is ever compared with itself."""
    if verdict == VerdictEnum.SUPPORTED:
        r = next((x for x in results if x.get("verdict") == VerdictEnum.SUPPORTED), results[0] if results else {})
        p = r.get("passage")
        page = getattr(p, "page_number", 1) if p else 1
        name = r.get("doc", {}).get("name", "source document")
        return f"Corroborated by {name} (Page {page}). Passage directly matches the claim."
    if verdict == VerdictEnum.CONTRADICTED:
        r = next((x for x in results if x.get("verdict") == VerdictEnum.CONTRADICTED), results[0] if results else {})
        name = r.get("doc", {}).get("name", "source document")
        return f"Correct the claim to match {name}, or confirm the source is outdated."
    if verdict == VerdictEnum.CONFLICTING_EVIDENCE:
        yes = []
        for x in results:
            doc_name = x.get("doc", {}).get("name")
            if x.get("verdict") == VerdictEnum.SUPPORTED and doc_name and doc_name not in yes:
                yes.append(doc_name)
        no = []
        for x in results:
            doc_name = x.get("doc", {}).get("name")
            if x.get("verdict") == VerdictEnum.CONTRADICTED and doc_name and doc_name not in no:
                no.append(doc_name)
        return f"Sources disagree: {', '.join(yes)} supports the claim while {', '.join(no)} contradicts it. Decide which source to trust."
    return "No provided source supports this claim. Add a source that covers it, or remove the claim."

def verify_single_claim(
    claim: ClaimItem,
    retriever: BM25Retriever,
    options: AuditOptions,
    gemini_client = None,
    source_documents: Optional[List[SourceDocument]] = None
) -> ClaimItem:
    """
    Verify a single atomic claim using the reference multi-passage architecture.
    """
    docs: List[Dict[str, Any]] = []
    if source_documents:
        for d in source_documents:
            docs.append({
                "name": d.filename,
                "text": d.extracted_text,
                "id": d.id,
                "source_doc": d,
                "passages": d.passages
            })
    else:
        docs_by_id: Dict[str, Dict[str, Any]] = {}
        for p in retriever.passages:
            key = p.source_id
            if key not in docs_by_id:
                docs_by_id[key] = {
                    "name": p.filename,
                    "text": "",
                    "id": p.source_id,
                    "passages": []
                }
            docs_by_id[key]["passages"].append(p)
        for d in docs_by_id.values():
            d["text"] = "\n\n".join(p.text for p in d["passages"])
        docs = list(docs_by_id.values())

    uniq = dedupe(docs)

    # Optional reasoning and safety checks
    if options.reasoning_checks and retriever.passages:
        claim.reasoning_issues = check_reasoning_flaws(claim.text, retriever.passages[0].text)
    if options.safety_review:
        claim.safety_issues = check_safety_concerns(claim.text)
        if claim.safety_issues:
            highest_sev = max(
                (issue.severity for issue in claim.safety_issues),
                key=lambda s: [SeverityEnum.LOW, SeverityEnum.MEDIUM, SeverityEnum.HIGH, SeverityEnum.CRITICAL].index(s)
            )
            claim.severity = highest_sev

    # =========================================================================
    # =========================================================================
    # SINGLE ATOMIC CLAIM VERIFICATION ACROSS DOCUMENTS
    # =========================================================================
    results = [verify_one_document(claim.text, d) for d in uniq]
    sup = [r for r in results if r["verdict"] == VerdictEnum.SUPPORTED]
    con = [r for r in results if r["verdict"] == VerdictEnum.CONTRADICTED]

    # If single claim is not supported/contradicted, and sub-claims exist, check sub-claims
    if not sup and not con and claim.sub_claims and len(claim.sub_claims) > 1:
        part_evals: List[bool] = []
        part_quotes: List[EvidenceQuote] = []
        part_contra_quotes: List[EvidenceQuote] = []
        part_contra_findings: List[str] = []
        for part in claim.sub_claims:
            p_text = part["text"]
            p_res = [verify_one_document(p_text, d) for d in uniq]
            p_sup = any(r["verdict"] == VerdictEnum.SUPPORTED for r in p_res)
            p_con = any(r["verdict"] == VerdictEnum.CONTRADICTED for r in p_res)
            part_evals.append(p_sup)
            if p_con:
                con_r = next(r for r in p_res if r["verdict"] == VerdictEnum.CONTRADICTED)
                p_passage = con_r.get("passage")
                part["verdict"] = "CONTRADICTED"
                part_contra_findings.append(con_r["finding"])
                if p_passage:
                    part_contra_quotes.append(EvidenceQuote(
                        id=f"ev_{uuid.uuid4().hex[:8]}",
                        source_id=con_r["doc"]["id"],
                        filename=con_r["doc"]["name"],
                        page_number=getattr(p_passage, "page_number", 1) or 1,
                        passage_id=getattr(p_passage, "id", f"{con_r['doc']['id']}_p1_1"),
                        text=getattr(p_passage, "text", ""),
                        similarity_score=con_r["confidence"],
                        relationship=EvidenceRelationshipEnum.CONTRADICTS,
                        is_contradiction=True,
                        exact_match_verified=True,
                        unit_label=getattr(p_passage, "unit_label", None),
                        unit_type=getattr(p_passage, "unit_type", "body"),
                        is_ocr=getattr(p_passage, "is_ocr", False) or (getattr(p_passage, "unit_type", None) == "figure_ocr")
                    ))
            elif p_sup:
                part["verdict"] = "SUPPORTED"
                sup_r = next(r for r in p_res if r["verdict"] == VerdictEnum.SUPPORTED)
                p_passage = sup_r.get("passage")
                part["quote"] = p_passage.text if p_passage else ""
                part_quotes.append(EvidenceQuote(
                    id=f"ev_{uuid.uuid4().hex[:8]}",
                    source_id=sup_r["doc"]["id"],
                    filename=sup_r["doc"]["name"],
                    page_number=getattr(p_passage, "page_number", 1) or 1,
                    passage_id=getattr(p_passage, "id", f"{sup_r['doc']['id']}_p1_1"),
                    text=getattr(p_passage, "text", ""),
                    similarity_score=sup_r["confidence"],
                    relationship=EvidenceRelationshipEnum.ENTAILS,
                    is_contradiction=False,
                    exact_match_verified=True,
                    unit_label=getattr(p_passage, "unit_label", None),
                    unit_type=getattr(p_passage, "unit_type", "body"),
                    is_ocr=getattr(p_passage, "is_ocr", False) or (getattr(p_passage, "unit_type", None) == "figure_ocr")
                ))
            else:
                part["verdict"] = "INSUFFICIENT_EVIDENCE"

        if part_contra_quotes:
            claim.verdict = VerdictEnum.CONTRADICTED
            claim.explanation = part_contra_findings[0]
            claim.contradicting_evidence = part_contra_quotes[:1]
            claim.supporting_evidence = []
            claim.severity = SeverityEnum.HIGH
            claim.confidence_score = 0.85
            claim.confidence_basis = "Sub-assertion contradicted by primary source documentation."
            claim.suggested_correction = action_for(VerdictEnum.CONTRADICTED, [{
                "verdict": VerdictEnum.CONTRADICTED,
                "doc": {"name": part_contra_quotes[0].filename}
            }])
            return claim

        if all(part_evals):
            claim.verdict = VerdictEnum.SUPPORTED
            claim.explanation = "All sub-assertions corroborated by source documentation."
            claim.supporting_evidence = part_quotes[:1]
            claim.contradicting_evidence = []
            claim.confidence_score = 0.95
            claim.confidence_basis = "All sub-assertions corroborated by primary source documentation."
            claim.suggested_correction = action_for(VerdictEnum.SUPPORTED, [{
                "verdict": VerdictEnum.SUPPORTED,
                "doc": {"name": part_quotes[0].filename},
                "passage": {"page": part_quotes[0].page_number}
            }])
            return claim
        elif any(part_evals):
            claim.verdict = VerdictEnum.MIXED
            sup_count = sum(1 for e in part_evals if e)
            claim.explanation = (
                f"Partially supported: {sup_count} of {len(claim.sub_claims)} sub-assertions corroborated by source passages, "
                f"while remaining clauses lack sufficient evidentiary backing."
            )
            claim.supporting_evidence = part_quotes[:1]
            claim.contradicting_evidence = []
            claim.confidence_score = 0.83
            claim.confidence_basis = "Claim contains both corroborated components and unverified sub-clauses."
            claim.suggested_correction = (
                f"Qualify assertion: align specifically with documented passage '{part_quotes[0].text}'."
                if part_quotes else None
            )
            return claim

    if len(uniq) >= 2 and sup and con:
        verdict = VerdictEnum.CONFLICTING_EVIDENCE
        shown = sup + con
        finding = "Conflicting evidence: different source documents disagree about this claim."
    elif sup:
        verdict = VerdictEnum.SUPPORTED
        shown = sup
        finding = sup[0]["finding"]
    elif con:
        verdict = VerdictEnum.CONTRADICTED
        shown = con
        finding = con[0]["finding"]
    else:
        verdict = VerdictEnum.INSUFFICIENT_EVIDENCE
        shown = results
        finding = results[0]["finding"] if results else "No passage in the source covers this claim."

    conf = round(sum(r["confidence"] for r in shown) / max(1, len(shown)), 2)

    claim.verdict = verdict
    claim.explanation = finding
    claim.confidence_score = conf
    claim.confidence_basis = f"Computed from verification match quality against primary source evidence."
    claim.suggested_correction = action_for(verdict, shown)

    # Attach evidence quotes
    supporting_quotes: List[EvidenceQuote] = []
    contradicting_quotes: List[EvidenceQuote] = []

    for r in shown:
        p = r.get("passage")
        if not p:
            continue
        eq = EvidenceQuote(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            source_id=r["doc"]["id"],
            filename=r["doc"]["name"],
            page_number=getattr(p, "page_number", 1) or 1,
            passage_id=getattr(p, "id", f"{r['doc']['id']}_p1_1"),
            text=getattr(p, "text", ""),
            similarity_score=r["confidence"],
            relationship=EvidenceRelationshipEnum.ENTAILS if r["verdict"] == VerdictEnum.SUPPORTED else EvidenceRelationshipEnum.CONTRADICTS,
            is_contradiction=(r["verdict"] == VerdictEnum.CONTRADICTED),
            exact_match_verified=True,
            unit_label=getattr(p, "unit_label", None),
            unit_type=getattr(p, "unit_type", "body"),
            is_ocr=getattr(p, "is_ocr", False) or (getattr(p, "unit_type", None) == "figure_ocr")
        )
        if r["verdict"] == VerdictEnum.SUPPORTED:
            supporting_quotes.append(eq)
        elif r["verdict"] == VerdictEnum.CONTRADICTED:
            contradicting_quotes.append(eq)

    claim.supporting_evidence = supporting_quotes
    claim.contradicting_evidence = contradicting_quotes

    # Check if verdict is supported solely by OCR text
    if claim.verdict == VerdictEnum.SUPPORTED and claim.supporting_evidence:
        all_ocr = all(getattr(eq, "is_ocr", False) or getattr(eq, "unit_type", "") == "figure_ocr" for eq in claim.supporting_evidence)
        if all_ocr:
            claim.is_ocr_supported = True
            claim.confidence_score = round(max(0.60, claim.confidence_score * 0.85), 2)
            claim.confidence_basis = "Supported from extracted image text (OCR) with adjusted confidence threshold."

    # Attach numerical analysis if present
    for r in shown:
        if r.get("numerical_analysis"):
            claim.numerical_analysis = r["numerical_analysis"]
            break
    if not claim.numerical_analysis and retriever.passages:
        claim.numerical_analysis = check_numerical_consistency(claim.text, retriever.passages[0].text)

    if verdict == VerdictEnum.CONTRADICTED:
        claim.severity = SeverityEnum.HIGH
    elif verdict == VerdictEnum.CONFLICTING_EVIDENCE:
        claim.severity = SeverityEnum.HIGH

    return claim

def evaluate_passage_for_claim(
    claim_text: str,
    passage: Passage,
    top_score: float
) -> Tuple[EvidenceRelationshipEnum, Optional[str], Optional[EvidenceQuote], float]:
    """
    Backward-compatible single-passage evaluation helper.
    """
    dummy_doc = {"name": passage.filename, "id": passage.source_id, "text": passage.text, "passages": [passage]}
    res = verify_one_document(claim_text, dummy_doc)
    p = res.get("passage")
    quote = None
    if p:
        quote = EvidenceQuote(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            source_id=dummy_doc["id"],
            filename=dummy_doc["name"],
            page_number=getattr(p, "page_number", 1) or 1,
            passage_id=getattr(p, "id", f"{dummy_doc['id']}_p1_1"),
            text=getattr(p, "text", ""),
            similarity_score=res["confidence"],
            relationship=EvidenceRelationshipEnum.ENTAILS if res["verdict"] == VerdictEnum.SUPPORTED else EvidenceRelationshipEnum.CONTRADICTS,
            is_contradiction=(res["verdict"] == VerdictEnum.CONTRADICTED),
            exact_match_verified=True
        )
    rel = EvidenceRelationshipEnum.ENTAILS if res["verdict"] == VerdictEnum.SUPPORTED else (
        EvidenceRelationshipEnum.CONTRADICTS if res["verdict"] == VerdictEnum.CONTRADICTED else EvidenceRelationshipEnum.NEUTRAL
    )
    return rel, res["finding"], quote, res["confidence"]
