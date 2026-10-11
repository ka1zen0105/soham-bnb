import re
import urllib.parse
import urllib.request
import json
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import ipaddress
import socket

def is_safe_url(url: str) -> bool:
    """
    Ensure URL is valid HTTP/HTTPS and not pointing to localhost, private IP,
    or internal cloud metadata endpoints.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return False
        # Resolve IP and check if private
        try:
            ip_str = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False

def extract_doi(query: str) -> Optional[str]:
    """Detect DOI patterns e.g. 10.1038/s41586-020-2649-2 or https://doi.org/10..."""
    m = re.search(r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', query)
    return m.group(1).rstrip('.') if m else None

def extract_arxiv_id(query: str) -> Optional[str]:
    """Detect arXiv ID e.g. 2303.08774, arXiv:2303.08774, or arxiv.org/abs/2303.08774"""
    m = re.search(r'(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)?([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+/[0-9]{7})', query, re.IGNORECASE)
    return m.group(1) if m else None

def fetch_doi_metadata(doi: str) -> Dict[str, Any]:
    """Fetch open-access paper metadata from Crossref."""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SecondOpinionAuditor/1.0 (mailto:audit@secondopinion.ai)"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    item = data.get("message", {})
    title = (item.get("title") or ["Untitled Paper"])[0]
    
    authors = []
    for a in item.get("author", []):
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)
    author_str = ", ".join(authors) if authors else "Unknown Authors"
    
    # Year
    year = "Unknown Year"
    created = item.get("published-print") or item.get("published-online") or item.get("created")
    if created and "date-parts" in created and created["date-parts"]:
        year = str(created["date-parts"][0][0])
    
    container = (item.get("container-title") or [""])[0]
    abstract = item.get("abstract") or ""
    # Strip JATS XML tags if present in abstract
    if abstract:
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()
    
    # References list if provided
    ref_list = []
    for ref in item.get("reference", []):
        ref_author = ref.get("author") or "Unknown"
        ref_year = ref.get("year") or ""
        ref_title = ref.get("article-title") or ref.get("journal-title") or ""
        ref_doi = ref.get("DOI") or ""
        ref_text = f"{ref_author} ({ref_year}). {ref_title} {ref_doi}".strip()
        if ref_text:
            ref_list.append(ref_text)
    
    units = []
    meta_text = f"Title: {title}\nAuthors: {author_str}\nYear: {year}\nJournal/Source: {container}\nDOI: {doi}"
    units.append({
        "index": 1,
        "label": "Paper Details",
        "text": meta_text,
        "unit_type": "body"
    })
    
    idx = 2
    if abstract:
        units.append({
            "index": idx,
            "label": "Abstract",
            "text": abstract,
            "unit_type": "body"
        })
        idx += 1
    
    if ref_list:
        for r_i, r in enumerate(ref_list[:30], 1):
            units.append({
                "index": idx,
                "label": f"Reference [{r_i}]",
                "text": r,
                "unit_type": "reference"
            })
            idx += 1
            
    warnings = []
    if not abstract:
        warnings.append("This paper appears paywalled; full abstract was not open-access on Crossref. Please upload the PDF if available.")
    else:
        warnings.append("Open-access paper details and abstract ingested. For complete document body, upload the full PDF.")

    return {
        "name": f"{title[:60].strip()} ({year}).doi",
        "type": "application/x-doi-citation",
        "units": units,
        "warnings": warnings,
        "meta": {
            "doi": doi,
            "title": title,
            "authors": author_str,
            "year": year
        }
    }

def fetch_arxiv_metadata(arxiv_id: str) -> Dict[str, Any]:
    """Fetch preprint from arXiv API."""
    url = f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SecondOpinionAuditor/1.0 (mailto:audit@secondopinion.ai)"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        xml_data = resp.read()
    
    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError(f"arXiv ID '{arxiv_id}' not found.")
        
    title_elem = entry.find("atom:title", ns)
    title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else "arXiv Preprint"
    
    summary_elem = entry.find("atom:summary", ns)
    summary = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""
    
    published_elem = entry.find("atom:published", ns)
    published = published_elem.text[:4] if published_elem is not None and published_elem.text else "Preprint"
    
    authors = []
    for a in entry.findall("atom:author", ns):
        n = a.find("atom:name", ns)
        if n is not None and n.text:
            authors.append(n.text.strip())
    author_str = ", ".join(authors) if authors else "Unknown Authors"
    
    units = [
        {
            "index": 1,
            "label": "arXiv Preprint Details",
            "text": f"Title: {title}\nAuthors: {author_str}\nYear: {published}\narXiv ID: {arxiv_id}",
            "unit_type": "body"
        }
    ]
    if summary:
        units.append({
            "index": 2,
            "label": "Abstract",
            "text": summary,
            "unit_type": "body"
        })
        
    return {
        "name": f"{title[:60].strip()} (arXiv {arxiv_id}).txt",
        "type": "text/plain",
        "units": units,
        "warnings": ["Ingested open-access arXiv preprint metadata and abstract."],
        "meta": {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": author_str,
            "year": published
        }
    }

def fetch_url_content(url: str) -> Dict[str, Any]:
    """Fetch open web document safely with strict timeouts and tag stripping."""
    if not is_safe_url(url):
        raise ValueError("URL is invalid or points to an internal/restricted address.")
        
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SecondOpinionAuditor/1.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        content_type = resp.headers.get_content_type()
        raw_bytes = resp.read(5 * 1024 * 1024) # Cap 5 MB
        
    html = raw_bytes.decode("utf-8", errors="replace")
    
    # Strip script and style
    html = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', html)
    # Extract title
    title_match = re.search(r'(?i)<title[^>]*>(.*?)</title>', html)
    title = title_match.group(1).strip() if title_match else url
    
    # Replace paragraphs and headings with newlines
    html = re.sub(r'(?i)<(p|div|h[1-6]|li|br)[^>]*>', '\n', html)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'[ \t]+', ' ', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    cleaned_text = "\n\n".join(lines)
    
    paragraphs = [p for p in re.split(r'\n\s*\n', cleaned_text) if p.strip()]
    units = []
    for idx, p in enumerate(paragraphs[:50], 1):
        units.append({
            "index": idx,
            "label": f"Section {idx}",
            "text": p,
            "unit_type": "body"
        })
        
    if not units:
        units.append({
            "index": 1,
            "label": "Web Page Content",
            "text": cleaned_text[:2000] or "[No readable text found on page]",
            "unit_type": "body"
        })
        
    return {
        "name": f"{title[:50].strip() or 'Web_Source'}.html",
        "type": "text/html",
        "units": units,
        "warnings": [],
        "meta": {"url": url, "title": title}
    }

def fetch_paper_from_query(query: str) -> Dict[str, Any]:
    """
    Universal resolver for DOI, arXiv, and web URLs.
    """
    clean = query.strip()
    if not clean:
        raise ValueError("Query string cannot be empty.")
        
    # 1. DOI
    doi = extract_doi(clean)
    if doi:
        try:
            return fetch_doi_metadata(doi)
        except Exception as e:
            raise RuntimeError(f"Could not retrieve DOI '{doi}' via Crossref API: {str(e)}")
            
    # 2. arXiv
    arxiv_id = extract_arxiv_id(clean)
    if arxiv_id:
        try:
            return fetch_arxiv_metadata(arxiv_id)
        except Exception as e:
            raise RuntimeError(f"Could not retrieve arXiv preprint '{arxiv_id}': {str(e)}")
            
    # 3. HTTP URL
    if clean.startswith("http://") or clean.startswith("https://"):
        try:
            return fetch_url_content(clean)
        except Exception as e:
            raise RuntimeError(f"Could not fetch URL '{clean}': {str(e)}")
            
    raise ValueError(f"Unrecognized query '{clean}'. Please enter a valid DOI (e.g. 10.1038/...), arXiv ID (e.g. 2303.08774), or URL.")
