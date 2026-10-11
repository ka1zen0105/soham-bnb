import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
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

COMMON_SUFFIXES = {
    'tion', 'tions', 'sion', 'sions', 'chitectures', 'chitecture', 
    'tures', 'ture', 'ment', 'ments', 'able', 'ible', 'ity', 'ities',
    'ness', 'nesses', 'fully', 'ful', 'ing', 'ings', 'ism', 'isms',
    'ist', 'ists', 'ize', 'ized', 'izing', 'ise', 'ised', 'ising',
    'ally', 'ology', 'ological', 'ical', 'ic', 'ized', 'ance', 'ence',
    'ly', 'ers', 'er', 'est'
}

COMMON_PREFIX_FRAGMENTS = {
    'ar', 'organiza', 'implemen', 'configura', 'discrep', 'concen', 
    'infrap', 'experi', 'signifi', 'fundamen', 'infeasi'
}

def unwrap_text_into_blocks(text: str) -> List[Tuple[str, str]]:
    """
    Groups raw text into coherent semantic blocks (paragraphs or bullet points),
    healing soft line-wraps and hyphenated/broken words (e.g. from PDF copy-paste),
    while preserving genuine bullet points and paragraph breaks.
    Returns list of (block_type, block_text) tuples where block_type is 'bullet' or 'prose'.
    """
    raw_blocks = re.split(r'\n\s*\n', text)
    processed_items: List[Tuple[str, str]] = []
    
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
            
        lines = block.splitlines()
        current_lines: List[str] = []
        is_bullet = False
        
        for raw_line in lines:
            line_str = raw_line.strip()
            if not line_str or (line_str.startswith('#') and len(line_str.split()) < 3):
                continue
                
            bullet_match = re.match(r'^([-*•]|\d+\.)\s+(.+)$', line_str)
            if bullet_match:
                if current_lines:
                    processed_items.append(('bullet' if is_bullet else 'prose', ' '.join(current_lines)))
                    current_lines = []
                is_bullet = True
                current_lines.append(bullet_match.group(2).strip())
            else:
                if not current_lines:
                    is_bullet = False
                    current_lines.append(line_str)
                else:
                    prev = current_lines[-1]
                    # Case 1: Line ended with hyphen: e.g. organiza- or ar-
                    if prev.endswith('-'):
                        stem = prev[:-1].rstrip()
                        w1_m = re.search(r'[A-Za-z]+$', stem)
                        w2_m = re.match(r'^[A-Za-z]+', line_str)
                        if w1_m and w2_m:
                            w1, w2 = w1_m.group(), w2_m.group()
                            if w2.lower() in COMMON_SUFFIXES or w1.lower() in COMMON_PREFIX_FRAGMENTS:
                                current_lines[-1] = stem[:w1_m.start()] + w1 + w2 + line_str[w2_m.end():]
                            else:
                                current_lines[-1] = stem + '-' + line_str
                        else:
                            current_lines[-1] = stem + '-' + line_str
                    else:
                        # Case 2: Line ended without hyphen but words were split across line break (organiza / tion, ar / chitectures)
                        w1_m = re.search(r'[A-Za-z]+$', prev)
                        w2_m = re.match(r'^[A-Za-z]+', line_str)
                        if w1_m and w2_m and (w2_m.group().lower() in COMMON_SUFFIXES or w1_m.group().lower() in COMMON_PREFIX_FRAGMENTS):
                            w1, w2 = w1_m.group(), w2_m.group()
                            current_lines[-1] = prev[:w1_m.start()] + w1 + w2 + line_str[w2_m.end():]
                        else:
                            current_lines.append(line_str)
                            
        if current_lines:
            processed_items.append(('bullet' if is_bullet else 'prose', ' '.join(current_lines)))
            
    return processed_items

def extract_claims_deterministic(answer_text: str) -> List[ClaimItem]:
    """
    Extract atomic claims deterministically from answer text, splitting into
    single-sentence atomic claims before verification, healing soft line-wraps
    and word fragmentation, and preserving character positions.
    """
    claims: List[ClaimItem] = []
    if not answer_text.strip():
        return claims

    claim_idx = 1
    blocks = unwrap_text_into_blocks(answer_text)

    for block_type, block_text in blocks:
        sents = sentences(block_text)
        for s_clean in sents:
            s_clean = s_clean.strip()
            if len(s_clean) < 10:
                continue

            words = s_clean.split()
            first_phrase = " ".join(words[:min(4, len(words))])
            pos = answer_text.find(first_phrase)
            if pos != -1:
                start_off = pos
                last_phrase = " ".join(words[max(0, len(words)-3):])
                end_pos = answer_text.find(last_phrase, start_off)
                end_off = (end_pos + len(last_phrase)) if end_pos != -1 else (start_off + len(s_clean))
            else:
                start_off = 0
                end_off = len(s_clean)

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

    if not claims and answer_text.strip():
        text_clean = answer_text.strip()
        cat = categorize_claim(text_clean)
        claims.append(ClaimItem(
            id="clm_1",
            claim_number=1,
            text=text_clean,
            start_offset=0,
            end_offset=len(text_clean),
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
