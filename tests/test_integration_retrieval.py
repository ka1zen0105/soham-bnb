import unittest
import os
import tempfile
from backend.models import (
    AuditCreateRequest, AuditStatusEnum, AuditReport, AuditOptions, VerdictEnum
)
from backend.document_processor import process_plain_text
from backend.claim_extractor import extract_claims_deterministic
from backend.evidence_retriever import BM25Retriever
from backend.claim_verifier import verify_single_claim
from backend.report_generator import generate_audit_summary
from backend.deterministic_validator import validate_audit_report
from backend.audit_repository import save_audit, get_audit, list_audits, delete_audit


class TestIntegrationRetrievalAndPersistence(unittest.TestCase):
    """
    Integration tests covering multi-document retrieval, end-to-end verification,
    deterministic validation, and SQLite database round-trip persistence.
    """

    def setUp(self):
        self.doc_text_1 = """BIOCORP PHARMACEUTICALS - Q3 2024 FINANCIAL REPORT
SECTION 1: FINANCIAL HIGHLIGHTS
Total consolidated revenue for the third quarter ended September 30, 2024 was $162 million, an increase of 14% compared to $142 million in Q3 2023. Operating margins contracted slightly to 26.2%.
Cash, cash equivalents, and marketable securities totaled $420 million as of September 30, 2024.
Pipeline Overview: The Phase 3 trial for BC-902 met all primary endpoints with zero observed adverse cardiovascular events."""

        self.doc_text_2 = """SECTION 2: PIPELINE & CLINICAL TRIALS
BC-902 Phase 3 Clinical Study:
The trial achieved statistically significant improvement in progression-free survival (p < 0.001), meeting its primary efficacy endpoint. Mild to moderate cardiovascular events were observed in 4.2% of treated subjects.
Regulatory Status:
The Biologics License Application (BLA) was accepted by the US FDA under Standard Review with a PDUFA action date set for June 2025. Priority Review was not requested."""

        self.answer_text = """BioCorp reported total Q3 revenue of $185 million, representing a 28% year-over-year increase.
The Phase 3 trial for BC-902 met all primary endpoints with zero observed adverse cardiovascular events.
BioCorp's total cash reserves stand at $420 million as of September 30, 2024."""

    def test_end_to_end_pipeline_and_sqlite_roundtrip(self):
        # 1. Ingest multi-documents
        doc1 = process_plain_text(self.doc_text_1, "BioCorp_Financials.txt")
        doc2 = process_plain_text(self.doc_text_2, "BioCorp_Clinical.txt")
        all_passages = doc1.passages + doc2.passages
        self.assertGreaterEqual(len(all_passages), 2)

        # 2. Extract discrete claims
        claims = extract_claims_deterministic(self.answer_text)
        self.assertEqual(len(claims), 3)

        # 3. Index with BM25
        retriever = BM25Retriever(all_passages)

        # 4. Verify claims
        options = AuditOptions()
        verified_claims = [verify_single_claim(c, retriever, options) for c in claims]

        # Claim 1 should be CONTRADICTED ($185M vs $162M)
        self.assertEqual(verified_claims[0].verdict, VerdictEnum.CONTRADICTED)
        # Claim 2 is CONFLICTING_EVIDENCE (endpoints met in doc 1, but adverse events observed in doc 2)
        self.assertEqual(verified_claims[1].verdict, VerdictEnum.CONFLICTING_EVIDENCE)
        # Claim 3 should be SUPPORTED ($420 million cash reserves)
        self.assertEqual(verified_claims[2].verdict, VerdictEnum.SUPPORTED)

        # 5. Summary & Deterministic validation
        summary = generate_audit_summary(verified_claims, 2)
        report = AuditReport(
            id="aud_integ_test_99",
            title="Integration Pipeline Test",
            created_at="2026-10-10 12:00:00 UTC",
            status=AuditStatusEnum.COMPLETED,
            current_step="Completed",
            progress_percentage=100,
            answer_text=self.answer_text,
            source_documents=[doc1, doc2],
            claims=verified_claims,
            summary=summary,
            options=options
        )

        validated = validate_audit_report(report)
        self.assertEqual(validated.summary.total_claims, 3)
        self.assertEqual(validated.summary.supported_count, 1)
        self.assertEqual(validated.summary.contradicted_count, 1)
        self.assertEqual(validated.summary.conflicting_count, 1)

        # 6. SQLite persistence
        save_audit(validated)
        persisted = get_audit("aud_integ_test_99")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.title, "Integration Pipeline Test")
        self.assertEqual(len(persisted.claims), 3)
        self.assertEqual(persisted.summary.supported_count, 1)
        self.assertEqual(persisted.summary.contradicted_count, 1)
        self.assertEqual(persisted.summary.conflicting_count, 1)

        # Clean up test audit
        delete_audit("aud_integ_test_99")


if __name__ == "__main__":
    unittest.main()
