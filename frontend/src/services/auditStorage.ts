import type { AuditReport, AuditListItem } from '../types';

const AUDIT_KEY_PREFIX = 'audit_';
const AUDIT_INDEX_KEY = 'saved_audit_ids';

/**
 * Safely saves an audit to both sessionStorage and localStorage.
 * Includes try/catch to gracefully handle storage quota limits or restricted browser modes.
 */
export function saveAuditToStorage(report: AuditReport): void {
  if (!report || !report.id) return;
  const key = `${AUDIT_KEY_PREFIX}${report.id}`;
  const serialized = JSON.stringify(report);

  // 1. Session Storage
  try {
    sessionStorage.setItem(key, serialized);
  } catch (err) {
    console.warn('Failed to save audit to sessionStorage:', err);
  }

  // 2. Local Storage
  try {
    localStorage.setItem(key, serialized);

    // Update index of saved IDs
    let savedIds: string[] = [];
    try {
      const rawIndex = localStorage.getItem(AUDIT_INDEX_KEY);
      if (rawIndex) {
        savedIds = JSON.parse(rawIndex);
      }
    } catch {
      savedIds = [];
    }

    if (!Array.isArray(savedIds)) savedIds = [];
    if (!savedIds.includes(report.id)) {
      savedIds.unshift(report.id);
      // Keep up to 100 recent audits in index
      localStorage.setItem(AUDIT_INDEX_KEY, JSON.stringify(savedIds.slice(0, 100)));
    }
  } catch (err) {
    console.warn('Failed to save audit to localStorage:', err);
  }
}

/**
 * Retrieves an audit from browser storage, checking sessionStorage first, then localStorage.
 */
export function getAuditFromStorage(auditId: string): AuditReport | null {
  if (!auditId) return null;
  const key = `${AUDIT_KEY_PREFIX}${auditId}`;

  // Check sessionStorage first
  try {
    const fromSession = sessionStorage.getItem(key);
    if (fromSession) {
      const parsed = JSON.parse(fromSession);
      if (parsed && parsed.id) return parsed as AuditReport;
    }
  } catch (err) {
    console.warn('Error reading audit from sessionStorage:', err);
  }

  // Fallback to localStorage
  try {
    const fromLocal = localStorage.getItem(key);
    if (fromLocal) {
      const parsed = JSON.parse(fromLocal);
      if (parsed && parsed.id) return parsed as AuditReport;
    }
  } catch (err) {
    console.warn('Error reading audit from localStorage:', err);
  }

  return null;
}

/**
 * Removes an audit from both sessionStorage and localStorage.
 */
export function removeAuditFromStorage(auditId: string): void {
  if (!auditId) return;
  const key = `${AUDIT_KEY_PREFIX}${auditId}`;

  try {
    sessionStorage.removeItem(key);
  } catch (err) {
    console.warn('Error removing audit from sessionStorage:', err);
  }

  try {
    localStorage.removeItem(key);
    const rawIndex = localStorage.getItem(AUDIT_INDEX_KEY);
    if (rawIndex) {
      const savedIds: string[] = JSON.parse(rawIndex);
      if (Array.isArray(savedIds)) {
        const nextIds = savedIds.filter(id => id !== auditId);
        localStorage.setItem(AUDIT_INDEX_KEY, JSON.stringify(nextIds));
      }
    }
  } catch (err) {
    console.warn('Error removing audit from localStorage:', err);
  }
}

/**
 * Converts a stored full AuditReport into an AuditListItem for history views.
 */
export function reportToListItem(report: AuditReport): AuditListItem {
  const claims = report.claims || [];
  const summary = report.summary;

  let total_claims = summary?.total_claims ?? claims.length;
  let contradicted_count = summary?.contradicted_count ?? 0;
  let supported_count = summary?.supported_count ?? 0;
  let insufficient_count = summary?.insufficient_count ?? 0;
  let ambiguous_count = summary?.ambiguous_count ?? 0;
  let conflicting_count = summary?.conflicting_count ?? 0;

  if (!summary || (total_claims === 0 && claims.length > 0)) {
    total_claims = claims.length;
    contradicted_count = claims.filter(c => c.verdict === 'CONTRADICTED').length;
    supported_count = claims.filter(c => c.verdict === 'SUPPORTED').length;
    insufficient_count = claims.filter(c => c.verdict === 'INSUFFICIENT_EVIDENCE').length;
    ambiguous_count = claims.filter(c => c.verdict === 'AMBIGUOUS' || c.verdict === 'MIXED').length;
    conflicting_count = claims.filter(c => c.verdict === 'CONFLICTING_EVIDENCE').length;
  }

  return {
    id: report.id,
    title: report.title || 'Audit Review',
    created_at: report.created_at,
    status: report.status,
    total_claims,
    contradicted_count,
    supported_count,
    insufficient_count,
    ambiguous_count,
    conflicting_count,
    source_doc_count: report.source_documents?.length || 0,
    parent_audit_id: report.parent_audit_id
  };
}

/**
 * Retrieves all saved audits from localStorage as AuditListItems for the history ledger.
 */
export function getSavedAuditsFromStorage(): AuditListItem[] {
  const items: AuditListItem[] = [];
  const seenIds = new Set<string>();

  try {
    // 1. Check indexed IDs
    const rawIndex = localStorage.getItem(AUDIT_INDEX_KEY);
    if (rawIndex) {
      const savedIds: string[] = JSON.parse(rawIndex);
      if (Array.isArray(savedIds)) {
        for (const id of savedIds) {
          if (!seenIds.has(id)) {
            const audit = getAuditFromStorage(id);
            if (audit) {
              items.push(reportToListItem(audit));
              seenIds.add(id);
            }
          }
        }
      }
    }

    // 2. Scan any other localStorage keys starting with 'audit_aud_' in case they weren't in index
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(AUDIT_KEY_PREFIX)) {
        const id = key.slice(AUDIT_KEY_PREFIX.length);
        if (!seenIds.has(id)) {
          const audit = getAuditFromStorage(id);
          if (audit) {
            items.push(reportToListItem(audit));
            seenIds.add(id);
          }
        }
      }
    }
  } catch (err) {
    console.warn('Error reading saved audits list from localStorage:', err);
  }

  return items;
}
