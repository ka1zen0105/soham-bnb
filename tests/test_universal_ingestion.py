import os
import unittest
from backend.models import (
    VerdictEnum, ClaimItem, AuditOptions, SeverityEnum, ClaimCategoryEnum
)
from backend.document_processor import process_file, parse_to_normalized_document
from backend.evidence_retriever import BM25Retriever
from backend.claim_verifier import verify_single_claim
from backend.paper_fetcher import extract_doi, extract_arxiv_id, fetch_arxiv_metadata

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

class TestUniversalSourceIngestion(unittest.TestCase):
    def setUp(self):
        self.options = AuditOptions(
            verify_sources=True,
            reasoning_checks=True,
            safety_review=True,
            external_verification=False
        )

    def _create_claim(self, claim_id: str, text: str) -> ClaimItem:
        return ClaimItem(
            id=claim_id,
            claim_number=1,
            text=text,
            start_offset=0,
            end_offset=len(text),
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=ClaimCategoryEnum.FACTUAL,
            explanation="",
            confidence_score=0.0,
            confidence_basis="",
            severity=SeverityEnum.LOW
        )

    def test_01_ieee_12page_13images_pdf_ingests_cleanly(self):
        """Test that 12-page IEEE PDF with 13 images ingests without error and ignores image bytes for text."""
        path = os.path.join(FIXTURES_DIR, "ieee_paper_12pages_13images.pdf")
        doc = process_file(path, "ieee_paper_12pages_13images.pdf")

        self.assertEqual(doc.filename, "ieee_paper_12pages_13images.pdf")
        self.assertGreaterEqual(doc.page_count, 12)
        self.assertGreaterEqual(doc.passage_count, 12)
        self.assertIn("Page 1", doc.extracted_text)
        self.assertIn("Page 12", doc.extracted_text)
        self.assertIn("Evaluation of Distributed Ledger Verification Protocols", doc.extracted_text)
        
        # Verify references were parsed into reference unit type
        ref_passages = [p for p in doc.passages if p.unit_type == "reference"]
        self.assertGreaterEqual(len(ref_passages), 1)
        self.assertIn("Smith", ref_passages[0].text)

    def test_02_pptx_slide3_claim_supported_with_location_label(self):
        """Test claim taken from slide 3 of PPTX is Supported with 'Slide 3' in evidence."""
        path = os.path.join(FIXTURES_DIR, "presentation_with_notes.pptx")
        doc = process_file(path, "presentation_with_notes.pptx")

        self.assertEqual(doc.filename, "presentation_with_notes.pptx")
        self.assertGreaterEqual(doc.page_count, 4)
        
        # Speaker notes present
        self.assertIn("Speaker notes", doc.extracted_text)

        # Verify claim from Slide 3
        claim_text = "Quantum supremacy benchmark was completed in 200 seconds across 53 qubits."
        claim = self._create_claim("clm_slide3", claim_text)
        retriever = BM25Retriever(doc.passages)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(verified.supporting_evidence), 1)
        
        ev = verified.supporting_evidence[0]
        self.assertEqual(ev.unit_label, "Slide 3")
        self.assertEqual(ev.page_number, 3)
        self.assertIn("200 seconds", ev.text)

    def test_03_spreadsheet_cell_claim_supported_with_sheet_row_label(self):
        """Test claim taken from Sheet 'Q3' row 12 of XLSX is Supported with 'Sheet 'Q3' row 12' label."""
        path = os.path.join(FIXTURES_DIR, "multisheet_financials.xlsx")
        doc = process_file(path, "multisheet_financials.xlsx")

        self.assertEqual(doc.filename, "multisheet_financials.xlsx")
        self.assertIn("Sheet 'Q3' row 12", doc.extracted_text)

        claim_text = "BC-902 clinical yield reached 94.8%."
        claim = self._create_claim("clm_xlsx", claim_text)
        retriever = BM25Retriever(doc.passages)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(verified.supporting_evidence), 1)

        ev = verified.supporting_evidence[0]
        self.assertEqual(ev.unit_label, "Sheet 'Q3' row 12")
        self.assertEqual(ev.unit_type, "table")
        self.assertIn("94.8%", ev.text)

    def test_04_nested_json_claim_supported_with_json_path_label(self):
        """Test claim taken from nested JSON value is Supported with 'Path ...' location label."""
        path = os.path.join(FIXTURES_DIR, "nested_infrastructure.json")
        doc = process_file(path, "nested_infrastructure.json")

        self.assertEqual(doc.filename, "nested_infrastructure.json")
        self.assertIn("infrastructure.datacenter.cluster.node_count: 128", doc.extracted_text)

        claim_text = "infrastructure.datacenter.cluster.node_count: 128"
        claim = self._create_claim("clm_json", claim_text)
        retriever = BM25Retriever(doc.passages)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(verified.supporting_evidence), 1)

        ev = verified.supporting_evidence[0]
        self.assertEqual(ev.unit_label, "Path infrastructure.datacenter.cluster.node_count")
        self.assertEqual(ev.unit_type, "json_path")
        self.assertIn("128", ev.text)

    def test_05_csv_ingests_and_verifies_row_labels(self):
        """Test CSV file ingests with Row labels and verifies correctly."""
        path = os.path.join(FIXTURES_DIR, "products_catalog.csv")
        doc = process_file(path, "products_catalog.csv")

        self.assertEqual(doc.filename, "products_catalog.csv")
        self.assertIn("Row 2", doc.extracted_text)
        self.assertIn("Titanium Sensor", doc.extracted_text)

        claim_text = "Titanium Sensor inventory count is 450."
        claim = self._create_claim("clm_csv", claim_text)
        retriever = BM25Retriever(doc.passages)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(verified.supporting_evidence), 1)
        self.assertEqual(verified.supporting_evidence[0].unit_label, "Row 2")

    def test_06_docx_with_embedded_images_ingests_without_error(self):
        """Test DOCX containing embedded images and tables ingests without crashing."""
        path = os.path.join(FIXTURES_DIR, "document_with_images.docx")
        doc = process_file(path, "document_with_images.docx")

        self.assertEqual(doc.filename, "document_with_images.docx")
        self.assertIn("Mutual TLS enforced on port 8443", doc.extracted_text)
        self.assertIn("NIST Special Publication", doc.extracted_text)

    def test_07_bib_file_parses_citations_into_references(self):
        """Test .bib file parses reference list into structured entries tagged unit_type='reference'."""
        path = os.path.join(FIXTURES_DIR, "academic_references.bib")
        doc = process_file(path, "academic_references.bib")

        self.assertEqual(doc.filename, "academic_references.bib")
        ref_passages = [p for p in doc.passages if p.unit_type == "reference"]
        self.assertGreaterEqual(len(ref_passages), 2)
        
        # Verify claim about Smith et al. (2021)
        claim_text = "Smith, John and Doe, Jane (2021). Scalable Quantum Verification on Hybrid Cloud Infrastructure."
        claim = self._create_claim("clm_bib", claim_text)
        retriever = BM25Retriever(doc.passages)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        ev = verified.supporting_evidence[0]
        self.assertEqual(ev.unit_label, "Reference [smith2021quantum]")
        self.assertEqual(ev.unit_type, "reference")

    def test_08_scanned_image_only_pdf_ingests_with_warning_not_failure(self):
        """Test that an image-only scanned PDF ingests with a warning chip, NEVER a failure."""
        path = os.path.join(FIXTURES_DIR, "scanned_image_only.pdf")
        doc = process_file(path, "scanned_image_only.pdf")

        # Document must exist and NOT raise an error
        self.assertIsNotNone(doc)
        self.assertEqual(doc.filename, "scanned_image_only.pdf")
        
        # Must contain warning about image-only pages
        self.assertGreaterEqual(len(doc.warnings), 1)
        warning_str = " ".join(doc.warnings).lower()
        self.assertTrue("image-only" in warning_str or "images only" in warning_str)

    def test_09_paper_fetcher_query_detection(self):
        """Test DOI and arXiv pattern extractors."""
        self.assertEqual(extract_doi("10.1038/s41586-020-2649-2"), "10.1038/s41586-020-2649-2")
        self.assertEqual(extract_doi("https://doi.org/10.1145/3372297.3417234"), "10.1145/3372297.3417234")
        self.assertEqual(extract_arxiv_id("arXiv:2303.08774"), "2303.08774")
        self.assertEqual(extract_arxiv_id("https://arxiv.org/abs/2106.09685"), "2106.09685")


if __name__ == "__main__":
    unittest.main()
