import os
import unittest
from backend.models import (
    ClaimItem, VerdictEnum, ClaimCategoryEnum, SeverityEnum, AuditOptions
)
from backend.document_processor import process_plain_text
from backend.evidence_retriever import BM25Retriever
from backend.claim_verifier import verify_single_claim

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "Albert_Einstein.txt")

class TestEinsteinVerdictAccuracy(unittest.TestCase):
    """
    Tests for verdict accuracy, footnote stripping, entity contradiction,
    document de-duplication, and multi-document conflict rules using the Albert_Einstein.txt fixture.
    """

    def setUp(self):
        self.options = AuditOptions(
            verify_sources=True,
            reasoning_checks=True,
            safety_review=True,
            external_verification=False
        )
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            self.einstein_source_text = f.read()

    def _create_claim(self, claim_id: str, text: str, category: ClaimCategoryEnum = ClaimCategoryEnum.FACTUAL) -> ClaimItem:
        return ClaimItem(
            id=claim_id,
            claim_number=1,
            text=text,
            start_offset=0,
            end_offset=len(text),
            verdict=VerdictEnum.INSUFFICIENT_EVIDENCE,
            category=category,
            explanation="",
            supporting_evidence=[],
            contradicting_evidence=[],
            confidence_score=0.0,
            confidence_basis="",
            severity=SeverityEnum.LOW
        )

    def test_01_claim_copied_from_paragraph_2_with_space_before_note1(self):
        """
        Test 1: The claim copied from paragraph 2, including the version with a space before [note 1].
        Expect: SUPPORTED, evidence is paragraph 2, sentence 1.
        """
        doc = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        retriever = BM25Retriever(doc.passages)

        claim_text = (
            "Born as a subject to the Kingdom of Württemberg, part of the German Empire, [note 1] "
            "Einstein moved to Switzerland in 1895, forsaking his citizenship the following year."
        )
        claim = self._create_claim("clm_1", claim_text)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertEqual(len(verified.supporting_evidence), 1)
        self.assertEqual(len(verified.contradicting_evidence), 0)
        
        ev = verified.supporting_evidence[0]
        # Must be paragraph 2, sentence 1 (p1_2_1)
        self.assertTrue(ev.passage_id.endswith("_p1_2_1") or "_p1_2_1" in ev.passage_id)
        self.assertIn("Switzerland", ev.text)
        self.assertIn("Kingdom of Württemberg", ev.text)
        self.assertNotIn("theoretical physicist", ev.text)
        self.assertGreaterEqual(verified.confidence_score, 0.95)
        self.assertIn("Corroborated by", verified.suggested_correction)

    def test_02_same_claim_with_england(self):
        """
        Test 2: The same claim with 'England'.
        Expect: CONTRADICTED, finding names England and Switzerland.
        """
        doc = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        retriever = BM25Retriever(doc.passages)

        claim_text = (
            "Born as a subject to the Kingdom of Württemberg, part of the German Empire, [note 1] "
            "Einstein moved to England in 1895, forsaking his citizenship the following year."
        )
        claim = self._create_claim("clm_2", claim_text)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.CONTRADICTED)
        self.assertEqual(len(verified.contradicting_evidence), 1)
        self.assertEqual(len(verified.supporting_evidence), 0)

        ev = verified.contradicting_evidence[0]
        self.assertTrue(ev.passage_id.endswith("_p1_2_1") or "_p1_2_1" in ev.passage_id)
        self.assertIn("Switzerland", ev.text)

        # Finding must record both 'England' and 'Switzerland'
        self.assertIn("England", verified.explanation)
        self.assertIn("Switzerland", verified.explanation)
        # Recommended action must not compare a file with itself
        self.assertNotIn("compare", verified.suggested_correction.lower())

    def test_03_einstein_was_born_in_1879(self):
        """
        Test 3: 'Einstein was born in 1879.'
        Expect: SUPPORTED, evidence is paragraph 1, sentence 1.
        """
        doc = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        retriever = BM25Retriever(doc.passages)

        claim = self._create_claim("clm_3", "Einstein was born in 1879.")
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertEqual(len(verified.supporting_evidence), 1)
        ev = verified.supporting_evidence[0]
        self.assertTrue(ev.passage_id.endswith("_p1_1_1") or "_p1_1_1" in ev.passage_id)
        self.assertIn("1879", ev.text)
        self.assertGreaterEqual(verified.confidence_score, 0.90)

    def test_04_nobel_prize_in_chemistry_in_1921(self):
        """
        Test 4: 'Einstein received the Nobel Prize in Chemistry in 1921.'
        Expect: CONTRADICTED, finding names Chemistry and Physics.
        """
        doc = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        retriever = BM25Retriever(doc.passages)

        claim = self._create_claim("clm_4", "Einstein received the Nobel Prize in Chemistry in 1921.")
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.CONTRADICTED)
        self.assertEqual(len(verified.contradicting_evidence), 1)
        ev = verified.contradicting_evidence[0]
        self.assertTrue(ev.passage_id.endswith("_p1_1_4") or "_p1_1_4" in ev.passage_id)
        self.assertIn("Chemistry", verified.explanation)
        self.assertIn("Physics", verified.explanation)

    def test_05_sentence_fragment_roosevelt_letter(self):
        """
        Test 5: A fragment of a longer sentence (the Roosevelt letter fragment).
        Expect: SUPPORTED, evidence is paragraph 2, sentence 8.
        """
        doc = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        retriever = BM25Retriever(doc.passages)

        claim_text = (
            "Roosevelt alerting him to the potential German nuclear weapons program and "
            "recommending that the US begin similar research, later carried out as the Manhattan Project."
        )
        claim = self._create_claim("clm_5", claim_text)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertEqual(len(verified.supporting_evidence), 1)
        ev = verified.supporting_evidence[0]
        self.assertTrue(ev.passage_id.endswith("_p1_2_8") or "_p1_2_8" in ev.passage_id)
        self.assertIn("Roosevelt", ev.text)
        self.assertGreaterEqual(verified.confidence_score, 0.95)

    def test_06_not_in_source_biocorp_revenue(self):
        """
        Test 6: A claim not in the source ('BioCorp reported total Q3 revenue of $185 million.').
        Expect: INSUFFICIENT_EVIDENCE, no evidence shown.
        """
        doc = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        retriever = BM25Retriever(doc.passages)

        claim = self._create_claim("clm_6", "BioCorp reported total Q3 revenue of $185 million.", category=ClaimCategoryEnum.NUMERICAL)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc])

        self.assertEqual(verified.verdict, VerdictEnum.INSUFFICIENT_EVIDENCE)
        self.assertEqual(len(verified.supporting_evidence), 0)
        self.assertEqual(len(verified.contradicting_evidence), 0)
        self.assertIn("No provided source supports this claim", verified.suggested_correction)

    def test_07_same_file_uploaded_twice(self):
        """
        Test 7: The same file uploaded twice.
        Expect: No CONFLICTING_EVIDENCE and no 'compare A and A'.
        """
        doc1 = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        doc2 = process_plain_text(self.einstein_source_text, "Albert Einstein (2).txt")
        retriever = BM25Retriever(doc1.passages + doc2.passages)

        claim_text = (
            "Born as a subject to the Kingdom of Württemberg, part of the German Empire, [note 1] "
            "Einstein moved to Switzerland in 1895, forsaking his citizenship the following year."
        )
        claim = self._create_claim("clm_7", claim_text)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc1, doc2])

        self.assertEqual(verified.verdict, VerdictEnum.SUPPORTED)
        self.assertNotIn("compare", verified.suggested_correction.lower())

    def test_08_two_different_documents_that_disagree(self):
        """
        Test 8: Two different documents that disagree.
        Expect: CONFLICTING_EVIDENCE naming both files.
        """
        doc1 = process_plain_text(self.einstein_source_text, "Albert Einstein (1).txt")
        alt_text = self.einstein_source_text.replace("moved to Switzerland", "moved to England")
        doc2 = process_plain_text(alt_text, "Einstein biography B.txt")
        retriever = BM25Retriever(doc1.passages + doc2.passages)

        claim_text = (
            "Born as a subject to the Kingdom of Württemberg, part of the German Empire, [note 1] "
            "Einstein moved to England in 1895, forsaking his citizenship the following year."
        )
        claim = self._create_claim("clm_8", claim_text)
        verified = verify_single_claim(claim, retriever, self.options, source_documents=[doc1, doc2])

        self.assertEqual(verified.verdict, VerdictEnum.CONFLICTING_EVIDENCE)
        self.assertIn("Albert Einstein (1).txt", verified.suggested_correction)
        self.assertIn("Einstein biography B.txt", verified.suggested_correction)
        self.assertNotIn("compare Albert Einstein (1).txt and Albert Einstein (1).txt", verified.suggested_correction)

if __name__ == "__main__":
    unittest.main()
