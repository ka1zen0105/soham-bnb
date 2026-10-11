import os
import re
import uuid
import json
import csv
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple

from backend.models import SourceDocument, Passage
from backend.text_normalizer import sentences

INJECTION_PATTERNS = [
    re.compile(r'(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b'),
    re.compile(r'(?i)\b(system\s*prompt|you\s+are\s+now|disregard\s+all\s+prior)\b'),
    re.compile(r'(?i)\[/?(inst|sys|system)\]'),
    re.compile(r'(?i)<<sys>>.*?</<sys>>', re.DOTALL),
    re.compile(r'(?i)\b(output\s+only\s+"?true"?|mark\s+this\s+claim\s+as\s+supported)\b'),
]

MAX_EXTRACTED_TEXT_BYTES = 5 * 1024 * 1024  # Cap extracted text at 5 MB

def sanitize_source_text(text: str) -> str:
    """
    Remove or neutralize prompt injection sequences to ensure source content
    is strictly evaluated as raw reference data, not system instructions.
    """
    if not text:
        return ""
    # Normalize unicode and whitespace
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Filter out excessive control characters
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    # Neutralize prompt injection attempts
    for pat in INJECTION_PATTERNS:
        text = pat.sub('[FILTERED_INSTRUCTION]', text)
    return text

def chunk_text_into_passages(
    source_id: str,
    filename: str,
    full_text: str,
    page_number: int = 1,
    unit_label: Optional[str] = None,
    unit_type: Optional[str] = "body",
    is_ocr: bool = False
) -> List[Passage]:
    """
    Build candidate passages from single sentences and adjacent sentence pairs
    (never treat a whole multi-sentence file as one passage and never default to the first passage).
    Attaches unit labels (e.g. 'Page 5', 'Slide 7', 'Sheet Q3 row 12') and unit types.
    """
    passages: List[Passage] = []
    if not full_text or not full_text.strip():
        return passages

    paragraphs = [p for p in re.split(r'\n\s*\n', full_text) if p.strip()]
    passage_num = 1

    for pi, para in enumerate(paragraphs, 1):
        cleaned_para = para.strip()
        if not cleaned_para:
            continue
        
        sents = sentences(cleaned_para.replace("\n", " "))
        if not sents:
            sents = [cleaned_para]

        label = unit_label or (f"Page {page_number}" if page_number > 1 else f"Paragraph {pi}")

        # Single sentences
        for si, s in enumerate(sents, 1):
            c_start = full_text.find(s)
            c_end = c_start + len(s) if c_start != -1 else 0
            passages.append(Passage(
                id=f"{source_id}_p{page_number}_{pi}_{si}",
                source_id=source_id,
                filename=filename,
                page_number=page_number,
                passage_number=passage_num,
                text=s,
                char_start=max(0, c_start),
                char_end=max(0, c_end),
                unit_index=page_number,
                unit_label=label,
                unit_type=unit_type or "body",
                is_ocr=is_ocr
            ))
            passage_num += 1

        # Adjacent sentence pairs (for multi-sentence claims)
        for si in range(len(sents) - 1):
            combined_s = sents[si] + " " + sents[si + 1]
            c_start = full_text.find(sents[si])
            c_end = c_start + len(combined_s) if c_start != -1 else 0
            passages.append(Passage(
                id=f"{source_id}_p{page_number}_{pi}_{si + 1}-{si + 2}",
                source_id=source_id,
                filename=filename,
                page_number=page_number,
                passage_number=passage_num,
                text=combined_s,
                char_start=max(0, c_start),
                char_end=max(0, c_end),
                unit_index=page_number,
                unit_label=label,
                unit_type=unit_type or "body",
                is_ocr=is_ocr
            ))
            passage_num += 1

    return passages

# =========================================================================
# FILE TYPE SNIFFER (MAGIC BYTES + EXTENSION)
# =========================================================================

def detect_file_format(file_path: str, filename: str) -> str:
    """
    Detect format by checking magic bytes and file extension fallback.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    header = b""
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as f:
                header = f.read(4096)
        except Exception:
            pass

    # 1. Magic bytes
    if header.startswith(b"%PDF"):
        return "pdf"
    if header.startswith(b"PK\x03\x04"):
        # Inspect zip contents to differentiate docx, pptx, xlsx, odt, odp, epub, zip
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                names = set(z.namelist())
                if any(n.startswith("word/") for n in names) or "word/document.xml" in names:
                    return "docx"
                if any(n.startswith("ppt/") for n in names) or "ppt/presentation.xml" in names:
                    return "pptx"
                if any(n.startswith("xl/") for n in names) or "xl/workbook.xml" in names:
                    return "xlsx"
                if "mimetype" in names:
                    try:
                        mime_val = z.read("mimetype").decode("utf-8", errors="ignore").strip()
                        if "opendocument.text" in mime_val:
                            return "odt"
                        if "opendocument.presentation" in mime_val:
                            return "odp"
                        if "epub" in mime_val:
                            return "epub"
                    except Exception:
                        pass
                if "META-INF/container.xml" in names:
                    return "epub"
                return "zip"
        except Exception:
            if ext in [".docx", ".pptx", ".xlsx", ".odt", ".odp", ".epub"]:
                return ext.lstrip(".")
            return "zip"

    if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"): # OLE CFB
        if ext in [".ppt"]:
            return "ppt"
        if ext in [".xls"]:
            return "xls"
        return "doc"

    if header.startswith(b"{\\rtf"):
        return "rtf"

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"

    if header.startswith(b"RIFF") and b"WEBP" in header[:16]:
        return "webp"

    # 2. Text heuristics
    try:
        sample_str = header.decode("utf-8", errors="ignore").strip()
        if sample_str.startswith("<!DOCTYPE html") or "<html" in sample_str.lower():
            return "html"
        if re.search(r'@(?:article|book|misc|inproceedings|techreport|phdthesis)\s*\{', sample_str, re.IGNORECASE):
            return "bib"
        if sample_str.startswith("TY  - ") or "\nTY  - " in sample_str:
            return "ris"
        if "\\documentclass" in sample_str or "\\begin{document}" in sample_str:
            return "tex"
    except Exception:
        pass

    # 3. Extension fallback
    ext_clean = ext.lstrip(".")
    if ext_clean in [
        "pdf", "docx", "doc", "rtf", "odt", "txt", "md", "html", "htm",
        "pptx", "ppt", "odp", "json", "jsonl", "csv", "tsv", "xlsx", "xls",
        "xml", "yaml", "yml", "bib", "ris", "tex", "epub", "png", "jpg", "jpeg", "webp", "zip"
    ]:
        if ext_clean in ["htm"]:
            return "html"
        if ext_clean in ["jpeg"]:
            return "jpg"
        if ext_clean in ["yml"]:
            return "yaml"
        return ext_clean

    return "txt"

# =========================================================================
# RECURSIVE DATA FLATTENING (JSON, YAML, XML)
# =========================================================================

def flatten_json_object(obj: Any, parent_path: str = "") -> List[Tuple[str, str]]:
    """
    Recursively flatten JSON into readable ('path', 'path: value') pairs.
    """
    items: List[Tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            curr = f"{parent_path}.{k}" if parent_path else str(k)
            if isinstance(v, (dict, list)):
                items.extend(flatten_json_object(v, curr))
            else:
                items.append((curr, f"{curr}: {v}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            curr = f"{parent_path}[{idx}]"
            if isinstance(item, (dict, list)):
                items.extend(flatten_json_object(item, curr))
            else:
                items.append((curr, f"{curr}: {item}"))
    else:
        items.append((parent_path or "root", f"{parent_path or 'root'}: {obj}"))
    return items

def flatten_xml_element(elem: ET.Element, parent_path: str = "") -> List[Tuple[str, str]]:
    """
    Recursively flatten XML into ('XPath', 'tag: text') pairs.
    """
    items: List[Tuple[str, str]] = []
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
    curr_path = f"{parent_path}/{tag}" if parent_path else f"/{tag}"
    text = (elem.text or "").strip()
    if text:
        items.append((curr_path, f"{curr_path}: {text}"))
    for child in elem:
        items.extend(flatten_xml_element(child, curr_path))
    return items

# =========================================================================
# INDIVIDUAL PARSERS RETURNING NORMALIZED UNITS
# Output schema: { name, type, units: [{ index, label, text, unit_type, is_ocr }], meta, warnings }
# =========================================================================

def parse_pdf(file_path: str, filename: str) -> Dict[str, Any]:
    units = []
    warnings = []
    skipped_image_pages = 0
    total_pages = 1

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        total_pages = len(doc)
        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_num = page_idx + 1
            # Extract clean text, ignoring embedded image raw streams
            text = page.get_text("text").strip()
            image_list = page.get_images()

            if text:
                sanitized = sanitize_source_text(text)
                units.append({
                    "index": page_num,
                    "label": f"Page {page_num}",
                    "text": sanitized,
                    "unit_type": "body",
                    "is_ocr": False
                })
            else:
                # Page contains little or no text
                if image_list:
                    skipped_image_pages += 1
                    # Record page-specific skipped warning
                    warnings.append(f"Page {page_num} is image-only and was skipped")
        doc.close()
    except ImportError:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        total_pages = len(reader.pages)
        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = reader.pages[page_idx]
            text = (page.extract_text() or "").strip()
            if text:
                sanitized = sanitize_source_text(text)
                units.append({
                    "index": page_num,
                    "label": f"Page {page_num}",
                    "text": sanitized,
                    "unit_type": "body",
                    "is_ocr": False
                })
            else:
                skipped_image_pages += 1
                warnings.append(f"Page {page_num} is image-only and was skipped")

    if skipped_image_pages > 0:
        summary_msg = f"{skipped_image_pages} page{'s are' if skipped_image_pages > 1 else ' is'} image-only and skipped"
        if summary_msg not in warnings:
            warnings.insert(0, summary_msg)

    # Check for cited references section inside PDF text
    ref_units = []
    for u in units:
        ref_match = re.search(r'(?i)\n\s*(?:References|Bibliography|Works Cited)\s*\n(.*)', u["text"], re.DOTALL)
        if ref_match:
            ref_body = ref_match.group(1).strip()
            ref_entries = [r.strip() for r in re.split(r'\n(?=\[\d+\]|\d+\.|\b[A-Z][a-zA-Z]+,?\s+(?:et al\.|\d{4}))', ref_body) if r.strip()]
            for r_idx, r_text in enumerate(ref_entries[:40], 1):
                ref_units.append({
                    "index": u["index"],
                    "label": f"References (Page {u['index']})",
                    "text": r_text,
                    "unit_type": "reference",
                    "is_ocr": False
                })

    units.extend(ref_units)

    if not units:
        # Document had only image pages or empty
        units.append({
            "index": 1,
            "label": "Page 1",
            "text": "[Scanned / Image-only PDF: No extractable machine-readable text was detected.]",
            "unit_type": "body",
            "is_ocr": False
        })

    return {
        "name": filename,
        "type": "application/pdf",
        "units": units,
        "meta": {"total_pages": total_pages, "skipped_image_pages": skipped_image_pages},
        "warnings": warnings
    }

def parse_pptx(file_path: str, filename: str) -> Dict[str, Any]:
    units = []
    warnings = []
    slide_count = 0

    if not zipfile.is_zipfile(file_path):
        raise ValueError(f"File '{filename}' is not a valid PowerPoint (.pptx) zip archive.")

    # Try python-pptx first
    try:
        import pptx
        prs = pptx.Presentation(file_path)
        slide_count = len(prs.slides)

        for s_idx, slide in enumerate(prs.slides):
            slide_num = s_idx + 1
            text_blocks: List[str] = []

            # 1. Slide shapes & titles
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text.strip():
                    text_blocks.append(shape.text.strip())
                elif shape.has_table:
                    # Table extraction
                    table_rows = []
                    for row in shape.table.rows:
                        row_vals = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_vals:
                            table_rows.append(" | ".join(row_vals))
                    if table_rows:
                        text_blocks.append("Table:\n" + "\n".join(table_rows))
                
                # Alt text if present
                try:
                    alt_desc = shape._element.nvSpPr.cNvPr.get('descr')
                    if alt_desc and alt_desc.strip():
                        text_blocks.append(f"Figure alt-text: {alt_desc.strip()}")
                except Exception:
                    pass

                # Chart title if present
                try:
                    if shape.has_chart and shape.chart.has_title:
                        c_title = shape.chart.chart_title.text_frame.text
                        if c_title and c_title.strip():
                            text_blocks.append(f"Chart: {c_title.strip()}")
                except Exception:
                    pass

            # 2. Speaker notes
            try:
                if slide.has_notes_slide:
                    notes_frame = slide.notes_slide.notes_text_frame
                    if notes_frame and notes_frame.text.strip():
                        text_blocks.append(f"Speaker notes: {notes_frame.text.strip()}")
            except Exception:
                pass

            combined = "\n\n".join(text_blocks).strip()
            if combined:
                units.append({
                    "index": slide_num,
                    "label": f"Slide {slide_num}",
                    "text": sanitize_source_text(combined),
                    "unit_type": "body",
                    "is_ocr": False
                })
            else:
                units.append({
                    "index": slide_num,
                    "label": f"Slide {slide_num}",
                    "text": "[Empty or Graphic Slide]",
                    "unit_type": "body",
                    "is_ocr": False
                })

    except Exception:
        # Fallback to direct XML parsing via zipfile
        with zipfile.ZipFile(file_path, "r") as z:
            slide_entries = [n for n in z.namelist() if re.match(r'^ppt/slides/slide\d+\.xml$', n)]
            slide_entries.sort(key=lambda n: int(re.search(r'slide(\d+)\.xml$', n).group(1)))
            slide_count = max(1, len(slide_entries))

            if not slide_entries:
                raise ValueError(f"No slide XML structures found inside presentation '{filename}'.")

            for s_idx, s_entry in enumerate(slide_entries):
                slide_num = s_idx + 1
                xml_data = z.read(s_entry).decode("utf-8", errors="replace")
                text_runs = re.findall(r'<(?:\w+:)?t[^>]*>(.*?)</(?:\w+:)?t>', xml_data, flags=re.DOTALL)
                clean_runs = [re.sub(r'<[^>]+>', '', t).strip() for t in text_runs if t.strip()]
                
                # Check for notes slide
                notes_entry = f"ppt/notesSlides/notesSlide{slide_num}.xml"
                if notes_entry in z.namelist():
                    n_data = z.read(notes_entry).decode("utf-8", errors="replace")
                    n_runs = re.findall(r'<(?:\w+:)?t[^>]*>(.*?)</(?:\w+:)?t>', n_data, flags=re.DOTALL)
                    clean_n = [re.sub(r'<[^>]+>', '', t).strip() for t in n_runs if t.strip()]
                    if clean_n:
                        clean_runs.append("Speaker notes: " + " ".join(clean_n))

                slide_text = " ".join(clean_runs)
                units.append({
                    "index": slide_num,
                    "label": f"Slide {slide_num}",
                    "text": sanitize_source_text(slide_text) or "[Empty Slide]",
                    "unit_type": "body",
                    "is_ocr": False
                })

    return {
        "name": filename,
        "type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "units": units,
        "meta": {"slide_count": slide_count},
        "warnings": warnings
    }

def extract_pptx_slides(file_path: str, source_id: str, original_filename: str, size_bytes: int = 0) -> SourceDocument:
    """
    Extract slides and text from a Microsoft PowerPoint presentation (.pptx).
    """
    try:
        norm_doc = parse_pptx(file_path, original_filename)
        return create_source_document_from_units(
            source_id=source_id,
            name=original_filename,
            file_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            units=norm_doc["units"],
            warnings=norm_doc.get("warnings", []),
            meta=norm_doc.get("meta", {}),
            size_bytes=size_bytes
        )
    except Exception as e:
        raise RuntimeError(f"Failed to extract PowerPoint (.pptx) '{original_filename}': {str(e)}")

def parse_docx(file_path: str, filename: str) -> Dict[str, Any]:
    units = []
    warnings = []
    
    try:
        import docx
        doc = docx.Document(file_path)
        
        current_section = "Introduction"
        current_paras: List[str] = []
        unit_idx = 1

        for p in doc.paragraphs:
            txt = p.text.strip()
            if not txt:
                continue
            if p.style and p.style.name and p.style.name.lower().startswith("heading"):
                if current_paras:
                    units.append({
                        "index": unit_idx,
                        "label": f"Section: {current_section}",
                        "text": sanitize_source_text("\n\n".join(current_paras)),
                        "unit_type": "reference" if "reference" in current_section.lower() else "body",
                        "is_ocr": False
                    })
                    unit_idx += 1
                    current_paras = []
                current_section = txt
            else:
                current_paras.append(txt)

        if current_paras:
            units.append({
                "index": unit_idx,
                "label": f"Section: {current_section}",
                "text": sanitize_source_text("\n\n".join(current_paras)),
                "unit_type": "reference" if "reference" in current_section.lower() else "body",
                "is_ocr": False
            })
            unit_idx += 1

        # Tables
        for t_idx, table in enumerate(doc.tables, 1):
            table_lines = []
            for row in table.rows:
                row_vals = [c.text.strip() for c in row.cells if c.text.strip()]
                if row_vals:
                    table_lines.append(" | ".join(row_vals))
            if table_lines:
                units.append({
                    "index": unit_idx,
                    "label": f"Table {t_idx}",
                    "text": sanitize_source_text("\n".join(table_lines)),
                    "unit_type": "table",
                    "is_ocr": False
                })
                unit_idx += 1

    except Exception as e:
        warnings.append(f"Standard docx extraction encountered: {str(e)}")

    if not units:
        units.append({
            "index": 1,
            "label": "Document Body",
            "text": "[Empty Word Document]",
            "unit_type": "body",
            "is_ocr": False
        })

    return {
        "name": filename,
        "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "units": units,
        "meta": {"unit_count": len(units)},
        "warnings": warnings
    }

def parse_xlsx(file_path: str, filename: str) -> Dict[str, Any]:
    """
    Parse Excel (.xlsx/.xls) spreadsheets into readable row-level units:
    'Sheet {sheet} row {row}' with exact 'column: value' pairs.
    """
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True)
    units = []
    warnings = []
    unit_idx = 1

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        headers: List[str] = []
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue

        # Detect headers from row 1
        first_row = rows[0]
        headers = [str(c).strip() if c is not None else f"Col{ci+1}" for ci, c in enumerate(first_row)]

        for r_idx, row in enumerate(rows[1:], 2):
            cell_pairs = []
            for c_idx, val in enumerate(row):
                if val is not None and str(val).strip():
                    col_name = headers[c_idx] if c_idx < len(headers) else f"Col{c_idx+1}"
                    cell_pairs.append(f"{col_name}: {val}")
            
            if cell_pairs:
                row_text = ", ".join(cell_pairs)
                units.append({
                    "index": unit_idx,
                    "label": f"Sheet '{sheet_name}' row {r_idx}",
                    "text": sanitize_source_text(row_text),
                    "unit_type": "table",
                    "is_ocr": False
                })
                unit_idx += 1

    wb.close()
    if not units:
        units.append({
            "index": 1,
            "label": "Sheet 'Sheet1' row 1",
            "text": "[Empty Spreadsheet]",
            "unit_type": "table",
            "is_ocr": False
        })

    return {
        "name": filename,
        "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "units": units,
        "meta": {"sheet_count": len(wb.sheetnames), "row_count": len(units)},
        "warnings": warnings
    }

def parse_csv(content: str, filename: str, delimiter: str = ",") -> Dict[str, Any]:
    units = []
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return {"name": filename, "type": "text/csv", "units": [], "meta": {}, "warnings": []}

    headers = [h.strip() or f"Col{i+1}" for i, h in enumerate(rows[0])]
    unit_idx = 1

    for r_idx, row in enumerate(rows[1:], 2):
        if not any(c.strip() for c in row):
            continue
        cell_pairs = []
        for c_idx, val in enumerate(row):
            if val.strip():
                col_name = headers[c_idx] if c_idx < len(headers) else f"Col{c_idx+1}"
                cell_pairs.append(f"{col_name}: {val.strip()}")
        if cell_pairs:
            units.append({
                "index": unit_idx,
                "label": f"Row {r_idx}",
                "text": sanitize_source_text(", ".join(cell_pairs)),
                "unit_type": "table",
                "is_ocr": False
            })
            unit_idx += 1

    return {
        "name": filename,
        "type": "text/csv" if delimiter == "," else "text/tab-separated-values",
        "units": units,
        "meta": {"row_count": len(units)},
        "warnings": []
    }

def parse_json(content: str, filename: str) -> Dict[str, Any]:
    units = []
    data = json.loads(content)
    pairs = flatten_json_object(data)
    
    # Group pairs by top-level or chunk for efficient passage retrieval
    unit_idx = 1
    for p_path, p_line in pairs:
        units.append({
            "index": unit_idx,
            "label": f"Path {p_path}",
            "text": sanitize_source_text(p_line),
            "unit_type": "json_path",
            "is_ocr": False
        })
        unit_idx += 1

    return {
        "name": filename,
        "type": "application/json",
        "units": units,
        "meta": {"field_count": len(units)},
        "warnings": []
    }

def parse_bibtex(content: str, filename: str) -> Dict[str, Any]:
    units = []
    entries = re.findall(r'@(\w+)\s*\{\s*([^,]+),\s*(.*?)\n\}', content, re.DOTALL)
    unit_idx = 1
    for entry_type, cite_key, fields_str in entries:
        fields: Dict[str, str] = {}
        for f_match in re.finditer(r'(\w+)\s*=\s*(?:\{([^{}]*)\}|"([^"]*)"|([^,\n]+))', fields_str, re.DOTALL):
            k = f_match.group(1).lower()
            v = f_match.group(2) or f_match.group(3) or f_match.group(4) or ""
            fields[k] = v.strip().replace("\n", " ")

        author = fields.get("author", "Unknown Author")
        year = fields.get("year", "Unknown Year")
        title = fields.get("title", cite_key)
        journal = fields.get("journal") or fields.get("booktitle") or ""
        doi = fields.get("doi") or ""

        entry_text = f"{author} ({year}). {title}. {journal} {doi}".strip()
        units.append({
            "index": unit_idx,
            "label": f"Reference [{cite_key}]",
            "text": sanitize_source_text(entry_text),
            "unit_type": "reference",
            "is_ocr": False
        })
        unit_idx += 1

    return {
        "name": filename,
        "type": "text/x-bibtex",
        "units": units,
        "meta": {"reference_count": len(units)},
        "warnings": []
    }

def parse_ris(content: str, filename: str) -> Dict[str, Any]:
    units = []
    records = [r.strip() for r in re.split(r'\nER\s*-\s*', content) if r.strip()]
    unit_idx = 1
    for rec in records:
        lines = rec.splitlines()
        fields: Dict[str, List[str]] = {}
        for line in lines:
            m = re.match(r'^([A-Z0-9]{2})\s*-\s*(.*)', line)
            if m:
                tag, val = m.group(1), m.group(2).strip()
                fields.setdefault(tag, []).append(val)
        
        authors = ", ".join(fields.get("AU", fields.get("A1", ["Unknown"])))
        title = " ".join(fields.get("TI", fields.get("T1", ["Untitled"])))
        year = " ".join(fields.get("PY", fields.get("Y1", ["Year"])))
        doi = " ".join(fields.get("DO", []))
        rec_id = " ".join(fields.get("ID", [f"Ref_{unit_idx}"]))

        entry_text = f"[{rec_id}] {authors} ({year}). {title}. {doi}".strip()
        units.append({
            "index": unit_idx,
            "label": f"Reference [{rec_id}]",
            "text": sanitize_source_text(entry_text),
            "unit_type": "reference",
            "is_ocr": False
        })
        unit_idx += 1

    return {
        "name": filename,
        "type": "application/x-research-info-systems",
        "units": units,
        "meta": {"record_count": len(units)},
        "warnings": []
    }

def parse_html_string(html_content: str, filename: str) -> Dict[str, Any]:
    clean_html = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', html_content)
    clean_html = re.sub(r'(?i)<(p|div|h[1-6]|li|br)[^>]*>', '\n', clean_html)
    raw_text = re.sub(r'<[^>]+>', ' ', clean_html)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', raw_text) if p.strip()]
    units = []
    for idx, p in enumerate(paragraphs, 1):
        units.append({
            "index": idx,
            "label": f"Section {idx}",
            "text": sanitize_source_text(p),
            "unit_type": "body",
            "is_ocr": False
        })
    return {
        "name": filename,
        "type": "text/html",
        "units": units,
        "meta": {"section_count": len(units)},
        "warnings": []
    }

def parse_odt_odp(file_path: str, filename: str, is_presentation: bool = False) -> Dict[str, Any]:
    units = []
    with zipfile.ZipFile(file_path, "r") as z:
        xml_content = z.read("content.xml").decode("utf-8", errors="replace")
        root = ET.fromstring(xml_content)
        
        if is_presentation:
            pages = root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}page")
            for p_idx, page in enumerate(pages, 1):
                page_texts = [elem.text.strip() for elem in page.iter() if elem.text and elem.text.strip()]
                units.append({
                    "index": p_idx,
                    "label": f"Slide {p_idx}",
                    "text": sanitize_source_text(" ".join(page_texts)),
                    "unit_type": "body",
                    "is_ocr": False
                })
        else:
            p_elems = root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p")
            text_chunks = [elem.text.strip() for elem in p_elems if elem.text and elem.text.strip()]
            units.append({
                "index": 1,
                "label": "Document Body",
                "text": sanitize_source_text("\n\n".join(text_chunks)),
                "unit_type": "body",
                "is_ocr": False
            })

    return {
        "name": filename,
        "type": "application/vnd.oasis.opendocument.presentation" if is_presentation else "application/vnd.oasis.opendocument.text",
        "units": units,
        "meta": {},
        "warnings": []
    }

def parse_rtf(file_path: str, filename: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # Strip RTF controls
    text = re.sub(r'\\[a-zA-Z0-9\-]+ ?', ' ', content)
    text = re.sub(r'[{}]', '', text)
    cleaned = sanitize_source_text(text)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', cleaned) if p.strip()]
    units = []
    for idx, p in enumerate(paragraphs, 1):
        units.append({
            "index": idx,
            "label": f"Section {idx}",
            "text": p,
            "unit_type": "body",
            "is_ocr": False
        })
    return {
        "name": filename,
        "type": "application/rtf",
        "units": units,
        "meta": {},
        "warnings": []
    }

def parse_image_file(file_path: str, filename: str) -> Dict[str, Any]:
    """
    Handle direct image file ingestion (.png, .jpg, .webp).
    """
    units = []
    warnings = []
    ocr_text = ""

    # Optional local OCR if pytesseract is available
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        ocr_text = pytesseract.image_to_string(img).strip()
    except Exception:
        pass

    if ocr_text:
        units.append({
            "index": 1,
            "label": "Image (OCR)",
            "text": sanitize_source_text(ocr_text),
            "unit_type": "figure_ocr",
            "is_ocr": True
        })
    else:
        warnings.append("Image uploaded: OCR engine not configured. Ingested without text.")
        units.append({
            "index": 1,
            "label": "Image",
            "text": f"[Image Source: {filename}]",
            "unit_type": "figure_ocr",
            "is_ocr": True
        })

    return {
        "name": filename,
        "type": f"image/{os.path.splitext(filename)[1].lstrip('.')}",
        "units": units,
        "meta": {},
        "warnings": warnings
    }

def parse_zip_archive(file_path: str, filename: str) -> Dict[str, Any]:
    """
    Safely extract zip archive with security caps:
    Max 50 files, max depth 2, max 20 MB uncompressed, skip executables & macros.
    """
    combined_units = []
    combined_warnings = []
    unit_idx = 1

    EXECUTABLE_EXTS = {".exe", ".bat", ".cmd", ".vbs", ".sh", ".ps1", ".dll", ".so", ".xlsm", ".vba"}

    with zipfile.ZipFile(file_path, "r") as z:
        entries = z.infolist()
        if len(entries) > 50:
            combined_warnings.append(f"Zip archive contains {len(entries)} items; capped extraction to 50 files.")
            entries = entries[:50]

        total_uncompressed = sum(e.file_size for e in entries)
        if total_uncompressed > 20 * 1024 * 1024:
            raise ValueError("Zip archive total uncompressed size exceeds 20 MB limit.")

        for entry in entries:
            if entry.is_dir():
                continue
            # Zip slip guard
            if ".." in entry.filename or entry.filename.startswith("/"):
                continue
            
            sub_ext = os.path.splitext(entry.filename)[1].lower()
            if sub_ext in EXECUTABLE_EXTS:
                continue

            # Extract to in-memory bytes or temp
            sub_bytes = z.read(entry.filename)
            sub_name = os.path.basename(entry.filename)
            
            # Sub-parse
            sub_fmt = detect_file_format_from_bytes(sub_bytes, sub_name)
            sub_result = parse_bytes_by_format(sub_bytes, sub_name, sub_fmt)
            
            for u in sub_result.get("units", []):
                combined_units.append({
                    "index": unit_idx,
                    "label": f"{sub_name} > {u['label']}",
                    "text": u["text"],
                    "unit_type": u.get("unit_type", "body"),
                    "is_ocr": u.get("is_ocr", False)
                })
                unit_idx += 1
            combined_warnings.extend(sub_result.get("warnings", []))

    return {
        "name": filename,
        "type": "application/zip",
        "units": combined_units,
        "meta": {"files_extracted": len(combined_units)},
        "warnings": combined_warnings
    }

# =========================================================================
# HELPER IN-MEMORY & BYTES ROUTER
# =========================================================================

def detect_file_format_from_bytes(raw_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if raw_bytes.startswith(b"%PDF"):
        return "pdf"
    if raw_bytes.startswith(b"PK\x03\x04"):
        if ext in ["docx", "pptx", "xlsx"]:
            return ext
        return "zip"
    if ext in ["json", "csv", "tsv", "bib", "ris", "md", "txt", "html"]:
        return ext
    return ext or "txt"

def parse_bytes_by_format(raw_bytes: bytes, filename: str, fmt: str) -> Dict[str, Any]:
    text_content = raw_bytes.decode("utf-8", errors="replace")
    if fmt == "json":
        return parse_json(text_content, filename)
    elif fmt in ["csv", "tsv"]:
        return parse_csv(text_content, filename, delimiter="\t" if fmt == "tsv" else ",")
    elif fmt == "bib":
        return parse_bibtex(text_content, filename)
    elif fmt == "ris":
        return parse_ris(text_content, filename)
    elif fmt == "html":
        return parse_html_string(text_content, filename)
    else:
        # Plain text paragraphs
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text_content) if p.strip()]
        units = []
        for idx, p in enumerate(paragraphs, 1):
            units.append({
                "index": idx,
                "label": f"Section {idx}",
                "text": sanitize_source_text(p),
                "unit_type": "body",
                "is_ocr": False
            })
        return {"name": filename, "type": "text/plain", "units": units, "meta": {}, "warnings": []}

# =========================================================================
# UNIVERSAL NORMALIZED INGESTION ORCHESTRATOR
# =========================================================================

def parse_to_normalized_document(file_path: str, filename: str) -> Dict[str, Any]:
    """
    Every parser returns: { name, type, units: [{ index, label, text, unit_type, is_ocr }], meta, warnings }
    """
    fmt = detect_file_format(file_path, filename)
    
    if fmt == "pdf":
        return parse_pdf(file_path, filename)
    elif fmt == "pptx":
        return parse_pptx(file_path, filename)
    elif fmt == "docx":
        return parse_docx(file_path, filename)
    elif fmt in ["xlsx", "xls"]:
        return parse_xlsx(file_path, filename)
    elif fmt in ["csv", "tsv"]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return parse_csv(content, filename, delimiter="\t" if fmt == "tsv" else ",")
    elif fmt == "json":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return parse_json(content, filename)
    elif fmt == "bib":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return parse_bibtex(content, filename)
    elif fmt == "ris":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return parse_ris(content, filename)
    elif fmt == "html":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return parse_html_string(content, filename)
    elif fmt in ["odt", "odp"]:
        return parse_odt_odp(file_path, filename, is_presentation=(fmt == "odp"))
    elif fmt == "rtf":
        return parse_rtf(file_path, filename)
    elif fmt in ["png", "jpg", "webp"]:
        return parse_image_file(file_path, filename)
    elif fmt == "zip":
        return parse_zip_archive(file_path, filename)
    else:
        # Default text / markdown / fallback
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
        units = []
        for idx, p in enumerate(paragraphs, 1):
            units.append({
                "index": idx,
                "label": f"Paragraph {idx}",
                "text": sanitize_source_text(p),
                "unit_type": "body",
                "is_ocr": False
            })
        if not units:
            units.append({
                "index": 1,
                "label": "Document",
                "text": "[Empty File]",
                "unit_type": "body",
                "is_ocr": False
            })
        return {
            "name": filename,
            "type": "text/plain",
            "units": units,
            "meta": {},
            "warnings": []
        }

def create_source_document_from_units(
    source_id: str,
    name: str,
    file_type: str,
    units: List[Dict[str, Any]],
    warnings: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    size_bytes: int = 0
) -> SourceDocument:
    """
    Construct a SourceDocument and candidate Passages from normalized units.
    """
    all_passages: List[Passage] = []
    full_text_parts: List[str] = []
    
    for u in units:
        u_idx = u.get("index", 1)
        u_label = u.get("label", f"Unit {u_idx}")
        u_text = u.get("text", "")
        u_type = u.get("unit_type", "body")
        u_is_ocr = u.get("is_ocr", False)

        if u_text.strip():
            full_text_parts.append(f"--- [{u_label}] ---\n" + u_text)
            p_list = chunk_text_into_passages(
                source_id=source_id,
                filename=name,
                full_text=u_text,
                page_number=u_idx,
                unit_label=u_label,
                unit_type=u_type,
                is_ocr=u_is_ocr
            )
            all_passages.extend(p_list)

    combined_text = "\n\n".join(full_text_parts)
    # Cap total text length at 5 MB
    if len(combined_text.encode('utf-8')) > MAX_EXTRACTED_TEXT_BYTES:
        combined_text = combined_text[:MAX_EXTRACTED_TEXT_BYTES]
        if warnings is not None:
            warnings.append("Extracted text capped at 5 MB safety limit.")

    return SourceDocument(
        id=source_id,
        filename=name,
        file_type=file_type,
        size_bytes=size_bytes or len(combined_text.encode('utf-8')),
        extracted_text=combined_text,
        page_count=max(1, len(units)),
        passage_count=len(all_passages),
        passages=all_passages,
        units=units,
        warnings=warnings or [],
        meta=meta or {}
    )

def process_file(file_path: str, original_filename: str) -> SourceDocument:
    """
    Universal physical file processor accepting ANY format.
    """
    source_id = str(uuid.uuid4())[:8]
    size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    ext = os.path.splitext(original_filename)[1].lower()

    if ext == ".pptx":
        return extract_pptx_slides(file_path, source_id, original_filename, size_bytes)

    norm_doc = parse_to_normalized_document(file_path, original_filename)
    return create_source_document_from_units(
        source_id=source_id,
        name=original_filename,
        file_type=norm_doc.get("type", "application/octet-stream"),
        units=norm_doc.get("units", []),
        warnings=norm_doc.get("warnings", []),
        meta=norm_doc.get("meta", {}),
        size_bytes=size_bytes
    )

def process_plain_text(content: str, filename: str = "Pasted_Source.txt") -> SourceDocument:
    """
    Process plain text source material into normalized units.
    """
    source_id = str(uuid.uuid4())[:8]
    sanitized = sanitize_source_text(content)
    passages = chunk_text_into_passages(source_id, filename, sanitized, page_number=1)
    paragraphs = [p for p in re.split(r'\n\s*\n', sanitized) if p.strip()]
    units = []
    for idx, p in enumerate(paragraphs, 1):
        units.append({
            "index": idx,
            "label": f"Paragraph {idx}",
            "text": p,
            "unit_type": "body",
            "is_ocr": False
        })
    if not units:
        units.append({
            "index": 1,
            "label": "Paragraph 1",
            "text": sanitized or "[Empty]",
            "unit_type": "body",
            "is_ocr": False
        })

    return SourceDocument(
        id=source_id,
        filename=filename,
        file_type="text/plain",
        size_bytes=len(content.encode('utf-8')),
        extracted_text=sanitized,
        page_count=1,
        passage_count=len(passages),
        passages=passages,
        units=units,
        warnings=[],
        meta={}
    )

