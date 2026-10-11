import math
import re
import uuid
import datetime
from typing import List, Tuple, Dict, Any, Optional
from backend.models import Passage, EvidenceQuote, EvidenceRelationshipEnum
from backend.text_normalizer import (
    normalize_text, strip_footnote_markers, calculate_fuzzy_similarity,
    extract_named_entities_and_terms
)

STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he',
    'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were', 'will',
    'with', 'this', 'these', 'those', 'their', 'they', 'we', 'our', 'you', 'your'
}

def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text into alphanumeric words after stripping footnotes."""
    cleaned = strip_footnote_markers(text)
    return [w.lower() for w in re.findall(r'\b[a-zA-Z0-9_\$%\.]+\b', cleaned) if w.lower() not in STOPWORDS]

def extract_entities_and_numbers(text: str) -> List[str]:
    """Extract numbers, dates, currency symbols, and capitalized phrases."""
    return [item.lower() for item in extract_named_entities_and_terms(text)]

class BM25Retriever:
    """
    BM25 Evidence Retriever with exact/near-exact match prioritization
    and entity-focused ranking.
    """
    def __init__(self, passages: List[Passage], k1: float = 1.5, b: float = 0.75):
        self.passages = passages
        self.k1 = k1
        self.b = b
        self.doc_count = len(passages)
        self.doc_tokens: List[List[str]] = []
        self.doc_lengths: List[int] = []
        self.df: Dict[str, int] = {}
        self.avg_doc_len = 1.0

        self._index()

    def _index(self):
        total_len = 0
        for p in self.passages:
            tokens = tokenize(p.text)
            self.doc_tokens.append(tokens)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            unique_tokens = set(tokens)
            for t in unique_tokens:
                self.df[t] = self.df.get(t, 0) + 1

        if self.doc_count > 0:
            self.avg_doc_len = max(1.0, total_len / self.doc_count)

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[Passage, float]]:
        if not self.passages or not query.strip():
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        norm_query = normalize_text(query)
        query_entities = extract_entities_and_numbers(query)
        scores: List[float] = [0.0] * self.doc_count

        # 1. Exact or near-exact match priority sweep across all passages
        for i, p in enumerate(self.passages):
            norm_p = normalize_text(p.text)
            if norm_query in norm_p:
                scores[i] += 100.0  # Top priority
                continue
            
            # Check individual sentences in passage for >= 0.90 similarity
            raw_sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p.text) if s.strip()]
            for s in raw_sents:
                sim = calculate_fuzzy_similarity(query, s)
                if sim >= 0.90:
                    scores[i] += 90.0 * sim
                    break

        # 2. Standard BM25 scoring
        for q in query_tokens:
            doc_freq = self.df.get(q, 0)
            if doc_freq == 0:
                continue

            idf = math.log((self.doc_count - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
            
            for i in range(self.doc_count):
                tf = self.doc_tokens[i].count(q)
                if tf == 0:
                    continue
                doc_len = self.doc_lengths[i]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[i] += idf * (numerator / denominator)

        # 3. Entity, date and numerical matching bonus
        for i, p in enumerate(self.passages):
            p_lower = normalize_text(p.text)
            entity_matches = sum(1 for e in query_entities if e in p_lower)
            if entity_matches > 0:
                scores[i] += (entity_matches * 2.5)

        # Rank and filter
        scored_pairs = [(self.passages[i], scores[i]) for i in range(self.doc_count) if scores[i] > 0.05]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]

def find_best_sentence_quote(
    claim_text: str,
    passage: Passage,
    target_sentence: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Find the most relevant sentence inside the passage to serve as the quote,
    returning (quote_text, context_before, context_after).
    Guarantees quote_text is a VERBATIM substring of passage.text.
    """
    # If explicit target sentence provided and present in passage
    if target_sentence and target_sentence in passage.text:
        idx = passage.text.find(target_sentence)
        before = passage.text[max(0, idx - 80):idx].strip()
        after = passage.text[idx + len(target_sentence):min(len(passage.text), idx + len(target_sentence) + 80)].strip()
        return target_sentence, before, after

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', passage.text) if s.strip()]
    if not sentences:
        return passage.text, "", ""

    claim_tokens = set(tokenize(claim_text))
    claim_entities = set(extract_entities_and_numbers(claim_text))
    best_sent = sentences[0]
    best_score = -1.0

    for s in sentences:
        s_tokens = set(tokenize(s))
        s_lower = normalize_text(s)
        overlap = len(claim_tokens.intersection(s_tokens)) / max(len(claim_tokens), 1)
        sim = calculate_fuzzy_similarity(claim_text, s)
        ent_overlap = sum(1 for e in claim_entities if e in s_lower)

        # Weighted score prioritizes fuzzy similarity and entity matches
        score = (sim * 4.0) + (overlap * 2.0) + (ent_overlap * 1.5)
        if score > best_score:
            best_score = score
            best_sent = s

    # Ensure best_sent is a verbatim substring
    idx = passage.text.find(best_sent)
    if idx != -1:
        before = passage.text[max(0, idx - 80):idx].strip()
        after = passage.text[idx + len(best_sent):min(len(passage.text), idx + len(best_sent) + 80)].strip()
        return best_sent, before, after

    return passage.text, "", ""

def create_grounded_evidence_quote(
    passage: Passage,
    claim_text: str,
    similarity_score: float,
    relationship: EvidenceRelationshipEnum,
    target_sentence: Optional[str] = None,
    source_type: str = "uploaded_document",
    source_url: Optional[str] = None
) -> EvidenceQuote:
    """
    Construct a strictly grounded EvidenceQuote with complete source provenance
    and strict verbatim substring validation against the source passage.
    """
    quote_text, before_ctx, after_ctx = find_best_sentence_quote(claim_text, passage, target_sentence)
    
    # Deterministic verbatim check: quote_text MUST exist in passage.text
    is_verbatim = quote_text in passage.text
    
    # Normalize score between 0.0 and 1.0 for UI display
    norm_score = round(min(1.0, max(0.05, similarity_score if similarity_score <= 1.0 else (similarity_score / 3.0))), 3)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    is_contra = (relationship == EvidenceRelationshipEnum.CONTRADICTS)

    return EvidenceQuote(
        id=str(uuid.uuid4())[:8],
        source_id=passage.source_id,
        source_type=source_type,
        url=source_url,
        filename=passage.filename,
        page_number=passage.page_number,
        passage_id=passage.id,
        text=quote_text,
        similarity_score=norm_score,
        relationship=relationship,
        is_contradiction=is_contra,
        exact_match_verified=is_verbatim,
        retrieval_timestamp=now_iso,
        context_before=before_ctx,
        context_after=after_ctx,
        extraction_error=None if is_verbatim else "Quote could not be mapped to verbatim passage offset.",
        unit_label=getattr(passage, "unit_label", None),
        unit_type=getattr(passage, "unit_type", "body"),
        is_ocr=getattr(passage, "is_ocr", False) or (getattr(passage, "unit_type", None) == "figure_ocr")
    )
