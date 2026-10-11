import React, { useEffect, useState } from 'react';
import { 
  Search, 
  Trash2, 
  Clock, 
  AlertCircle, 
  FileText,
  RefreshCw,
  ChevronRight
} from 'lucide-react';
import type { AuditListItem } from '../types';
import { fetchAuditsList, deleteAudit } from '../services/api';
import { getSavedAuditsFromStorage, removeAuditFromStorage } from '../services/auditStorage';

interface HistoryPageProps {
  navigate: (route: string) => void;
}

export const HistoryPage: React.FC<HistoryPageProps> = ({ navigate }) => {
  const [audits, setAudits] = useState<AuditListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadAudits = async () => {
    try {
      setLoading(true);
      setError(null);
      let serverAudits: AuditListItem[] = [];
      try {
        serverAudits = await fetchAuditsList();
      } catch (err) {
        console.warn('Server fetchAuditsList failed, falling back to browser storage:', err);
      }

      // Read saved audits from browser localStorage
      const localAudits = getSavedAuditsFromStorage();

      // Combine server audits and local audits, preferring freshest records
      const auditMap = new Map<string, AuditListItem>();

      // Put local audits in map first
      for (const la of localAudits) {
        auditMap.set(la.id, la);
      }

      // Put server audits in map (server takes precedence if present)
      for (const sa of serverAudits) {
        auditMap.set(sa.id, sa);
      }

      const combined = Array.from(auditMap.values());
      setAudits(combined);
    } catch (err: any) {
      const fallback = getSavedAuditsFromStorage();
      if (fallback.length > 0) {
        setAudits(fallback);
      } else {
        setError(err.message || 'Failed to load audit history');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudits();
  }, []);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete audit '${id}'? This will permanently remove its claim ledger.`)) {
      return;
    }

    try {
      setDeletingId(id);
      // Attempt server deletion; if server returns 404 or fails on ephemeral serverless instance, don't block
      try {
        await deleteAudit(id);
      } catch (err) {
        console.warn('Server audit deletion failed or not found, removing locally:', err);
      }

      // Remove from browser storage (sessionStorage and localStorage)
      removeAuditFromStorage(id);

      setAudits(prev => prev.filter(a => a.id !== id));
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const filteredAudits = audits
    .filter(a => {
      if (searchTerm.trim() && !a.title.toLowerCase().includes(searchTerm.toLowerCase()) && !a.id.toLowerCase().includes(searchTerm.toLowerCase())) {
        return false;
      }
      if (statusFilter !== 'ALL' && a.status !== statusFilter) {
        return false;
      }
      return true;
    })
    .sort((a, b) => {
      if (sortOrder === 'desc') {
        return b.created_at.localeCompare(a.created_at);
      }
      return a.created_at.localeCompare(b.created_at);
    });

  return (
    <div className="w-full max-w-[1200px] mx-auto px-6 lg:px-10 py-9 space-y-7">
      {/* Title & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-extrabold text-[var(--ink)] tracking-tight">
            Audit History Ledger
          </h1>
          <p className="text-[14px] text-[var(--text-secondary)] mt-1 font-medium">
            Searchable historical verification sessions recorded in second_opinion.db
          </p>
        </div>

        <button
          type="button"
          onClick={loadAudits}
          className="flex items-center gap-2 h-[38px] px-3.5 bg-[var(--surface)] hover:bg-[var(--surface-hover)] border border-[var(--line)] text-[12.5px] font-bold text-[var(--ink)] rounded-[10px] transition-colors self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[var(--accent)]' : ''}`} />
          <span>Refresh Ledger</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center gap-3 bg-[var(--surface)] p-3.5 rounded-[16px] border border-[var(--line)]">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-[var(--text-secondary)]" />
          <input
            type="text"
            placeholder="Search audits by title, topic, or audit ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full h-[38px] pl-9 pr-4 text-[13px] bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] focus:outline-none focus:ring-2 focus:ring-[var(--ink)] text-[var(--ink)] placeholder:text-[var(--text-secondary)]"
          />
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-[38px] text-[12px] font-semibold bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] py-1.5 px-3 focus:outline-none text-[var(--ink)]"
          >
            <option value="ALL">All Statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="FAILED">Failed</option>
            <option value="PENDING">Pending</option>
          </select>

          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as any)}
            className="h-[38px] text-[12px] font-semibold bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] py-1.5 px-3 focus:outline-none text-[var(--ink)]"
          >
            <option value="desc">Newest First</option>
            <option value="asc">Oldest First</option>
          </select>
        </div>
      </div>

      {/* Audits Full-Width Table Card */}
      <div className="bg-[var(--surface)] rounded-[16px] border border-[var(--line)] overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-[var(--text-secondary)] text-[13px]">
            <Clock className="w-5 h-5 mx-auto mb-2 animate-spin text-[var(--accent)]" />
            Loading historical records...
          </div>
        ) : error ? (
          <div className="p-8 text-center text-[var(--contradicted-text)] text-[13px]">
            <AlertCircle className="w-5 h-5 mx-auto mb-2 text-[var(--contradicted-dot)]" />
            {error}
          </div>
        ) : filteredAudits.length === 0 ? (
          <div className="p-16 text-center text-[var(--text-secondary)] text-[13px]">
            No audits match your search query.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[var(--text-secondary)] text-[11px] font-bold uppercase tracking-wider border-b border-[var(--line)] bg-[var(--surface-alt)]">
                <tr>
                  <th className="py-3 px-5">Audit Name</th>
                  <th className="py-3 px-4 font-mono">ID</th>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4 text-center">Sources</th>
                  <th className="py-3 px-4 text-center">Claims</th>
                  <th className="py-3 px-4 text-center">Contradictions</th>
                  <th className="py-3 px-4 text-center">Supported</th>
                  <th className="py-3 px-4 text-center">Ungrounded</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line)]">
                {filteredAudits.map((a) => (
                  <tr
                    key={a.id}
                    onClick={() => navigate(`/audit/${a.id}`)}
                    className="hover:bg-[var(--surface-hover)] transition-colors cursor-pointer group"
                  >
                    <td className="py-3.5 px-5 font-bold text-[var(--ink)]">
                      <div className="flex items-center gap-2.5">
                        <FileText className="w-4 h-4 text-[var(--text-secondary)] group-hover:text-[var(--ink)] shrink-0 transition-colors" />
                        <span className="truncate max-w-[280px]">{a.title}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-[12px] text-[var(--text-secondary)]">
                      {a.id}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-[12px] text-[var(--text-secondary)]">
                      {a.created_at}
                    </td>
                    <td className="py-3.5 px-4 text-center font-mono text-[12px] text-[var(--text-body)]">
                      {a.source_doc_count}
                    </td>
                    <td className="py-3.5 px-4 text-center font-mono font-bold text-[var(--ink)]">
                      {a.total_claims}
                    </td>
                    <td className="py-3.5 px-4 text-center font-mono">
                      {a.contradicted_count > 0 ? (
                        <span className="font-bold text-[var(--contradicted-text)]">
                          {a.contradicted_count}
                        </span>
                      ) : (
                        <span className="text-[var(--text-secondary)]">0</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-center font-mono font-bold text-[var(--supported-text)]">
                      {a.supported_count}
                    </td>
                    <td className="py-3.5 px-4 text-center font-mono text-[var(--insufficient-text)] font-semibold">
                      {a.insufficient_count}
                    </td>
                    <td className="py-3.5 px-4">
                      {a.status === 'COMPLETED' ? (
                        <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-[var(--supported-text)]">
                          <span className="w-2 h-2 rounded-full bg-[var(--supported-dot)]" />
                          <span>Completed</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-[var(--contradicted-text)]">
                          <span className="w-2 h-2 rounded-full bg-[var(--contradicted-dot)]" />
                          <span>Failed</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-5 text-right">
                      <div className="flex items-center justify-end gap-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/audit/${a.id}`);
                          }}
                          className="text-[12px] text-[var(--ink)] hover:text-[var(--accent-text)] font-bold inline-flex items-center gap-1 transition-colors"
                        >
                          <span>Review</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDelete(a.id, e)}
                          disabled={deletingId === a.id}
                          aria-label={`Delete audit ${a.id}`}
                          className="text-[var(--text-secondary)] hover:text-[var(--contradicted-text)] p-1.5 rounded-[8px] hover:bg-[var(--contradicted-tint)] transition-colors"
                          title="Delete audit from database"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
