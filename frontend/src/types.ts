export type Verdict = 
  | 'SUPPORTED' 
  | 'CONTRADICTED' 
  | 'INSUFFICIENT_EVIDENCE' 
  | 'CONFLICTING_EVIDENCE'
  | 'AMBIGUOUS' 
  | 'MIXED';

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type ClaimCategory = 'FACTUAL' | 'NUMERICAL' | 'REASONING' | 'SAFETY';

export type AuditStatus = 
  | 'PENDING' 
  | 'PROCESSING_SOURCES' 
  | 'EXTRACTING_CLAIMS' 
  | 'RETRIEVING_EVIDENCE' 
  | 'VERIFYING_CLAIMS' 
  | 'PREPARING_REPORT' 
  | 'COMPLETED' 
  | 'FAILED';

export interface Passage {
  id: string;
  source_id: string;
  filename: string;
  page_number?: number;
  passage_number: number;
  text: string;
  char_start: number;
  char_end: number;
}

export interface SourceDocument {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  extracted_text: string;
  page_count: number;
  passage_count: number;
  passages?: Passage[];
  source_url?: string;
}

export interface EvidenceQuote {
  id: string;
  source_id: string;
  source_type?: string;
  url?: string;
  filename: string;
  page_number?: number;
  passage_id: string;
  text: string;
  similarity_score: number;
  relationship?: 'ENTAILS' | 'CONTRADICTS' | 'NEUTRAL';
  is_contradiction: boolean;
  exact_match_verified: boolean;
  retrieval_timestamp?: string;
  context_before?: string;
  context_after?: string;
  extraction_error?: string;
}

export interface NumericalDiscrepancy {
  has_discrepancy: boolean;
  claim_numbers: string[];
  source_numbers: string[];
  metric_type?: string;
  percentage_error?: number;
  detail?: string;
}

export interface ReasoningIssue {
  issue_type: string;
  description: string;
  severity: Severity;
}

export interface SafetyIssue {
  issue_type: string;
  description: string;
  recommendation: string;
  severity: Severity;
}

export interface ClaimItem {
  id: string;
  claim_number: number;
  text: string;
  start_offset: number;
  end_offset: number;
  verdict: Verdict;
  category: ClaimCategory;
  explanation: string;
  supporting_evidence: EvidenceQuote[];
  contradicting_evidence: EvidenceQuote[];
  confidence_score: number;
  confidence_basis: string;
  suggested_correction?: string | null;
  severity: Severity;
  numerical_analysis?: NumericalDiscrepancy | null;
  reasoning_issues: ReasoningIssue[];
  safety_issues: SafetyIssue[];
  sub_claims?: any[];
  provenance_audit?: any;
}

export interface AuditSummary {
  total_claims: number;
  supported_count: number;
  contradicted_count: number;
  insufficient_count: number;
  conflicting_count?: number;
  ambiguous_count: number;
  mixed_count: number;
  reasoning_issue_count: number;
  safety_issue_count: number;
  overall_assessment: string;
  key_findings: string[];
  traceable_claims_count?: number;
  traceability_percentage?: number;
}

export interface AuditOptions {
  verify_sources: boolean;
  reasoning_checks: boolean;
  safety_review: boolean;
  external_verification: boolean;
  custom_gemini_api_key?: string | null;
}

export interface AuditReport {
  id: string;
  title: string;
  created_at: string;
  status: AuditStatus;
  current_step: string;
  progress_percentage: number;
  error_message?: string | null;
  answer_text: string;
  source_documents: SourceDocument[];
  claims: ClaimItem[];
  summary: AuditSummary;
  options: AuditOptions;
  parent_audit_id?: string | null;
}

export interface AuditListItem {
  id: string;
  title: string;
  created_at: string;
  status: AuditStatus;
  total_claims: number;
  contradicted_count: number;
  supported_count: number;
  insufficient_count: number;
  ambiguous_count: number;
  source_doc_count: number;
  parent_audit_id?: string | null;
}

export interface AuditInputsResponse {
  audit_id: string;
  title: string;
  answer_text: string;
  options: AuditOptions;
  source_documents: SourceDocument[];
  parent_audit_id?: string | null;
}

export interface EditedDocumentInput {
  id?: string;
  filename: string;
  text: string;
}

export interface AuditRerunRequest {
  title?: string;
  answer_text: string;
  source_document_ids?: string[];
  source_text?: string;
  edited_documents?: EditedDocumentInput[];
  options?: AuditOptions;
}

export interface SettingsConfig {
  gemini_api_key_configured: boolean;
  gemini_model: string;
  default_verify_sources: boolean;
  default_reasoning_checks: boolean;
  default_safety_review: boolean;
  retention_days: number;
  version: string;
  python_version: string;
  engine_mode: string;
  disclaimer: string;
}
