import re
import uuid
from typing import List, Dict, Any, Optional
from backend.models import ClaimItem, VerdictEnum, ClaimCategoryEnum, SeverityEnum

from backend.text_normalizer import sentences, strip_footnote_markers
from backend.numerical_checker import extract_dates

SAFETY_KEYWORDS = re.compile(r'\b(dose|dosage|contraindicated|safety|toxic|hazard|warning|caution|lethal|dangerous|unauthorized|risk|emergency|severe)\b', re.IGNORECASE)
REASONING_KEYWORDS = re.compile(r'\b(therefore|consequently|as a result|causes|proves|implies|leads to|because|demonstrates that|guarantees)\b', re.IGNORECASE)

def has_number_or_date(text: str) -> bool:
    """
    Check if the claim contains a genuine number or date.
    Footnote markers like [1], [a], [note 1] are stripped first so citations
    are not misclassified as numerical data.
    """
    cleaned = strip_footnote_markers(text)
    if extract_dates(cleaned):
        return True
    if re.search(r'\b\d+(?:[.,]\d+)*\b|\$\d+|\d+%', cleaned):
        return True
    return False

def categorize_claim(text: str) -> ClaimCategoryEnum:
    if SAFETY_KEYWORDS.search(text):
        return ClaimCategoryEnum.SAFETY
    if has_number_or_date(text):
        return ClaimCategoryEnum.NUMERICAL
    if REASONING_KEYWORDS.search(text):
        return ClaimCategoryEnum.REASONING
    return ClaimCategoryEnum.FACTUAL

def decompose_sub_claims(text: str) -> List[str]:
    """
    Decompose a compound or multi-part claim into distinct verifiable sub-assertions.
    """
    delims = r'(?:;\s*|,\s+and\s+|,\s+but\s+|,\s+while\s+|,\s+whereas\s+|,\s+representing\s+|,\s+providing\s+|,\s+driven\s+by\s+|\s+with\s+(?:zero|no|\d+)\s+)'
    parts = re.split(delims, text, flags=re.IGNORECASE)
    cleaned_parts = [p.strip().rstrip('.,;') for p in parts if len(p.strip()) >= 15]
    if len(cleaned_parts) > 1:
        return cleaned_parts
    return []

def split_claims_into_atomic(claims: List[ClaimItem]) -> List[ClaimItem]:
    """
    Split extracted claims into single-sentence atomic claims before verification.
    Each claim gets one verdict.
    """
    atomic: List[ClaimItem] = []
    claim_idx = 1
    for c in claims:
        sents = sentences(c.text)
        if len(sents) <= 1:
            c.claim_number = claim_idx
            c.id = f"clm_{claim_idx}"
            c.category = categorize_claim(c.text)
            c.severity = SeverityEnum.MEDIUM if c.category == ClaimCategoryEnum.NUMERICAL else (
                SeverityEnum.HIGH if c.category == ClaimCategoryEnum.SAFETY else SeverityEnum.LOW
            )
            c.sub_claims = []
            atomic.append(c)
            claim_idx += 1
        else:
            for s in sents:
                s_clean = s.strip()
                if not s_clean:
                    continue
                cat = categorize_claim(s_clean)
                atomic.append(ClaimItem(
                    id=f"clm_{claim_idx}",
                    claim_number=claim_idx,
                    text=s_clean,
                    start_offset=c.start_offset,
                    end_offset=c.end_offset,
                    verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
                    category=cat,
                    explanation="",
                    supporting_evidence=[],
                    contradicting_evidence=[],
                    confidence_score=0.0,
                    confidence_basis="",
                    severity=SeverityEnum.MEDIUM if cat == ClaimCategoryEnum.NUMERICAL else (
                        SeverityEnum.HIGH if cat == ClaimCategoryEnum.SAFETY else SeverityEnum.LOW
                    ),
                    sub_claims=[]
                ))
                claim_idx += 1
    return atomic

def extract_claims_deterministic(answer_text: str) -> List[ClaimItem]:
    """
    Extract atomic claims deterministically from answer text, splitting into
    single-sentence atomic claims before verification and preserving character positions.
    """
    claims: List[ClaimItem] = []
    if not answer_text.strip():
        return claims

    claim_idx = 1
    lines = answer_text.splitlines(keepends=True)
    char_cursor = 0

    for line in lines:
        line_len = len(line)
        stripped = line.strip()
        
        # Skip empty lines, headers without assertions, or trivial greetings
        if not stripped or (stripped.startswith('#') and len(stripped.split()) < 3):
            char_cursor += line_len
            continue
            
        # Check for bullet point
        bullet_match = re.match(r'^\s*([-*•]|\d+\.)\s*(.+)$', line)
        if bullet_match:
            bullet_content = bullet_match.group(2).strip()
            # Split bullet into discrete single-sentence atomic claims
            sents = sentences(bullet_content)
            for s_clean in sents:
                if len(s_clean) < 10:
                    continue
                pos = answer_text.find(s_clean, char_cursor)
                start_off = pos if pos != -1 else char_cursor
                end_off = start_off + len(s_clean)
                
                cat = categorize_claim(s_clean)
                claims.append(ClaimItem(
                    id=f"clm_{claim_idx}",
                    claim_number=claim_idx,
                    text=s_clean,
                    start_offset=start_off,
                    end_offset=end_off,
                    verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
                    category=cat,
                    explanation="",
                    supporting_evidence=[],
                    contradicting_evidence=[],
                    confidence_score=0.0,
                    confidence_basis="",
                    severity=SeverityEnum.MEDIUM if cat == ClaimCategoryEnum.NUMERICAL else (
                        SeverityEnum.HIGH if cat == ClaimCategoryEnum.SAFETY else SeverityEnum.LOW
                    ),
                    sub_claims=[]
                ))
                claim_idx += 1
        else:
            # Regular prose paragraph: split into discrete single-sentence atomic claims
            sents = sentences(stripped)
            for s_clean in sents:
                if len(s_clean) < 12:
                    continue
                pos = answer_text.find(s_clean, char_cursor)
                start_off = pos if pos != -1 else char_cursor
                end_off = start_off + len(s_clean)

                cat = categorize_claim(s_clean)
                claims.append(ClaimItem(
                    id=f"clm_{claim_idx}",
                    claim_number=claim_idx,
                    text=s_clean,
                    start_offset=start_off,
                    end_offset=end_off,
                    verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
                    category=cat,
                    explanation="",
                    supporting_evidence=[],
                    contradicting_evidence=[],
                    confidence_score=0.0,
                    confidence_basis="",
                    severity=SeverityEnum.MEDIUM if cat == ClaimCategoryEnum.NUMERICAL else (
                        SeverityEnum.HIGH if cat == ClaimCategoryEnum.SAFETY else SeverityEnum.LOW
                    ),
                    sub_claims=[]
                ))
                claim_idx += 1

        char_cursor += line_len

    # If no claims parsed (e.g. single sentence without standard punctuation), use full text
    if not claims and answer_text.strip():
        text_clean = answer_text.strip()
        pos = answer_text.find(text_clean)
        cat = categorize_claim(text_clean)
        claims.append(ClaimItem(
            id="clm_1",
            claim_number=1,
            text=text_clean,
            start_offset=pos if pos != -1 else 0,
            end_offset=(pos + len(text_clean)) if pos != -1 else len(answer_text),
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=cat,
            explanation="",
            supporting_evidence=[],
            contradicting_evidence=[],
            confidence_score=0.0,
            confidence_basis="",
            severity=SeverityEnum.LOW
        ))

    return claims
