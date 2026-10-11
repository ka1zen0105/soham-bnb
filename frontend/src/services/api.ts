import type { AuditReport, AuditListItem, SettingsConfig, AuditOptions } from '../types';

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

export async function uploadSourceFile(file: File): Promise<{
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  page_count: number;
  passage_count: number;
  preview_snippet: string;
}> {
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

export async function pasteSourceText(text: string, filename?: string): Promise<{
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  page_count: number;
  passage_count: number;
  preview_snippet: string;
}> {
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

export async function createAudit(payload: {
  title?: string;
  answer_text: string;
  source_text?: string;
  source_document_ids?: string[];
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
