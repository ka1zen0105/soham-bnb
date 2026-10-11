from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class VerdictEnum(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    MIXED = "MIXED"

class SeverityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ClaimCategoryEnum(str, Enum):
    FACTUAL = "FACTUAL"
    NUMERICAL = "NUMERICAL"
    REASONING = "REASONING"
    SAFETY = "SAFETY"

class EvidenceRelationshipEnum(str, Enum):
    ENTAILS = "ENTAILS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"

class AuditStatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING_SOURCES = "PROCESSING_SOURCES"
    EXTRACTING_CLAIMS = "EXTRACTING_CLAIMS"
    RETRIEVING_EVIDENCE = "RETRIEVING_EVIDENCE"
    VERIFYING_CLAIMS = "VERIFYING_CLAIMS"
    PREPARING_REPORT = "PREPARING_REPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Passage(BaseModel):
    id: str
    source_id: str
    filename: str
    page_number: Optional[int] = 1
    passage_number: int
    text: str
    char_start: int
    char_end: int

class SourceDocument(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    extracted_text: str
    page_count: int
    passage_count: int
    passages: List[Passage] = []
    source_url: Optional[str] = None

class EvidenceQuote(BaseModel):
    id: str
    source_id: str
    source_type: str = "uploaded_document"
    url: Optional[str] = None
    filename: str
    page_number: Optional[int] = 1
    passage_id: str
    text: str
    similarity_score: float = 0.0
    relationship: EvidenceRelationshipEnum = EvidenceRelationshipEnum.ENTAILS
    is_contradiction: bool = False
    exact_match_verified: bool = True
    retrieval_timestamp: Optional[str] = None
    context_before: Optional[str] = ""
    context_after: Optional[str] = ""
    extraction_error: Optional[str] = None

class NumericalDiscrepancy(BaseModel):
    has_discrepancy: bool = False
    claim_numbers: List[str] = []
    source_numbers: List[str] = []
    metric_type: Optional[str] = None
    percentage_error: Optional[float] = None
    detail: Optional[str] = None

class ReasoningIssue(BaseModel):
    issue_type: str
    description: str
    severity: SeverityEnum = SeverityEnum.MEDIUM

class SafetyIssue(BaseModel):
    issue_type: str
    description: str
    recommendation: str
    severity: SeverityEnum = SeverityEnum.HIGH

class ClaimItem(BaseModel):
    id: str
    claim_number: int
    text: str
    start_offset: int
    end_offset: int
    verdict: VerdictEnum
    category: ClaimCategoryEnum
    explanation: str
    supporting_evidence: List[EvidenceQuote] = []
    contradicting_evidence: List[EvidenceQuote] = []
    confidence_score: float
    confidence_basis: str
    suggested_correction: Optional[str] = None
    severity: SeverityEnum = SeverityEnum.LOW
    numerical_analysis: Optional[NumericalDiscrepancy] = None
    reasoning_issues: List[ReasoningIssue] = []
    safety_issues: List[SafetyIssue] = []
    sub_claims: List[Dict[str, Any]] = []
    provenance_audit: Optional[Dict[str, Any]] = None

class AuditSummary(BaseModel):
    total_claims: int = 0
    supported_count: int = 0
    contradicted_count: int = 0
    insufficient_count: int = 0
    conflicting_count: int = 0
    ambiguous_count: int = 0
    mixed_count: int = 0
    reasoning_issue_count: int = 0
    safety_issue_count: int = 0
    overall_assessment: str = ""
    key_findings: List[str] = []
    traceable_claims_count: int = 0
    traceability_percentage: float = 0.0

class AuditOptions(BaseModel):
    verify_sources: bool = True
    reasoning_checks: bool = True
    safety_review: bool = True
    external_verification: bool = False
    custom_gemini_api_key: Optional[str] = None

class AuditCreateRequest(BaseModel):
    title: Optional[str] = "Untitled Audit"
    answer_text: str
    source_text: Optional[str] = None
    source_document_ids: List[str] = []
    options: AuditOptions = AuditOptions()

class AuditReport(BaseModel):
    id: str
    title: str
    created_at: str
    status: AuditStatusEnum
    current_step: str = ""
    progress_percentage: int = 0
    error_message: Optional[str] = None
    answer_text: str
    source_documents: List[SourceDocument] = []
    claims: List[ClaimItem] = []
    summary: AuditSummary = AuditSummary()
    options: AuditOptions = AuditOptions()

class AuditListItem(BaseModel):
    id: str
    title: str
    created_at: str
    status: AuditStatusEnum
    total_claims: int
    contradicted_count: int
    supported_count: int
    insufficient_count: int
    ambiguous_count: int
    conflicting_count: int = 0
    source_doc_count: int

class SettingsConfig(BaseModel):
    gemini_api_key_configured: bool = False
    gemini_model: str = "gemini-2.5-flash"
    default_verify_sources: bool = True
    default_reasoning_checks: bool = True
    default_safety_review: bool = True
    retention_days: int = 30
    version: str = "1.0.0"
    python_version: str = "3.12"
    engine_mode: str = "Deterministic Hybrid Verification Engine"
    disclaimer: str = "Second Opinion evaluates claims strictly against provided source passages. Automated verdicts indicate evidentiary grounding and should accompany expert human review."
