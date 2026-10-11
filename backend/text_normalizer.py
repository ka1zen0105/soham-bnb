import re
import os
import hashlib
import unicodedata
import difflib
from typing import List, Tuple, Optional, Any, Dict, Set

STOP = set(
    "a an the of in on at to for from by with and or but is was were be been being as that this "
    "these those it its he she his her they their than then also which who whom into onto over under "
    "after before while during about against between".split()
)
MARK = re.compile(r"\[[^\]]*\]")  # footnote markers such as [note 1], [a], [8], [citation needed]
TOK = re.compile(r"[A-Za-zÀ-ɏ]+|\d+(?:[.,]\d+)*")
BOUND = re.compile(r'(?<=[.!?])(?<!\s[A-Z]\.)(?:\[[^\]]*\])*\s+(?=["\'(\[]?[A-Z0-9])')

# Footnote markers fallback pattern
FOOTNOTE_PATTERN = MARK

# Suffixes added when duplicating or saving files
FILE_COPY_SUFFIX_PATTERN = re.compile(r'(?:\s*\(\d+\)|\s*-\s*copy(?:\s*\d+)?|_\d+)$', re.IGNORECASE)

def strip_footnote_markers(text: str) -> str:
    """Strip Wikipedia/academic footnote markers such as [note 1], [a], [8], [citation needed] and artifacts."""
    if not text:
        return ""
    t = MARK.sub("", text)
    t = re.sub(r"\(\s*listen\b[^)]*\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[ⓘℹ]", "", t)
    return t

def norm(text: str) -> str:
    """
    Normalise text according to reference verification engine:
    1. Unicode NFKC normalisation
    2. Straight quotes (' and ") and ASCII dashes (-)
    3. Strip footnote markers [note 1], [a], [8]
    4. Strip artifacts like '(listen ⓘ)', audio buttons, and symbols
    5. Collapse whitespace
    6. Remove space before punctuation (e.g. 'Empire ,' -> 'Empire,')
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"').replace("`", "'")
    t = re.sub(r"[‐-―−–—]", "-", t)
    t = MARK.sub("", t)
    t = re.sub(r"\(\s*listen\b[^)]*\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[ⓘℹ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", t)

def normalize_text(text: str) -> str:
    """Convenience lowercase wrapper around norm()."""
    return norm(text).lower()

def tokens(text: str) -> Tuple[List[str], List[str]]:
    """Extract raw tokens and lowercase tokens."""
    raw = TOK.findall(norm(text))
    return raw, [w.lower() for w in raw]

def sentences(paragraph: str) -> List[str]:
    """Split a paragraph into distinct sentences respecting abbreviations and footnotes."""
    out, start = [], 0
    for m in BOUND.finditer(paragraph):
        out.append(paragraph[start : m.end()].strip())
        start = m.end()
    out.append(paragraph[start:].strip())
    return [s for s in out if s]

def key_tokens(claim: str) -> Set[str]:
    """Years, numbers and proper nouns (capitalised words that do not start a sentence)."""
    n = norm(claim)
    keys = {m.group().lower() for m in re.finditer(r"\d+(?:[.,]\d+)*", n)}
    for m in re.finditer(r"[A-Za-zÀ-ɏ]+", n):
        before = n[: m.start()].rstrip()
        if m.group()[0].isupper() and before and before[-1] not in '.!?"':
            keys.add(m.group().lower())
    return keys

def dedupe(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Treat documents with identical content as one (e.g. 'a.txt' and 'a (2).txt')."""
    seen, out = {}, []
    for d in docs:
        h = hashlib.sha1(norm(d["text"]).lower().encode()).hexdigest()
        if h in seen:
            seen[h].setdefault("aliases", []).append(d["name"])
        else:
            d_copy = dict(d)
            d_copy["id"] = d.get("id") or h[:8]
            d_copy["aliases"] = []
            seen[h] = d_copy
            out.append(d_copy)
    return out

def normalize_filename(filename: str) -> str:
    """
    De-duplicate filenames by stripping copy suffixes like ' (2)', ' - Copy', '_1'.
    Returns clean lowercase base filename.
    """
    if not filename:
        return "unnamed"
    base = os.path.basename(filename).strip()
    name, ext = os.path.splitext(base)
    clean_name = FILE_COPY_SUFFIX_PATTERN.sub('', name).strip()
    return f"{clean_name}{ext}".lower()

def get_canonical_doc_key(doc: Any) -> str:
    """
    Compute a fingerprint for document de-duplication:
    Documents with identical text content hash, or identical normalized name + content,
    are treated as the exact same document.
    """
    text = getattr(doc, 'extracted_text', None) or ""
    filename = getattr(doc, 'filename', None) or ""
    clean_text = normalize_text(text)
    if clean_text:
        content_hash = hashlib.sha1(clean_text.encode('utf-8')).hexdigest()[:16]
        return f"hash:{content_hash}"
    return f"file:{normalize_filename(filename)}"

def calculate_fuzzy_similarity(text1: str, text2: str) -> float:
    """Calculate normalized SequenceMatcher ratio between two strings."""
    n1 = normalize_text(text1)
    n2 = normalize_text(text2)
    if not n1 and not n2:
        return 1.0
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()

def extract_named_entities_and_terms(text: str) -> List[str]:
    """
    Extract proper nouns, multi-word capitalized phrases, quantities, and dates.
    """
    cleaned = strip_footnote_markers(text)
    caps = re.findall(r'\b[A-Z][a-z]+(?:\s+(?:of|the|and|de|von|van|part|in)\s+[A-Z][a-z]+|\s+[A-Z][a-z]+)*\b', cleaned)
    nums = re.findall(r'\$?\b\d+[\d,]*\.?\d*%?', cleaned)
    return [c.strip() for c in (caps + nums) if len(c.strip()) > 1]

def find_sentence_factual_discrepancy(
    claim_text: str,
    source_sentence: str,
    min_similarity: float = 0.65
) -> Optional[Tuple[str, str, str]]:
    """
    Compare a claim against a highly-aligned candidate source sentence.
    If the sentence is structurally and contextually aligned (similarity >= min_similarity)
    but differs on a key fact (e.g. claim says 'England', source says 'Switzerland'),
    returns (claim_value, source_value, detail_explanation).
    """
    norm_c = normalize_text(claim_text)
    norm_s = normalize_text(source_sentence)
    
    if not norm_c or not norm_s:
        return None
    
    if norm_c == norm_s or norm_c.rstrip('.,;:!? ') in norm_s:
        return None  # Exact match or verbatim substring, no discrepancy

    ratio = difflib.SequenceMatcher(None, norm_c, norm_s).ratio()
    if ratio < min_similarity:
        return None  # Not aligned enough to claim a factual replacement

    words_c = [re.sub(r'^[^\w$%]+|[^\w$%]+$', '', w) for w in norm_c.split()]
    words_c = [w for w in words_c if w]
    words_s = [re.sub(r'^[^\w$%]+|[^\w$%]+$', '', w) for w in norm_s.split()]
    words_s = [w for w in words_s if w]

    if words_c == words_s:
        return None

    matcher = difflib.SequenceMatcher(None, words_c, words_s)
    
    replaces = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            c_frag = " ".join(words_c[i1:i2])
            s_frag = " ".join(words_s[j1:j2])
            replaces.append((c_frag, s_frag))
        elif tag in ('delete', 'insert'):
            pass

    if len(replaces) == 1:
        c_val, s_val = replaces[0]
        trivial = {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of'}
        if c_val in trivial and s_val in trivial:
            return None
        
        c_raw = _find_cased_token(claim_text, c_val)
        s_raw = _find_cased_token(source_sentence, s_val)
        detail = f"Claim asserts '{c_raw}', but source documents '{s_raw}'."
        return c_raw, s_raw, detail

    if len(replaces) > 1 and ratio >= 0.75:
        discrepancies = []
        for c_frag, s_frag in replaces:
            c_raw = _find_cased_token(claim_text, c_frag)
            s_raw = _find_cased_token(source_sentence, s_frag)
            discrepancies.append(f"Claim asserts '{c_raw}', but source documents '{s_raw}'")
        detail = "; ".join(discrepancies) + "."
        return replaces[0][0], replaces[0][1], detail

    return None

def _find_cased_token(original_text: str, lower_token: str) -> str:
    """Find original cased representation of a lowercased token from source text."""
    pattern = re.compile(re.escape(lower_token), re.IGNORECASE)
    m = pattern.search(original_text)
    if m:
        return m.group(0).strip()
    return lower_token.capitalize()
