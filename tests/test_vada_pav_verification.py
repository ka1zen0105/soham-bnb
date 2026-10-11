import os
import unittest
from backend.models import (
    AuditReport, AuditSummary, ClaimItem, VerdictEnum,
    ClaimCategoryEnum, AuditStatusEnum, AuditOptions
)
from backend.document_processor import process_plain_text
from backend.evidence_retriever import BM25Retriever
from backend.claim_verifier import verify_single_claim
from backend.claim_extractor import (
    categorize_claim, has_number_or_date, extract_claims_deterministic,
    split_claims_into_atomic
)
from backend.deterministic_validator import validate_audit_report, is_valid_quote_match
from backend.text_normalizer import norm

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "Vada_Pav.txt")

CLAIM_1 = "Vada pav, alternatively spelt wada pao, (listenⓘ) is a vegetarian fast food dish native to the Indian state of Maharashtra.[1] The dish consists of a deep-fried potato dumpling placed inside a bread bun (pav) sliced almost in half through the middle."
CLAIM_2 = "It is generally accompanied by one or more chutneys and a green chili pepper.[2] Although it originated as an inexpensive street food in Mumbai, it is now served in food stalls and restaurants across India."
CLAIM_3 = "It is also called Bombay burger[3] in keeping with its origins and its resemblance in physical form to a burger."

class TestVadaPavVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            cls.source_text = f.read()
        cls.doc = process_plain_text(cls.source_text, filename="Vada_Pav.txt")
        cls.retriever = BM25Retriever(cls.doc.passages)
        cls.options = AuditOptions()

    def test_claim_1_from_screenshot_is_supported_with_evidence(self):
        """Claim #1 from screenshot must return SUPPORTED with evidence."""
        claim = ClaimItem(
            id="clm_1",
            claim_number=1,
            text=CLAIM_1,
            start_offset=0,
            end_offset=len(CLAIM_1),
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=ClaimCategoryEnum.FACTUAL,
            explanation="",
            confidence_score=0.0,
            confidence_basis=""
        )
        verified = verify_single_claim(claim, self.retriever, self.options, source_documents=[self.doc])
        
        # Run deterministic validation
        report = AuditReport(
            id="test_rpt_1",
            title="Vada Pav Audit",
            created_at="2026-10-11T00:00:00Z",
            status=AuditStatusEnum.VERIFYING_CLAIMS,
            answer_text=CLAIM_1,
            source_documents=[self.doc],
            claims=[verified],
            summary=AuditSummary(total_claims=1)
        )
        validated = validate_audit_report(report)
        final_claim = validated.claims[0]

        self.assertEqual(final_claim.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(final_claim.supporting_evidence), 1)
        self.assertTrue(final_claim.supporting_evidence[0].exact_match_verified)
        self.assertNotIn("Deterministic validation override", final_claim.explanation)

    def test_claim_2_from_screenshot_is_supported_with_evidence(self):
        """Claim #2 from screenshot must return SUPPORTED with evidence."""
        claim = ClaimItem(
            id="clm_2",
            claim_number=2,
            text=CLAIM_2,
            start_offset=0,
            end_offset=len(CLAIM_2),
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=ClaimCategoryEnum.FACTUAL,
            explanation="",
            confidence_score=0.0,
            confidence_basis=""
        )
        verified = verify_single_claim(claim, self.retriever, self.options, source_documents=[self.doc])
        
        report = AuditReport(
            id="test_rpt_2",
            title="Vada Pav Audit",
            created_at="2026-10-11T00:00:00Z",
            status=AuditStatusEnum.VERIFYING_CLAIMS,
            answer_text=CLAIM_2,
            source_documents=[self.doc],
            claims=[verified],
            summary=AuditSummary(total_claims=1)
        )
        validated = validate_audit_report(report)
        final_claim = validated.claims[0]

        self.assertEqual(final_claim.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(final_claim.supporting_evidence), 1)
        self.assertTrue(final_claim.supporting_evidence[0].exact_match_verified)

    def test_claim_3_from_screenshot_is_supported_with_evidence(self):
        """Claim #3 from screenshot must return SUPPORTED with evidence."""
        claim = ClaimItem(
            id="clm_3",
            claim_number=3,
            text=CLAIM_3,
            start_offset=0,
            end_offset=len(CLAIM_3),
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=ClaimCategoryEnum.FACTUAL,
            explanation="",
            confidence_score=0.0,
            confidence_basis=""
        )
        verified = verify_single_claim(claim, self.retriever, self.options, source_documents=[self.doc])
        
        report = AuditReport(
            id="test_rpt_3",
            title="Vada Pav Audit",
            created_at="2026-10-11T00:00:00Z",
            status=AuditStatusEnum.VERIFYING_CLAIMS,
            answer_text=CLAIM_3,
            source_documents=[self.doc],
            claims=[verified],
            summary=AuditSummary(total_claims=1)
        )
        validated = validate_audit_report(report)
        final_claim = validated.claims[0]

        self.assertEqual(final_claim.verdict, VerdictEnum.SUPPORTED)
        self.assertGreaterEqual(len(final_claim.supporting_evidence), 1)
        self.assertTrue(final_claim.supporting_evidence[0].exact_match_verified)

    def test_claim_categorization_only_numerical_when_contains_number_or_date(self):
        """Fix claim type classification: only label NUMERICAL if the claim contains a number or date."""
        # Claim 1 contains "half" and footnote [1], but no genuine number or date
        self.assertFalse(has_number_or_date(CLAIM_1))
        self.assertEqual(categorize_claim(CLAIM_1), ClaimCategoryEnum.FACTUAL)

        # Claim with actual year
        claim_with_year = "Einstein moved to Switzerland in 1895."
        self.assertTrue(has_number_or_date(claim_with_year))
        self.assertEqual(categorize_claim(claim_with_year), ClaimCategoryEnum.NUMERICAL)

        # Claim with quantity
        claim_with_qty = "BioCorp reported total Q3 revenue of $185 million."
        self.assertTrue(has_number_or_date(claim_with_qty))
        self.assertEqual(categorize_claim(claim_with_qty), ClaimCategoryEnum.NUMERICAL)

    def test_atomic_claim_splitting(self):
        """Split extracted claims into single-sentence atomic claims before verification."""
        multi_sentence_text = (
            "Vada pav, alternatively spelt wada pao, (listenⓘ) is a vegetarian fast food dish native to the Indian state of Maharashtra.[1] "
            "The dish consists of a deep-fried potato dumpling placed inside a bread bun (pav) sliced almost in half through the middle."
        )
        claims = extract_claims_deterministic(multi_sentence_text)
        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0].category, ClaimCategoryEnum.FACTUAL)
        self.assertEqual(claims[1].category, ClaimCategoryEnum.FACTUAL)

    def test_soft_wrap_and_split_words_unwrapping(self):
        """Verify that line-wrapped and split words (e.g. from PDF copy-paste) are unwrapped into full assertions."""
        wrapped_text = (
            "Public code repositories such as GitHub offer a wide range\n"
            "of programming examples; however, they often fail to reflect\n"
            "the internal conventions, documentation styles, and system ar\n"
            "chitectures characteristic of proprietary or enterprise-level code.\n"
            "In real-world hardware development, each organiza\n"
            "tion typically maintains code with a unique structure, domain\n"
            "specific APIs, and customized business logic."
        )
        claims = extract_claims_deterministic(wrapped_text)
        self.assertEqual(len(claims), 2)
        self.assertIn("system architectures", claims[0].text)
        self.assertIn("each organization", claims[1].text)
        self.assertFalse(any(c.text.strip().endswith("system ar") for c in claims))
        self.assertFalse(any(c.text.strip().startswith("tion") for c in claims))

    def test_quote_validation_accepts_normalized_substring_and_high_similarity(self):
        """Quote validation must compare normalised text, accepting substring or similarity > 0.9."""
        source_p = "Vada pav, alternatively spelt wada pao, (listen ⓘ) is a vegetarian fast food dish native to the Indian state of Maharashtra.[1]"
        # Substring quote
        quote_clean = "Vada pav, alternatively spelt wada pao, is a vegetarian fast food dish"
        self.assertTrue(is_valid_quote_match(quote_clean, source_p))

        # Near-identical quote with dash variation and minor whitespace
        quote_similar = "Vada pav, alternatively spelt wada pao, is a vegetarian fast food dish native to the Indian state of Maharashtra"
        self.assertTrue(is_valid_quote_match(quote_similar, source_p))

        # Completely unrelated quote
        quote_unrelated = "BioCorp reported Q3 revenue of $185 million."
        self.assertFalse(is_valid_quote_match(quote_unrelated, source_p))

    def test_override_only_insufficient_when_both_find_nothing_with_informative_finding(self):
        """Override only produces Insufficient when both find nothing, with informative finding text."""
        unrelated_claim = ClaimItem(
            id="clm_unrelated",
            claim_number=1,
            text="BioCorp reported total Q3 revenue of $185 million.",
            start_offset=0,
            end_offset=45,
            verdict=VerdictEnum.SUPPORTED, # Pretend model wrongly flagged supported without evidence
            category=ClaimCategoryEnum.NUMERICAL,
            explanation="",
            confidence_score=0.8,
            confidence_basis="",
            supporting_evidence=[]
        )
        report = AuditReport(
            id="test_rpt_unrelated",
            title="Unrelated Audit",
            created_at="2026-10-11T00:00:00Z",
            status=AuditStatusEnum.VERIFYING_CLAIMS,
            answer_text="BioCorp reported total Q3 revenue of $185 million.",
            source_documents=[self.doc],
            claims=[unrelated_claim],
            summary=AuditSummary(total_claims=1)
        )
        validated = validate_audit_report(report)
        final_claim = validated.claims[0]

        self.assertEqual(final_claim.verdict, VerdictEnum.INSUFFICIENT_EVIDENCE)
        self.assertIn("No source passage covers:", final_claim.explanation)
        self.assertIn("185", final_claim.explanation.lower())

    def test_contradiction_detection_with_differing_key_token(self):
        """Key token difference should produce CONTRADICTED with evidence."""
        contradicted_claim = ClaimItem(
            id="clm_contra",
            claim_number=1,
            text="Vada pav is a vegetarian fast food dish native to the Indian state of Gujarat.",
            start_offset=0,
            end_offset=80,
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=ClaimCategoryEnum.FACTUAL,
            explanation="",
            confidence_score=0.0,
            confidence_basis=""
        )
        verified = verify_single_claim(contradicted_claim, self.retriever, self.options, source_documents=[self.doc])
        self.assertEqual(verified.verdict, VerdictEnum.CONTRADICTED)
        self.assertGreaterEqual(len(verified.contradicting_evidence), 1)

    def test_dynamic_traceability_computation(self):
        """Traceable must be computed as claims with at least 1 evidence divided by total claims."""
        from backend.models import EvidenceQuote
        eq = EvidenceQuote(
            id="ev1",
            source_id=self.doc.id,
            filename=self.doc.filename,
            passage_id=self.doc.passages[0].id,
            text=self.doc.passages[0].text,
            exact_match_verified=True
        )
        claims = [
            ClaimItem(
                id="c1", claim_number=1, text="c1", start_offset=0, end_offset=2,
                verdict=VerdictEnum.SUPPORTED,
                category=ClaimCategoryEnum.FACTUAL,
                explanation="ok",
                confidence_score=0.9,
                confidence_basis="test",
                supporting_evidence=[eq]  # 1 evidence
            ),
            ClaimItem(
                id="c2", claim_number=2, text="c2", start_offset=0, end_offset=2,
                verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
                category=ClaimCategoryEnum.FACTUAL,
                explanation="",
                confidence_score=0.5,
                confidence_basis="test",
                supporting_evidence=[]  # 0 evidence
            ),
            ClaimItem(
                id="c3", claim_number=3, text="c3", start_offset=0, end_offset=2,
                verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
                category=ClaimCategoryEnum.FACTUAL,
                explanation="",
                confidence_score=0.5,
                confidence_basis="test",
                supporting_evidence=[]  # 0 evidence
            )
        ]
        report = AuditReport(
            id="test_rpt_trace",
            title="Traceability Test",
            created_at="2026-10-11T00:00:00Z",
            status=AuditStatusEnum.VERIFYING_CLAIMS,
            answer_text="test",
            source_documents=[self.doc],
            claims=claims,
            summary=AuditSummary(total_claims=3)
        )
        validated = validate_audit_report(report)
        # 1 claim out of 3 has evidence -> 33.3%
        self.assertEqual(validated.summary.traceable_claims_count, 1)
        self.assertEqual(validated.summary.traceability_percentage, 33.3)

if __name__ == "__main__":
    unittest.main()
