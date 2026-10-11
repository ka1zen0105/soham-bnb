import re
from typing import List, Tuple, Optional, Dict, Any
from backend.models import NumericalDiscrepancy
from backend.text_normalizer import normalize_text, strip_footnote_markers

DATE_PATTERN = re.compile(
    r'\b(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?:\d{1,2}(?:st|nd|rd|th)?,\s+)?\d{4}|Q[1-4]\s+\d{4})\b',
    re.IGNORECASE
)

# Multi-century year matching (1600 - 2099)
YEAR_ONLY_PATTERN = re.compile(r'\b(1[6789]\d\d|20\d\d)\b')

# Strict scale matching that requires complete words
NUMBER_PATTERN = re.compile(
    r'(?P<currency>[\$\€\£\¥])?\s*(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<scale>\b(?:billion|million|trillion|thousand)\b)?\s*(?P<percent>%)?',
    re.IGNORECASE
)

# Product model codes, standards, or identifiers to ignore as standalone quantities
IDENTIFIER_PATTERN = re.compile(r'[a-zA-Z]+-\d+|\bQ[1-4]\b|\bISO/\w+\b', re.IGNORECASE)

def extract_dates(text: str) -> List[str]:
    """Extract standard full date strings and financial quarters."""
    cleaned = strip_footnote_markers(text)
    return [m.group(0).strip() for m in DATE_PATTERN.finditer(cleaned)]

def parse_number_value(match: re.Match) -> Tuple[float, str, str]:
    """Parse matched number into (normalized_float, raw_str, category)."""
    raw_num = match.group('number').replace(',', '')
    val = float(raw_num)
    scale = (match.group('scale') or '').lower()
    
    if scale == 'billion':
        val *= 1e9
    elif scale == 'million':
        val *= 1e6
    elif scale == 'thousand':
        val *= 1e3
    elif scale == 'trillion':
        val *= 1e12

    raw_str = match.group(0).strip()
    
    category = "QUANTITY"
    if match.group('currency') or raw_str.startswith('$') or raw_str.startswith('€') or raw_str.startswith('£'):
        category = "CURRENCY"
    elif match.group('percent') or '%' in raw_str:
        category = "PERCENTAGE"
    elif YEAR_ONLY_PATTERN.match(raw_str) and not scale:
        category = "YEAR"

    return val, raw_str, category

def extract_numbers(text: str) -> List[Tuple[float, str, str]]:
    """
    Extract numbers with categories, excluding numbers that are purely part of full date strings,
    quarters, or product identifiers (like BC-902).
    """
    cleaned = strip_footnote_markers(text)
    date_spans = [m.span() for m in DATE_PATTERN.finditer(cleaned)]
    identifier_spans = [m.span() for m in IDENTIFIER_PATTERN.finditer(cleaned)]

    results = []
    for m in NUMBER_PATTERN.finditer(cleaned):
        m_start, m_end = m.span()
        
        # Check if contained inside full date or identifier
        inside_date = any(d_start <= m_start and m_end <= d_end for d_start, d_end in date_spans)
        inside_id = any(i_start <= m_start and m_end <= i_end for i_start, i_end in identifier_spans)
        
        if inside_id:
            continue

        raw = m.group(0).strip()
        if inside_date:
            continue

        try:
            val, raw_str, category = parse_number_value(m)
            # Avoid matching trivial isolated single digits like "1" or "2" unless currency/percent
            if category == "QUANTITY" and val < 10 and not match_has_unit(m, cleaned):
                continue
            results.append((val, raw_str, category))
        except (ValueError, TypeError):
            continue

    return results

def match_has_unit(match: re.Match, full_text: str) -> bool:
    """Check if number is immediately followed by a measurement unit (e.g. months, years, mg)."""
    end_pos = match.end()
    following_text = full_text[end_pos:end_pos + 15].strip()
    return bool(re.match(r'^(months|years|days|mg|ml|patients|cases|endpoints)\b', following_text, re.IGNORECASE))

def check_date_consistency(claim_text: str, evidence_text: str) -> Optional[Tuple[str, str, str]]:
    """
    Check if a specific date or year in claim contradicts date in evidence.
    Returns (claim_date, evidence_date, explanation) if discrepancy found.
    Only checks when the texts discuss related events.
    """
    claim_dates = extract_dates(claim_text)
    evidence_dates = extract_dates(evidence_text)

    if claim_dates and evidence_dates:
        # Require topical overlap between sentences
        c_norm_words = set(normalize_text(claim_text).split())
        e_norm_words = set(normalize_text(evidence_text).split())
        shared = c_norm_words.intersection(e_norm_words)
        # If they share at least one non-trivial keyword (e.g. action, fda, trial, revenue, review)
        non_trivial_shared = [w for w in shared if len(w) > 3 and w not in ('with', 'from', 'that', 'this')]
        if not non_trivial_shared:
            return None

        for cd in claim_dates:
            if cd.lower() in evidence_text.lower():
                continue
            for ed in evidence_dates:
                if cd.lower() != ed.lower():
                    return cd, ed, f"Claim specifies '{cd}' but source passage documents '{ed}'"

    return None

def check_numerical_consistency(claim_text: str, evidence_text: str) -> NumericalDiscrepancy:
    """
    Deterministically compare numerical figures and dates between claim and evidence.
    Only flags discrepancies when the metric category and subject context match.
    """
    # 1. Date consistency check
    date_mismatch = check_date_consistency(claim_text, evidence_text)
    if date_mismatch:
        c_date, e_date, detail = date_mismatch
        return NumericalDiscrepancy(
            has_discrepancy=True,
            claim_numbers=[c_date],
            source_numbers=[e_date],
            metric_type="Temporal / Date Mismatch",
            percentage_error=None,
            detail=detail
        )

    claim_nums = extract_numbers(claim_text)
    evidence_nums = extract_numbers(evidence_text)

    if not claim_nums or not evidence_nums:
        return NumericalDiscrepancy(has_discrepancy=False)

    # Context relevance check: claim and evidence must share context keywords
    c_words = set(normalize_text(claim_text).split())
    e_words = set(normalize_text(evidence_text).split())
    shared_words = c_words.intersection(e_words)

    discrepancy_found = False
    mismatched_claim_nums = []
    mismatched_ev_nums = []
    detail_reasons = []
    pct_err_val: Optional[float] = None

    for c_val, c_raw, c_cat in claim_nums:
        exact_found = any(c_raw.lower() == e_raw.lower() for _, e_raw, _ in evidence_nums)
        if exact_found:
            continue

        # If YEAR, compare for exact equality only (never apply percentage tolerance to years/dates)
        if c_cat == "YEAR":
            if len(shared_words) >= 5:
                compatible_ev = [
                    (e_val, e_raw, e_cat) for e_val, e_raw, e_cat in evidence_nums
                    if e_cat == "YEAR"
                ]
                if compatible_ev:
                    closest = min(compatible_ev, key=lambda x: abs(x[0] - c_val))
                    if abs(c_val - closest[0]) > 0:
                        discrepancy_found = True
                        mismatched_claim_nums.append(c_raw)
                        mismatched_ev_nums.append(closest[1])
                        detail_reasons.append(
                            f"Claim specifies year '{c_raw}' but source passage documents '{closest[1]}'"
                        )
            continue

        compatible_ev = [
            (e_val, e_raw, e_cat) for e_val, e_raw, e_cat in evidence_nums
            if e_cat == c_cat
        ]

        if compatible_ev:
            closest = min(compatible_ev, key=lambda x: abs(x[0] - c_val))
            diff = abs(c_val - closest[0])
            if diff > 1e-5:
                discrepancy_found = True
                mismatched_claim_nums.append(c_raw)
                mismatched_ev_nums.append(closest[1])
                pct_err = round((diff / max(abs(closest[0]), 1e-9)) * 100, 1)
                pct_err_val = pct_err
                detail_reasons.append(
                    f"Claim asserts '{c_raw}' but source passage specifies '{closest[1]}' (discrepancy of {pct_err}%)"
                )

    if discrepancy_found:
        return NumericalDiscrepancy(
            has_discrepancy=True,
            claim_numbers=mismatched_claim_nums,
            source_numbers=mismatched_ev_nums,
            metric_type="Numerical Mismatch",
            percentage_error=pct_err_val,
            detail="; ".join(detail_reasons)
        )

    return NumericalDiscrepancy(
        has_discrepancy=False,
        claim_numbers=[raw for _, raw, _ in claim_nums],
        source_numbers=[raw for _, raw, _ in evidence_nums],
        detail="Numerical values in claim align with evidence."
    )
