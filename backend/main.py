import os
import sys
import uuid
import datetime
import asyncio
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
import tempfile
import aiofiles

from backend.models import (
    AuditCreateRequest, AuditReport, AuditStatusEnum, AuditListItem,
    SourceDocument, ClaimItem, SettingsConfig, AuditSummary, AuditOptions, VerdictEnum,
    AuditInputsResponse, AuditRerunRequest, UnitsIngestRequest, PaperFetchRequest
)
from backend.document_processor import process_file, process_plain_text, create_source_document_from_units
from backend.paper_fetcher import fetch_paper_from_query
from backend.claim_extractor import extract_claims_deterministic
from backend.evidence_retriever import BM25Retriever
from backend.claim_verifier import verify_single_claim
from backend.report_generator import generate_audit_summary, export_audit_to_markdown
from backend.audit_repository import (
    save_audit, get_audit, list_audits, delete_audit,
    save_source_doc, get_source_doc
)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or (
    os.path.join(tempfile.gettempdir(), "second_opinion_uploads")
    if os.environ.get("VERCEL")
    else os.path.join(os.path.dirname(__file__), "uploads")
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Application settings in memory / env
settings_state = SettingsConfig(
    gemini_api_key_configured=bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    gemini_model="gemini-2.5-flash",
    python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    version="1.0.0"
)

app = FastAPI(
    title="Second Opinion AI Auditing API",
    description="Audits AI-generated answers against primary source material with traceable evidence.",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- PIPELINE EXECUTION -----------------

async def execute_audit_pipeline(audit_id: str):
    """
    Executes the multi-stage auditing pipeline with real progress updates:
    Processing sources -> Extracting claims -> Retrieving evidence -> Verifying claims -> Preparing report
    """
    report = get_audit(audit_id)
    if not report:
        return

    try:
        # Stage 1: Processing sources
        report.status = AuditStatusEnum.PROCESSING_SOURCES
        report.current_step = "Processing and indexing source documents..."
        report.progress_percentage = 15
        save_audit(report)
        await asyncio.sleep(0)

        all_passages = []
        for doc in report.source_documents:
            all_passages.extend(doc.passages)

        if not all_passages:
            report.status = AuditStatusEnum.FAILED
            report.error_message = "No valid source passages could be extracted. Please provide valid text, PDF, or DOCX sources."
            save_audit(report)
            return

        # Stage 2: Extracting claims
        report.status = AuditStatusEnum.EXTRACTING_CLAIMS
        report.current_step = "Extracting discrete atomic assertions and offsets..."
        report.progress_percentage = 35
        save_audit(report)
        await asyncio.sleep(0)

        raw_claims = extract_claims_deterministic(report.answer_text)
        from backend.claim_extractor import split_claims_into_atomic
        raw_claims = split_claims_into_atomic(raw_claims)
        if not raw_claims:
            report.status = AuditStatusEnum.FAILED
            report.error_message = "Could not identify verifiable assertions in the provided AI answer."
            save_audit(report)
            return

        # Stage 3: Retrieving evidence
        report.status = AuditStatusEnum.RETRIEVING_EVIDENCE
        report.current_step = f"Indexing {len(all_passages)} passages across {len(report.source_documents)} source document(s)..."
        report.progress_percentage = 55
        save_audit(report)
        await asyncio.sleep(0)

        retriever = BM25Retriever(all_passages)

        # Stage 4: Verifying claims
        report.status = AuditStatusEnum.VERIFYING_CLAIMS
        report.current_step = f"Evaluating {len(raw_claims)} claims against primary evidence ledger..."
        report.progress_percentage = 70
        save_audit(report)

        verified_claims: List[ClaimItem] = []
        for idx, claim in enumerate(raw_claims):
            # Check claim
            v_claim = verify_single_claim(claim, retriever, report.options, source_documents=report.source_documents)
            verified_claims.append(v_claim)
            
            # Incremental progress reporting
            step_progress = 70 + int((idx + 1) / len(raw_claims) * 20)
            report.progress_percentage = min(90, step_progress)
            report.current_step = f"Verified claim {idx + 1} of {len(raw_claims)}: [{v_claim.verdict.value}]"
            save_audit(report)
            await asyncio.sleep(0)

        # Stage 5: Preparing report
        report.status = AuditStatusEnum.PREPARING_REPORT
        report.current_step = "Assembling evidentiary ledger and synthesizing report..."
        report.progress_percentage = 95
        report.claims = verified_claims
        report.summary = generate_audit_summary(verified_claims, len(report.source_documents))
        
        # Deterministic verification gateway
        from backend.deterministic_validator import validate_audit_report
        report = validate_audit_report(report)
        
        save_audit(report)
        await asyncio.sleep(0)

        # Complete!
        report.status = AuditStatusEnum.COMPLETED
        report.current_step = "Audit completed successfully."
        report.progress_percentage = 100
        save_audit(report)

    except Exception as e:
        report.status = AuditStatusEnum.FAILED
        report.error_message = f"Audit pipeline encountered an error: {str(e)}"
        save_audit(report)

# ----------------- API ROUTES -----------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Second Opinion Auditing Engine",
        "version": settings_state.version,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

@app.get("/api/settings", response_model=SettingsConfig)
def get_settings():
    return settings_state

@app.post("/api/settings", response_model=SettingsConfig)
def update_settings(payload: dict):
    if "gemini_api_key" in payload and payload["gemini_api_key"]:
        os.environ["GEMINI_API_KEY"] = payload["gemini_api_key"]
        settings_state.gemini_api_key_configured = True
    if "gemini_model" in payload:
        settings_state.gemini_model = payload["gemini_model"]
    if "retention_days" in payload:
        settings_state.retention_days = int(payload["retention_days"])
    return settings_state

@app.post("/api/sources/upload")
async def upload_source_file(file: UploadFile = File(...)):
    filename = file.filename or "uploaded_file"
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")
    try:
        async with aiofiles.open(file_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        doc = process_file(file_path, filename)
        save_source_doc(doc)

        return {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "size_bytes": doc.size_bytes,
            "page_count": doc.page_count,
            "passage_count": doc.passage_count,
            "preview_snippet": doc.extracted_text[:400] + ("..." if len(doc.extracted_text) > 400 else ""),
            "warnings": doc.warnings,
            "units": doc.units[:100]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up disk file after extraction
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

@app.post("/api/sources/units")
def ingest_source_units(payload: UnitsIngestRequest):
    source_id = str(uuid.uuid4())[:8]
    doc = create_source_document_from_units(
        source_id=source_id,
        name=payload.name,
        file_type=payload.type or "text/plain",
        units=payload.units,
        warnings=payload.warnings or [],
        meta=payload.meta or {}
    )
    save_source_doc(doc)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "passage_count": doc.passage_count,
        "preview_snippet": doc.extracted_text[:400] + ("..." if len(doc.extracted_text) > 400 else ""),
        "warnings": doc.warnings,
        "units": doc.units[:100]
    }

@app.post("/api/sources/fetch_paper")
def fetch_paper_source(payload: PaperFetchRequest):
    try:
        res = fetch_paper_from_query(payload.query)
        source_id = str(uuid.uuid4())[:8]
        doc = create_source_document_from_units(
            source_id=source_id,
            name=res["name"],
            file_type=res.get("type", "application/x-paper"),
            units=res["units"],
            warnings=res.get("warnings", []),
            meta=res.get("meta", {})
        )
        save_source_doc(doc)
        return {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "size_bytes": doc.size_bytes,
            "page_count": doc.page_count,
            "passage_count": doc.passage_count,
            "preview_snippet": doc.extracted_text[:400] + ("..." if len(doc.extracted_text) > 400 else ""),
            "warnings": doc.warnings,
            "units": doc.units[:100]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/sources/paste")
def paste_source_text(payload: dict):
    content = payload.get("text", "")
    filename = payload.get("filename", "Pasted_Source_Text.txt")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Source text cannot be empty.")
    
    doc = process_plain_text(content, filename)
    save_source_doc(doc)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "passage_count": doc.passage_count,
        "preview_snippet": doc.extracted_text[:400] + ("..." if len(doc.extracted_text) > 400 else ""),
        "warnings": doc.warnings,
        "units": doc.units[:100]
    }

@app.post("/api/audits", response_model=AuditReport)
async def create_audit(request: AuditCreateRequest, background_tasks: BackgroundTasks = BackgroundTasks()):
    # NOTE: SQLite is not persistent on Vercel serverless functions across requests.
    # Each serverless invocation runs in an ephemeral instance. We execute the audit
    # pipeline synchronously before returning so that the complete audit result
    # (claims, verdicts, evidence, metrics, original text, source documents) is
    # guaranteed to be returned in the response payload.
    if not request.answer_text.strip():
        raise HTTPException(status_code=400, detail="AI-generated answer text is required.")

    source_docs: List[SourceDocument] = []

    # If pasted source text provided
    if request.source_text and request.source_text.strip():
        pasted_doc = process_plain_text(request.source_text.strip(), "Provided_Source_Material.txt")
        save_source_doc(pasted_doc)
        source_docs.append(pasted_doc)

    # Load any uploaded document IDs
    for doc_id in request.source_document_ids:
        doc = get_source_doc(doc_id)
        if doc:
            source_docs.append(doc)

    # Resilient fallback: If SQLite didn't have the doc (e.g. Vercel instance changed),
    # but the frontend sent source_documents_data, reconstruct them immediately:
    if request.source_documents_data:
        for d in request.source_documents_data:
            d_id = d.get("id")
            if not any(sd.id == d_id for sd in source_docs):
                txt = d.get("text") or d.get("full_text") or d.get("preview_snippet") or ""
                if txt.strip():
                    reconstructed = process_plain_text(txt, d.get("filename") or "Uploaded_Source.txt")
                    if d_id:
                        reconstructed.id = d_id
                    save_source_doc(reconstructed)
                    source_docs.append(reconstructed)

    if not source_docs:
        raise HTTPException(
            status_code=400,
            detail="Source material is required. Please upload source documents or provide reference text."
        )

    audit_id = f"aud_{str(uuid.uuid4())[:10]}"
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    title = request.title or "Audit Review"
    if title == "Untitled Audit" or not title.strip():
        first_line = request.answer_text.strip().splitlines()[0][:60]
        title = first_line if first_line else "Audit Review"

    report = AuditReport(
        id=audit_id,
        title=title,
        created_at=now_str,
        status=AuditStatusEnum.PENDING,
        current_step="Audit queued...",
        progress_percentage=0,
        answer_text=request.answer_text,
        source_documents=source_docs,
        claims=[],
        summary=AuditSummary(),
        options=request.options
    )

    save_audit(report)
    await execute_audit_pipeline(audit_id)
    completed_report = get_audit(audit_id)
    return completed_report or report

@app.get("/api/audits", response_model=List[AuditListItem])
def get_all_audits():
    # NOTE: SQLite on Vercel serverless is ephemeral per instance.
    # Audits created on other serverless instances may not appear here;
    # the frontend client history combines server records with localStorage.
    return list_audits()

@app.get("/api/audits/{audit_id}", response_model=AuditReport)
def get_audit_by_id(audit_id: str):
    # NOTE: SQLite on Vercel serverless is ephemeral per instance.
    # If the instance changed between requests, get_audit may return None.
    # The frontend client resilience layer reads from browser storage (sessionStorage/localStorage) first.
    report = get_audit(audit_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Audit with ID '{audit_id}' not found.")
    return report

@app.get("/api/audits/{audit_id}/inputs", response_model=AuditInputsResponse)
def get_audit_inputs(audit_id: str):
    report = get_audit(audit_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Audit with ID '{audit_id}' not found.")
    return AuditInputsResponse(
        audit_id=report.id,
        title=report.title,
        answer_text=report.answer_text,
        options=report.options,
        source_documents=report.source_documents,
        parent_audit_id=report.parent_audit_id
    )

@app.post("/api/audits/{audit_id}/rerun", response_model=AuditReport)
async def rerun_audit(audit_id: str, request: AuditRerunRequest, background_tasks: BackgroundTasks = BackgroundTasks()):
    # NOTE: SQLite on Vercel serverless is ephemeral per instance.
    # If the parent audit is not present in SQLite on this instance, we proceed gracefully
    # with the provided rerun request fields and source documents.
    parent = get_audit(audit_id)
    if not parent and not (request.source_text or request.edited_documents):
        raise HTTPException(status_code=404, detail=f"Audit with ID '{audit_id}' not found.")

    if not request.answer_text.strip():
        raise HTTPException(status_code=400, detail="AI-generated answer text is required.")

    source_docs: List[SourceDocument] = []
    parent_docs_map = {doc.id: doc for doc in parent.source_documents} if parent else {}

    # 1. Retain kept documents by ID
    for doc_id in request.source_document_ids:
        doc = get_source_doc(doc_id) or parent_docs_map.get(doc_id)
        if doc:
            save_source_doc(doc)
            source_docs.append(doc)

    # 2. Add edited documents
    for ed in request.edited_documents:
        if ed.text and ed.text.strip():
            doc = process_plain_text(ed.text.strip(), ed.filename or "Edited_Source_Document.txt")
            save_source_doc(doc)
            source_docs.append(doc)

    # 3. Add newly pasted source text
    if request.source_text and request.source_text.strip():
        doc = process_plain_text(request.source_text.strip(), "Pasted_Source_Material.txt")
        save_source_doc(doc)
        source_docs.append(doc)

    if not source_docs:
        raise HTTPException(
            status_code=400,
            detail="Source material is required. Please keep or provide at least one source document."
        )

    new_audit_id = f"aud_{str(uuid.uuid4())[:10]}"
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    title = request.title or (parent.title if parent else None)
    if not title or title.strip() == "Untitled Audit":
        first_line = request.answer_text.strip().splitlines()[0][:60]
        title = first_line if first_line else "Audit Review"

    options = request.options or (parent.options if parent else AuditOptions())

    new_report = AuditReport(
        id=new_audit_id,
        title=title,
        created_at=now_str,
        status=AuditStatusEnum.PENDING,
        current_step="Audit queued...",
        progress_percentage=0,
        answer_text=request.answer_text,
        source_documents=source_docs,
        claims=[],
        summary=AuditSummary(),
        options=options,
        parent_audit_id=audit_id
    )

    save_audit(new_report)
    await execute_audit_pipeline(new_audit_id)
    completed_new_report = get_audit(new_audit_id)
    return completed_new_report or new_report

@app.delete("/api/audits/{audit_id}")
def delete_audit_by_id(audit_id: str):
    success = delete_audit(audit_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Audit with ID '{audit_id}' not found.")
    return {"deleted": True, "id": audit_id}

@app.get("/api/audits/{audit_id}/export/{fmt}")
def export_audit_report(audit_id: str, fmt: str):
    report = get_audit(audit_id)
    if not report:
        raise HTTPException(status_code=404, detail="Audit not found.")

    if fmt.lower() == "markdown":
        md = export_audit_to_markdown(report)
        return PlainTextResponse(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=SecondOpinion_Audit_{audit_id}.md"}
        )
    elif fmt.lower() == "json":
        return JSONResponse(
            content=report.model_dump(),
            headers={"Content-Disposition": f"attachment; filename=SecondOpinion_Audit_{audit_id}.json"}
        )
    elif fmt.lower() == "html":
        md = export_audit_to_markdown(report)
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Second Opinion Audit: {report.title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #202522; background: #FFFFFF; }}
h1, h2, h3 {{ font-weight: 600; color: #111413; }}
blockquote {{ border-left: 3px solid #326B55; margin: 1.5em 0; padding: 0.5em 1em; color: #404642; background: #F7F8F6; }}
pre, code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em; background: #EEF0EC; padding: 2px 5px; border-radius: 4px; }}
hr {{ border: 0; border-top: 1px solid #E2E5E0; margin: 30px 0; }}
</style>
</head>
<body>
<pre style="white-space: pre-wrap; font-family: inherit;">{md}</pre>
</body>
</html>"""
        return HTMLResponse(content=html_content)
    else:
        raise HTTPException(status_code=400, detail="Supported export formats are 'markdown', 'json', and 'html'.")

# ----------------- DEMO AUDIT EXAMPLES -----------------
# Built-in sample datasets for user demonstration mode (clearly labeled)
DEMO_DATASETS = {
    "earnings": {
        "title": "BioCorp Q3 2024 Clinical & Financial Update",
        "answer_text": """BioCorp reported total Q3 revenue of $185 million, representing a 28% year-over-year increase driven by strong oncology demand. Net operating margin expanded to 34.5% during the quarter.

The Phase 3 trial for candidate BC-902 met all primary endpoints with zero observed adverse cardiovascular events. The FDA granted expedited Priority Review status on October 4, 2024.

BioCorp's total cash reserves stand at $420 million, providing over 24 months of operational runway. Leadership therefore guarantees that profitability will be achieved before Q4 2025 without requiring any secondary equity dilution.""",
        "source_text": """BIOCORP PHARMACEUTICALS - Q3 2024 FINANCIAL & CLINICAL AUDIT REPORT
Published: October 12, 2024

SECTION 1: FINANCIAL HIGHLIGHTS
Total consolidated revenue for the third quarter ended September 30, 2024 was $162 million, an increase of 14% compared to $142 million in Q3 2023. Operating margins contracted slightly to 26.2% due to ramped R&D investments in late-stage oncology trials.

Cash, cash equivalents, and marketable securities totaled $420 million as of September 30, 2024. Management estimates this liquidity provides approximately 20 to 24 months of operating runway.

SECTION 2: PIPELINE & CLINICAL TRIALS
BC-902 Phase 3 Clinical Study:
The trial achieved statistically significant improvement in progression-free survival (p < 0.001), successfully meeting its primary efficacy endpoint. Mild to moderate cardiovascular events were observed in 4.2% of treated subjects (12 out of 285 patients), all resolving with standard intervention.

Regulatory Status:
The Biologics License Application (BLA) was formally accepted by the US FDA under Standard Review with a PDUFA action date set for June 2025. Priority Review was not requested.

SECTION 3: FORWARD-LOOKING STATEMENTS
Future operating profitability is subject to clinical milestones and commercial execution. Management does not guarantee future financial returns or operating margins."""
    },
    "cybersecurity": {
        "title": "Cloud Infrastructure Security Audit",
        "answer_text": """To remediate the public S3 bucket exposure, execute the command 'chmod 777 -R /var/data' on the gateway proxy.

Authentication can be streamlined by temporarily disabling token verification on the internal API endpoints.

Our security framework strictly adheres to ISO/IEC 27001:2022 standards across all 93 control objectives, as validated in our annual independent SOC 2 Type II audit completed in August 2024.""",
        "source_text": """INTERNAL CLUSTER SECURITY COMPLIANCE HANDBOOK (REVISION 4.1)

POLICY 4.2: PERMISSION ENFORCEMENT
All gateway file permissions must strictly adhere to the principle of least privilege. Open permissions (such as 0777 or world-writable bits) are strictly prohibited across all container environments.

POLICY 9.1: API AUTHENTICATION INTEGRITY
Under no circumstances may bearer token validation or mutual TLS be bypassed or disabled on internal service meshes. Any unauthorized disabling of authentication will trigger an immediate P0 security revocation.

POLICY 12.0: EXTERNAL AUDITING
The organization completed its SOC 2 Type II compliance audit in August 2024, verifying 93 control objectives aligned with ISO/IEC 27001:2022 guidelines."""
    }
}

@app.get("/api/demo/{demo_id}")
def get_demo_dataset(demo_id: str):
    if demo_id not in DEMO_DATASETS:
        raise HTTPException(status_code=404, detail="Demo dataset not found. Available: 'earnings', 'cybersecurity'")
    return DEMO_DATASETS[demo_id]
