import type { AuditReport, AuditListItem, SettingsConfig, AuditOptions, AuditInputsResponse, AuditRerunRequest } from '../types';

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export async function checkHealth(): Promise<{ status: string; service: string; version: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function fetchSettings(): Promise<SettingsConfig> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error('Failed to load settings');
  return res.json();
}

export async function saveSettings(payload: Partial<SettingsConfig> & { gemini_api_key?: string }): Promise<SettingsConfig> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error('Failed to save settings');
  return res.json();
}

export interface UploadedDocResponse {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  page_count: number;
  passage_count: number;
  preview_snippet: string;
  warnings?: string[];
  units?: any[];
}

export async function uploadSourceFile(file: File): Promise<UploadedDocResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/sources/upload`, {
    method: 'POST',
    body: formData
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }
  return res.json();
}

export async function pasteSourceText(text: string, filename?: string): Promise<UploadedDocResponse> {
  const res = await fetch(`${API_BASE}/sources/paste`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, filename })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Pasting source text failed' }));
    throw new Error(err.detail || 'Pasting source text failed');
  }
  return res.json();
}

export async function fetchPaperByDoiOrUrl(query: string): Promise<UploadedDocResponse> {
  const res = await fetch(`${API_BASE}/sources/fetch_paper`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch paper' }));
    throw new Error(err.detail || 'Failed to fetch paper');
  }
  return res.json();
}

export async function ingestPreParsedUnits(
  name: string,
  type: string,
  units: any[],
  warnings?: string[],
  meta?: any
): Promise<UploadedDocResponse> {
  const res = await fetch(`${API_BASE}/sources/units`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, type, units, warnings, meta })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to ingest units' }));
    throw new Error(err.detail || 'Failed to ingest units');
  }
  return res.json();
}

export async function createAudit(payload: {
  title?: string;
  answer_text: string;
  source_text?: string;
  source_document_ids?: string[];
  source_documents_data?: Array<{ id: string; filename: string; text?: string; preview_snippet?: string }>;
  options?: AuditOptions;
}): Promise<AuditReport> {
  const res = await fetch(`${API_BASE}/audits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Audit creation failed' }));
    throw new Error(err.detail || 'Audit creation failed');
  }
  return res.json();
}

export async function fetchAudit(auditId: string): Promise<AuditReport> {
  const res = await fetch(`${API_BASE}/audits/${auditId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Audit not found' }));
    throw new Error(err.detail || 'Audit not found');
  }
  return res.json();
}

export async function fetchAuditsList(): Promise<AuditListItem[]> {
  const res = await fetch(`${API_BASE}/audits`);
  if (!res.ok) throw new Error('Failed to retrieve audits list');
  return res.json();
}

export async function deleteAudit(auditId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/audits/${auditId}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error('Failed to delete audit');
}

export async function fetchDemoDataset(demoId: string): Promise<{
  title: string;
  answer_text: string;
  source_text: string;
}> {
  const res = await fetch(`${API_BASE}/demo/${demoId}`);
  if (!res.ok) throw new Error('Failed to load demo dataset');
  return res.json();
}

export async function fetchAuditInputs(auditId: string): Promise<AuditInputsResponse> {
  const res = await fetch(`${API_BASE}/audits/${auditId}/inputs`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch audit inputs' }));
    throw new Error(err.detail || 'Failed to fetch audit inputs');
  }
  return res.json();
}

export async function rerunAudit(auditId: string, payload: AuditRerunRequest): Promise<AuditReport> {
  const res = await fetch(`${API_BASE}/audits/${auditId}/rerun`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to re-run audit' }));
    throw new Error(err.detail || 'Failed to re-run audit');
  }
  return res.json();
}
