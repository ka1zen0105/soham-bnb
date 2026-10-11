import unittest
import asyncio
from fastapi import BackgroundTasks, HTTPException

from backend.main import get_audit_inputs, rerun_audit, create_audit, paste_source_text
from backend.models import (
    AuditCreateRequest, AuditRerunRequest, AuditOptions, AuditReport,
    AuditStatusEnum, SourceDocument, EditedDocumentInput
)
from backend.audit_repository import save_audit, get_audit, delete_audit, save_source_doc, get_source_doc

class TestAuditRerunAndInputs(unittest.TestCase):

    def test_get_audit_inputs_and_rerun(self):
        bg = BackgroundTasks()

        # 1. Create an initial audit
        create_req = AuditCreateRequest(
            title="Quarterly Earnings Review 2024",
            answer_text="BioCorp reported revenue of $185 million in Q3 2024.",
            source_text="BioCorp Q3 2024 actual revenue was $162 million."
        )
        orig_audit = asyncio.run(create_audit(create_req, bg))
        orig_id = orig_audit.id
        self.assertTrue(len(orig_audit.source_documents) >= 1)
        orig_doc_id = orig_audit.source_documents[0].id

        # 2. Add a second document via paste endpoint
        doc2_dict = paste_source_text({
            "text": "Second reference material on clinical operations.",
            "filename": "Clinical_Notes.txt"
        })
        doc2_id = doc2_dict["id"]

        # Attach doc2 to the original audit and mark completed
        orig_report = get_audit(orig_id)
        doc2_obj = get_source_doc(doc2_id)
        orig_report.source_documents.append(doc2_obj)
        orig_report.status = AuditStatusEnum.COMPLETED
        save_audit(orig_report)

        # 3. Test GET /api/audits/{id}/inputs
        inputs_data = get_audit_inputs(orig_id)
        self.assertEqual(inputs_data.audit_id, orig_id)
        self.assertEqual(inputs_data.title, "Quarterly Earnings Review 2024")
        self.assertEqual(inputs_data.answer_text, "BioCorp reported revenue of $185 million in Q3 2024.")
        self.assertEqual(len(inputs_data.source_documents), 2)
        self.assertTrue(bool(inputs_data.source_documents[0].extracted_text))
        self.assertTrue(bool(inputs_data.source_documents[0].filename))

        # 4. Test POST /api/audits/{id}/rerun: Edit text and remove doc2 (keep only orig_doc_id)
        edited_text = "BioCorp reported actual revenue of $162 million in Q3 2024."
        rerun_req = AuditRerunRequest(
            title="Quarterly Earnings Review 2024 (Revised)",
            answer_text=edited_text,
            source_document_ids=[orig_doc_id]  # Only kept orig_doc_id
        )
        new_audit = asyncio.run(rerun_audit(orig_id, rerun_req, bg))
        new_id = new_audit.id

        # Check new audit properties
        self.assertNotEqual(new_id, orig_id)
        self.assertEqual(new_audit.parent_audit_id, orig_id)
        self.assertEqual(new_audit.answer_text, edited_text)
        self.assertEqual(len(new_audit.source_documents), 1)
        self.assertEqual(new_audit.source_documents[0].id, orig_doc_id)

        # 5. Check original audit is completely UNCHANGED
        orig_check = get_audit(orig_id)
        self.assertIsNotNone(orig_check)
        self.assertEqual(orig_check.id, orig_id)
        self.assertEqual(orig_check.answer_text, "BioCorp reported revenue of $185 million in Q3 2024.")
        self.assertEqual(len(orig_check.source_documents), 2)
        self.assertEqual(orig_check.status, AuditStatusEnum.COMPLETED)

        # Cleanup
        delete_audit(orig_id)
        delete_audit(new_id)

    def test_rerun_with_edited_document_text(self):
        bg = BackgroundTasks()

        create_req = AuditCreateRequest(
            title="Document Edit Test",
            answer_text="Sample answer statement.",
            source_text="Original document content."
        )
        orig_audit = asyncio.run(create_audit(create_req, bg))
        orig_id = orig_audit.id

        # Re-run with edited document content
        rerun_req = AuditRerunRequest(
            answer_text="Updated answer statement.",
            source_document_ids=[],
            edited_documents=[
                EditedDocumentInput(
                    filename="Updated_Source.txt",
                    text="Completely new modified reference content."
                )
            ]
        )
        new_audit = asyncio.run(rerun_audit(orig_id, rerun_req, bg))
        new_id = new_audit.id

        self.assertEqual(new_audit.parent_audit_id, orig_id)
        self.assertEqual(len(new_audit.source_documents), 1)
        self.assertEqual(new_audit.source_documents[0].filename, "Updated_Source.txt")
        self.assertEqual(new_audit.source_documents[0].extracted_text, "Completely new modified reference content.")

        # Cleanup
        delete_audit(orig_id)
        delete_audit(new_id)

    def test_rerun_error_validation(self):
        bg = BackgroundTasks()

        # 404 for nonexistent audit
        with self.assertRaises(HTTPException) as ctx404:
            asyncio.run(rerun_audit("aud_nonexistent", AuditRerunRequest(answer_text="Hello"), bg))
        self.assertEqual(ctx404.exception.status_code, 404)

        # Create valid audit to test bad input
        create_req = AuditCreateRequest(
            title="Validation Test",
            answer_text="Valid text",
            source_text="Valid source"
        )
        orig_audit = asyncio.run(create_audit(create_req, bg))
        orig_id = orig_audit.id

        # 400 for empty answer text
        with self.assertRaises(HTTPException) as ctx400_empty:
            asyncio.run(rerun_audit(
                orig_id,
                AuditRerunRequest(
                    answer_text="   ",
                    source_document_ids=[orig_audit.source_documents[0].id]
                ),
                bg
            ))
        self.assertEqual(ctx400_empty.exception.status_code, 400)

        # 400 for zero source documents
        with self.assertRaises(HTTPException) as ctx400_nodocs:
            asyncio.run(rerun_audit(
                orig_id,
                AuditRerunRequest(
                    answer_text="Some text",
                    source_document_ids=[]
                ),
                bg
            ))
        self.assertEqual(ctx400_nodocs.exception.status_code, 400)

        delete_audit(orig_id)

if __name__ == "__main__":
    unittest.main()
