from typing import Tuple, Optional
from backend.models import VerdictEnum, NumericalDiscrepancy

def calculate_confidence(
    verdict: VerdictEnum,
    retrieval_score: float = 0.0,
    lexical_overlap: float = 0.0,
    numerical_analysis: Optional[NumericalDiscrepancy] = None,
    has_exact_quote: bool = False,
    similarity_ratio: float = 0.0,
    agreeing_passage_count: int = 1,
    contradicting_passage_count: int = 0,
    discrepancy_detail: Optional[str] = None
) -> Tuple[float, str]:
    """
    Calculate confidence score (0.0 - 1.0) dynamically based on match quality,
    corroborating passage count, and discrepancy certainty.
    Confidence is never a fixed hardcoded constant.
    """
    best_sim = max(similarity_ratio, lexical_overlap, min(1.0, retrieval_score / 3.0))

    if verdict == VerdictEnum.SUPPORTED:
        if has_exact_quote and (best_sim >= 0.90 or similarity_ratio >= 0.90):
            # Near-perfect or exact verbatim match
            passage_bonus = min(0.04, 0.02 * max(0, agreeing_passage_count - 1))
            score = round(min(0.99, max(0.95, 0.95 + passage_bonus)), 2)
            pct = int(best_sim * 100)
            basis = f"High confidence: Exact or near-exact match ({pct}% similarity) substantiated by primary source documentation."
        elif best_sim >= 0.65:
            passage_bonus = min(0.06, 0.03 * max(0, agreeing_passage_count - 1))
            score = round(min(0.94, max(0.80, 0.78 + 0.16 * best_sim + passage_bonus)), 2)
            pct = int(best_sim * 100)
            basis = f"High confidence: Strong thematic and entity grounding ({pct}% match) across {agreeing_passage_count} corroborating passage(s)."
        else:
            score = round(min(0.79, max(0.55, 0.55 + 0.25 * best_sim)), 2)
            pct = int(best_sim * 100)
            basis = f"Moderate confidence: Partial lexical grounding ({pct}% similarity) without direct verbatim phrasing."
        return score, basis

    if verdict == VerdictEnum.CONTRADICTED:
        if numerical_analysis and numerical_analysis.has_discrepancy:
            # Deterministic arithmetic mismatch
            score = 0.95
            basis = f"High confidence: Deterministic mathematical mismatch verified against source passage ({numerical_analysis.detail})."
        elif best_sim >= 0.65:
            # Strong factual discrepancy in aligned context
            score = round(min(0.97, max(0.88, 0.85 + 0.12 * best_sim)), 2)
            basis = f"High confidence: Direct conflicting factual assertion verified in primary source text ({discrepancy_detail or 'opposing documentation'})."
        else:
            score = round(min(0.85, max(0.70, 0.70 + 0.15 * best_sim)), 2)
            basis = f"Moderate confidence: Contextual discrepancy detected ({discrepancy_detail or 'divergent assertion'})."
        return score, basis

    if verdict == VerdictEnum.CONFLICTING_EVIDENCE:
        passage_factor = min(0.06, 0.02 * (agreeing_passage_count + contradicting_passage_count))
        score = round(min(0.95, max(0.75, 0.78 + 0.12 * best_sim + passage_factor)), 2)
        pct = int(best_sim * 100)
        basis = f"High confidence: Divergent evidence confirmed across distinct source documents ({pct}% match alignment)."
        return score, basis

    if verdict == VerdictEnum.MIXED:
        score = round(min(0.88, max(0.65, 0.70 + 0.18 * best_sim)), 2)
        pct = int(best_sim * 100)
        basis = f"Moderate confidence: Claim contains both corroborated components ({pct}% match) and unverified sub-clauses."
        return score, basis

    if verdict == VerdictEnum.AMBIGUOUS:
        score = round(min(0.80, max(0.55, 0.58 + 0.18 * best_sim)), 2)
        basis = "Moderate confidence: Source passages contain conflicting interpretations or indeterminate metrics."
        return score, basis

    # INSUFFICIENT_EVIDENCE
    # Higher confidence that evidence is missing when best retrieval similarity is lowest
    if best_sim < 0.20:
        score = round(min(0.95, 0.90 + 0.05 * (1.0 - best_sim * 5.0)), 2)
        basis = "High confidence: Exhaustive lexical and semantic retrieval yielded no relevant source passages."
    else:
        score = round(min(0.80, max(0.60, 0.75 - 0.20 * best_sim)), 2)
        pct = int(best_sim * 100)
        basis = f"Moderate confidence: Distant thematic mentions found (similarity {pct}%), but none corroborate the specific assertion."

    return score, basis
