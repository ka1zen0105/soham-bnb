import os
import json
import sqlite3
from typing import List, Optional, Dict, Any
import tempfile
from backend.models import AuditReport, AuditListItem, AuditStatusEnum, SourceDocument

DB_PATH = os.environ.get("DB_PATH") or (
    os.path.join(tempfile.gettempdir(), "second_opinion.db")
    if os.environ.get("VERCEL")
    else os.path.join(os.path.dirname(__file__), "second_opinion.db")
)

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            current_step TEXT,
            progress_percentage INTEGER DEFAULT 0,
            error_message TEXT,
            total_claims INTEGER DEFAULT 0,
            supported_count INTEGER DEFAULT 0,
            contradicted_count INTEGER DEFAULT 0,
            insufficient_count INTEGER DEFAULT 0,
            ambiguous_count INTEGER DEFAULT 0,
            conflicting_count INTEGER DEFAULT 0,
            source_doc_count INTEGER DEFAULT 0,
            report_data TEXT NOT NULL
        )
    """)
    # Migration if conflicting_count not yet added
    try:
        cursor.execute("ALTER TABLE audits ADD COLUMN conflicting_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_docs (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            doc_data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Initialize upon import
init_db()

def save_audit(report: AuditReport):
    conn = get_connection()
    cursor = conn.cursor()
    report_json = report.model_dump_json()
    cursor.execute("""
        INSERT OR REPLACE INTO audits (
            id, title, created_at, status, current_step, progress_percentage,
            error_message, total_claims, supported_count, contradicted_count,
            insufficient_count, ambiguous_count, conflicting_count, source_doc_count, report_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report.id,
        report.title,
        report.created_at,
        report.status.value,
        report.current_step,
        report.progress_percentage,
        report.error_message,
        report.summary.total_claims,
        report.summary.supported_count,
        report.summary.contradicted_count,
        report.summary.insufficient_count,
        report.summary.ambiguous_count,
        getattr(report.summary, "conflicting_count", 0),
        len(report.source_documents),
        report_json
    ))
    conn.commit()
    conn.close()

def get_audit(audit_id: str) -> Optional[AuditReport]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT report_data FROM audits WHERE id = ?", (audit_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    data = json.loads(row["report_data"])
    return AuditReport.model_validate(data)

def list_audits() -> List[AuditListItem]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, created_at, status, total_claims, contradicted_count,
               supported_count, insufficient_count, ambiguous_count, conflicting_count, source_doc_count
        FROM audits
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        conflicting = r["conflicting_count"] if "conflicting_count" in r.keys() else 0
        items.append(AuditListItem(
            id=r["id"],
            title=r["title"],
            created_at=r["created_at"],
            status=AuditStatusEnum(r["status"]),
            total_claims=r["total_claims"],
            contradicted_count=r["contradicted_count"],
            supported_count=r["supported_count"],
            insufficient_count=r["insufficient_count"],
            ambiguous_count=r["ambiguous_count"],
            conflicting_count=conflicting,
            source_doc_count=r["source_doc_count"]
        ))
    return items

def delete_audit(audit_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audits WHERE id = ?", (audit_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def save_source_doc(doc: SourceDocument):
    conn = get_connection()
    cursor = conn.cursor()
    doc_json = doc.model_dump_json()
    cursor.execute("""
        INSERT OR REPLACE INTO source_docs (id, filename, file_type, size_bytes, doc_data)
        VALUES (?, ?, ?, ?, ?)
    """, (doc.id, doc.filename, doc.file_type, doc.size_bytes, doc_json))
    conn.commit()
    conn.close()

def get_source_doc(doc_id: str) -> Optional[SourceDocument]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT doc_data FROM source_docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    data = json.loads(row["doc_data"])
    return SourceDocument.model_validate(data)
