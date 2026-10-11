import React, { useEffect, useState, useMemo } from 'react';
import {
  ArrowLeft,
  Download,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Copy,
  Check,
  Clock,
  AlertCircle,
  Info,
  FileText,
  LayoutGrid,
  Table as TableIcon
} from 'lucide-react';
import type { AuditReport, ClaimItem, EvidenceQuote, Verdict } from '../types';
import { fetchAudit, API_BASE } from '../services/api';
import { getVerdictStyle } from '../lib/verdict';

interface AuditResultsPageProps {
  auditId: string;
  navigate: (route: string) => void;
}

export const AuditResultsPage: React.FC<AuditResultsPageProps> = ({ auditId, navigate }) => {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layout, setLayout] = useState<'deck' | 'table'>('deck');
  const [verdictFilter, setVerdictFilter] = useState<string>('ALL');
  const [searchQ, setSearchQ] = useState('');
  const [sortOrder, setSortOrder] = useState<'claim' | 'evidence'>('claim');

  // Deck view tabs & diff mode
  const [activeTab, setActiveTab] = useState<'evidence' | 'context' | 'source'>('evidence');
  const [contextMode, setContextMode] = useState<'view' | 'diff'>('view');

  // Table view expanded row
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const data = await fetchAudit(auditId);
        if (!alive) return;
        setReport(data);
        if (data.claims && data.claims.length > 0) {
          setSelectedId(data.claims[0].id);
        }
      } catch (err: any) {
        if (alive) setError(err.message || 'Failed to load audit report');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [auditId]);

  // Derived counts for tabs
  const counts = useMemo(() => {
    if (!report) return { ALL: 0, CONTRADICTED: 0, CONFLICTING_EVIDENCE: 0, INSUFFICIENT_EVIDENCE: 0, SUPPORTED: 0, AMBIGUOUS: 0 };
    const res: Record<string, number> = {
      ALL: report.claims.length,
      CONTRADICTED: 0,
      CONFLICTING_EVIDENCE: 0,
      INSUFFICIENT_EVIDENCE: 0,
      SUPPORTED: 0,
      AMBIGUOUS: 0,
    };
    report.claims.forEach(c => {
      const v = c.verdict;
      if (v === 'AMBIGUOUS' || v === 'MIXED') {
        res.AMBIGUOUS = (res.AMBIGUOUS || 0) + 1;
      } else if (res[v] !== undefined) {
        res[v] = (res[v] || 0) + 1;
      }
    });
    return res;
  }, [report]);

  // List of tabs that have at least 1 claim (plus ALL)
  const availableTabs = useMemo(() => {
    const list: { key: string; label: string; count: number }[] = [
      { key: 'ALL', label: 'All', count: counts.ALL || 0 }
    ];
    if (counts.CONTRADICTED > 0) {
      list.push({ key: 'CONTRADICTED', label: 'Contradicted', count: counts.CONTRADICTED });
    }
    if (counts.CONFLICTING_EVIDENCE > 0) {
      list.push({ key: 'CONFLICTING_EVIDENCE', label: 'Conflicting', count: counts.CONFLICTING_EVIDENCE });
    }
    if (counts.INSUFFICIENT_EVIDENCE > 0) {
      list.push({ key: 'INSUFFICIENT_EVIDENCE', label: 'Insufficient', count: counts.INSUFFICIENT_EVIDENCE });
    }
    if (counts.SUPPORTED > 0) {
      list.push({ key: 'SUPPORTED', label: 'Supported', count: counts.SUPPORTED });
    }
    if (counts.AMBIGUOUS > 0) {
      list.push({ key: 'AMBIGUOUS', label: 'Ambiguous', count: counts.AMBIGUOUS });
    }
    return list;
  }, [counts]);

  // Filtered & sorted claims
  const filteredClaims = useMemo(() => {
    if (!report) return [];
    let list = report.claims.filter(c => {
      if (verdictFilter !== 'ALL') {
        if (verdictFilter === 'AMBIGUOUS') {
          if (c.verdict !== 'AMBIGUOUS' && c.verdict !== 'MIXED') return false;
        } else if (c.verdict !== verdictFilter) {
          return false;
        }
      }
      if (searchQ.trim()) {
        const q = searchQ.toLowerCase();
        const evText = [...c.supporting_evidence, ...c.contradicting_evidence]
          .map(e => `${e.text} ${e.filename}`).join(' ').toLowerCase();
        if (!c.text.toLowerCase().includes(q) && !c.explanation.toLowerCase().includes(q) && !evText.includes(q)) {
          return false;
        }
      }
      return true;
    });

    if (sortOrder === 'evidence') {
      list = [...list].sort((a, b) => {
        const cntA = (a.supporting_evidence?.length || 0) + (a.contradicting_evidence?.length || 0);
        const cntB = (b.supporting_evidence?.length || 0) + (b.contradicting_evidence?.length || 0);
        return cntB - cntA || a.claim_number - b.claim_number;
      });
    } else {
      list = [...list].sort((a, b) => a.claim_number - b.claim_number);
    }

    return list;
  }, [report, verdictFilter, searchQ, sortOrder]);

  const focusedClaim = useMemo(() => {
    if (!report?.claims.length) return null;
    return report.claims.find(c => c.id === selectedId) || filteredClaims[0] || report.claims[0];
  }, [report, selectedId, filteredClaims]);

  const focusedIndexInFiltered = useMemo(() => {
    if (!focusedClaim) return -1;
    return filteredClaims.findIndex(c => c.id === focusedClaim.id);
  }, [filteredClaims, focusedClaim]);

  const handlePrevClaim = () => {
    if (focusedIndexInFiltered > 0) {
      setSelectedId(filteredClaims[focusedIndexInFiltered - 1].id);
    }
  };

  const handleNextClaim = () => {
    if (focusedIndexInFiltered < filteredClaims.length - 1) {
      setSelectedId(filteredClaims[focusedIndexInFiltered + 1].id);
    }
  };

  const handleCopyClaim = () => {
    if (!focusedClaim) return;
    const vStyle = getVerdictStyle(focusedClaim.verdict);
    navigator.clipboard.writeText(
      `Claim #${focusedClaim.claim_number} [${vStyle.label}]: "${focusedClaim.text}"\n\nFinding: ${focusedClaim.explanation}`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Helper when clicking a sentence in original answer
  const selectClaimFromSentence = (claimId: string) => {
    const isHidden = !filteredClaims.some(c => c.id === claimId);
    if (isHidden) {
      setVerdictFilter('ALL');
    }
    setSelectedId(claimId);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-64px)] bg-white">
        <div className="text-center">
          <Clock className="w-5 h-5 mx-auto animate-spin text-[var(--accent)]" />
          <p className="mt-2 text-[13px] text-[var(--text-secondary)] font-medium">Loading audit ledger…</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-64px)] bg-white">
        <div className="text-center max-w-sm p-6">
          <AlertCircle className="w-8 h-8 text-[var(--contradicted-dot)] mx-auto" />
          <p className="mt-3 text-[15px] font-bold text-[var(--ink)]">Unable to load audit</p>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{error || 'Report not found'}</p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 px-4 py-2 border border-[var(--line)] rounded-[10px] text-[13px] font-bold text-[var(--ink)] hover:bg-[var(--surface-hover)]"
          >
            Back to Workspace
          </button>
        </div>
      </div>
    );
  }

  const focusedVStyle = focusedClaim ? getVerdictStyle(focusedClaim.verdict) : null;
  const allEvidence = focusedClaim 
    ? [...(focusedClaim.contradicting_evidence || []), ...(focusedClaim.supporting_evidence || [])]
    : [];

  return (
    <div className="min-h-[calc(100vh-64px)] flex flex-col bg-white text-[var(--ink)]">
      
      {/* ══ 1. Page Header (White, bottom hairline, padding 24px 40px 22px) ══ */}
      <header className="bg-white border-b border-[var(--line)] p-[24px_40px_22px] flex flex-col gap-3 shrink-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          
          {/* Left: back button + title + Completed pill + mono ID */}
          <div className="flex items-start sm:items-center gap-3.5 min-w-0">
            <button
              onClick={() => navigate('/')}
              aria-label="Back to workspace"
              className="w-[38px] h-[38px] rounded-[10px] border border-[var(--line)] bg-white flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--ink)] hover:bg-[var(--surface-hover)] transition-colors shrink-0"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>

            <div className="min-w-0">
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-[22px] font-extrabold text-[var(--ink)] tracking-tight leading-tight">
                  {report.title}
                </h1>
                
                {/* Completed pill: green dot + text on --supported-tint */}
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[12px] font-bold bg-[var(--supported-tint)] text-[var(--supported-text)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--supported-dot)]" />
                  <span>Completed</span>
                </span>

                {/* Audit ID mono chip */}
                <span className="text-[12px] font-mono text-[var(--text-secondary)] bg-[#F2F4F7] px-2 py-0.5 rounded-[6px]">
                  {report.id}
                </span>
              </div>

              {/* Timestamp / source count / claim count line */}
              <p className="text-[12px] font-mono text-[var(--text-secondary)] mt-1">
                {report.created_at} · {report.source_documents?.length || 1} source{(report.source_documents?.length || 1) !== 1 ? 's' : ''} · {report.claims.length} claims
              </p>
            </div>
          </div>

          {/* Right: Deck / Table switch + Export button (no verdict count pills) */}
          <div className="flex items-center gap-3 self-start sm:self-auto shrink-0">
            {/* Deck / Table switch */}
            <div className="bg-[#F2F4F7] p-[3px] rounded-[10px] flex items-center gap-1">
              <button
                onClick={() => setLayout('deck')}
                aria-pressed={layout === 'deck'}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-[12px] rounded-[8px] transition-colors ${
                  layout === 'deck'
                    ? 'bg-white text-[var(--ink)] font-bold shadow-xs'
                    : 'text-[var(--text-secondary)] hover:text-[var(--ink)] font-semibold'
                }`}
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                <span>Deck</span>
              </button>
              <button
                onClick={() => setLayout('table')}
                aria-pressed={layout === 'table'}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-[12px] rounded-[8px] transition-colors ${
                  layout === 'table'
                    ? 'bg-white text-[var(--ink)] font-bold shadow-xs'
                    : 'text-[var(--text-secondary)] hover:text-[var(--ink)] font-semibold'
                }`}
              >
                <TableIcon className="w-3.5 h-3.5" />
                <span>Table</span>
              </button>
            </div>

            {/* Export button */}
            <a
              href={`${API_BASE}/audits/${report.id}/export/markdown`}
              download
              className="h-[38px] px-3.5 border border-[var(--line)] rounded-[10px] bg-white text-[var(--ink)] hover:bg-[var(--surface-hover)] text-[12px] font-bold inline-flex items-center gap-2 transition-colors"
              title="Download audit as Markdown"
            >
              <Download className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
              <span>Export</span>
            </a>
          </div>
        </div>

        {/* Assessment sentence: no boxed banner */}
        {report.summary?.overall_assessment && (
          <div className="flex items-center gap-2 text-[13px] text-[var(--text-body)] pt-1">
            <Info className="w-4 h-4 text-[var(--accent-text)] shrink-0" />
            <p className="truncate">
              <strong className="text-[var(--ink)] font-bold">Assessment.</strong> {report.summary.overall_assessment}
            </p>
          </div>
        )}
      </header>

      {/* ══ 2. DECK VIEW ═══════════════════════════════════════════════════ */}
      {layout === 'deck' && (
        <div className="flex flex-col lg:flex-row flex-1 overflow-hidden">
          
          {/* Left Column: Claim Ledger (360px wide, right hairline border) */}
          <aside className="w-full lg:w-[380px] shrink-0 border-r border-[var(--line)] flex flex-col bg-white">
            
            {/* Header row: "Claim ledger" + Sort select */}
            <div className="p-[16px_20px_12px] border-b border-[var(--line)] flex items-center justify-between gap-3">
              <h2 className="text-[14px] font-extrabold text-[var(--ink)]">
                Claim ledger
              </h2>
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[var(--text-secondary)] font-medium">Sort</span>
                <select
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value as any)}
                  aria-label="Sort claims"
                  className="text-[12px] font-medium bg-[var(--surface-alt)] border border-[var(--line)] rounded-[8px] py-1 px-2 text-[var(--ink)] focus:outline-none"
                >
                  <option value="claim">Claim order</option>
                  <option value="evidence">Most evidence</option>
                </select>
              </div>
            </div>

            {/* Verdict filter as underlined text tabs with counts */}
            <div className="flex items-center gap-4 px-5 border-b border-[var(--line)] overflow-x-auto no-scrollbar">
              {availableTabs.map((tab) => {
                const isActive = verdictFilter === tab.key;
                return (
                  <button
                    key={tab.key}
                    onClick={() => setVerdictFilter(tab.key)}
                    aria-pressed={isActive}
                    className={`py-2.5 text-[12.5px] whitespace-nowrap transition-colors border-b-2 ${
                      isActive
                        ? 'border-[var(--ink)] text-[var(--ink)] font-bold'
                        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--ink)] font-medium'
                    }`}
                  >
                    <span>{tab.label}</span>
                    <span className="ml-1 text-[11px] text-[var(--text-secondary)] font-normal">
                      · {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Claim search input: 38px high, --surface-alt, hairline border */}
            <div className="p-3 border-b border-[var(--line)]">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-[var(--text-secondary)] absolute left-3 top-3 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search claims..."
                  value={searchQ}
                  onChange={(e) => setSearchQ(e.target.value)}
                  className="w-full h-[38px] pl-8 pr-3 text-[13px] bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[var(--ink)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--ink)]"
                />
              </div>
            </div>

            {/* Vertical list of claims: no card borders, no colored borders */}
            <div className="flex-1 overflow-y-auto divide-y divide-[var(--line)]">
              {filteredClaims.length === 0 ? (
                <div className="p-8 text-center text-[13px] text-[var(--text-secondary)]">
                  No claims match this filter.
                </div>
              ) : (
                filteredClaims.map((c) => {
                  const isSelected = c.id === focusedClaim?.id;
                  const vStyle = getVerdictStyle(c.verdict);
                  const evCount = (c.supporting_evidence?.length || 0) + (c.contradicting_evidence?.length || 0);

                  return (
                    <button
                      key={c.id}
                      onClick={() => setSelectedId(c.id)}
                      className={`w-full text-left p-4 transition-colors ${
                        isSelected ? 'bg-[var(--surface-hover)]' : 'hover:bg-[var(--surface-alt)]'
                      }`}
                    >
                      {/* Line 1: Claim number (mono, secondary), verdict dot + label, N evidence right */}
                      <div className="flex items-center justify-between text-[11.5px] leading-tight">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[var(--text-secondary)]">#{c.claim_number}</span>
                          <span className="flex items-center gap-1 font-semibold" style={{ color: vStyle.text }}>
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: vStyle.dot }} />
                            <span>{vStyle.shortLabel}</span>
                          </span>
                        </div>
                        <span className="font-mono text-[var(--text-secondary)] text-[11px]">
                          {evCount} evidence
                        </span>
                      </div>

                      {/* Line 2: Claim text clamped to two lines (14px) */}
                      <p className="text-[13.5px] font-medium text-[var(--ink)] line-clamp-2 mt-1.5 leading-snug">
                        {c.text}
                      </p>
                    </button>
                  );
                })
              )}
            </div>
          </aside>

          {/* Right Column: Focused Claim (padding 28px 44px 48px, max-w-[780px]) */}
          <main className="flex-1 overflow-y-auto p-[28px_44px_48px] bg-white">
            {focusedClaim && focusedVStyle ? (
              <div className="max-w-[780px] space-y-6">
                
                {/* Top row: "Claim X of Y" + prev/next buttons */}
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium text-[var(--text-secondary)]">
                    Claim {focusedIndexInFiltered >= 0 ? focusedIndexInFiltered + 1 : 1} of {filteredClaims.length}
                  </span>
                  
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={handlePrevClaim}
                      disabled={focusedIndexInFiltered <= 0}
                      aria-label="Previous claim"
                      className="w-[36px] h-[36px] rounded-[8px] border border-[var(--line)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--ink)] hover:bg-[var(--surface-hover)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <button
                      onClick={handleNextClaim}
                      disabled={focusedIndexInFiltered >= filteredClaims.length - 1}
                      aria-label="Next claim"
                      className="w-[36px] h-[36px] rounded-[8px] border border-[var(--line)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--ink)] hover:bg-[var(--surface-hover)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Verdict pill + claim id/type mono + Copy claim ghost button */}
                <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
                  <div className="flex items-center gap-2.5">
                    {/* Verdict pill */}
                    <span
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-bold"
                      style={{ backgroundColor: focusedVStyle.tint, color: focusedVStyle.text }}
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: focusedVStyle.dot }} />
                      <span>{focusedVStyle.label}</span>
                    </span>

                    {/* Claim info in mono */}
                    <span className="text-[12px] font-mono text-[var(--text-secondary)]">
                      #{focusedClaim.claim_number} · {focusedClaim.category}
                    </span>
                  </div>

                  {/* Copy claim button */}
                  <button
                    onClick={handleCopyClaim}
                    className="flex items-center gap-1 text-[12px] font-semibold text-[var(--text-secondary)] hover:text-[var(--ink)] transition-colors py-1 px-2 rounded-[6px] hover:bg-[var(--surface-hover)]"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-[var(--accent-text)]" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? 'Copied' : 'Copy claim'}</span>
                  </button>
                </div>

                {/* Claim heading: 22px, weight 700, line-height 1.4 */}
                <h3 className="text-[22px] font-bold text-[var(--ink)] leading-[1.4] tracking-tight">
                  "{focusedClaim.text}"
                </h3>

                {/* Underlined tabs: Evidence, In context, Source file */}
                <div className="border-b border-[var(--line)] flex items-center gap-6">
                  <button
                    onClick={() => setActiveTab('evidence')}
                    aria-pressed={activeTab === 'evidence'}
                    className={`pb-3 text-[14px] transition-colors border-b-2 ${
                      activeTab === 'evidence'
                        ? 'border-[var(--ink)] text-[var(--ink)] font-bold'
                        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--ink)] font-semibold'
                    }`}
                  >
                    Evidence
                  </button>
                  <button
                    onClick={() => setActiveTab('context')}
                    aria-pressed={activeTab === 'context'}
                    className={`pb-3 text-[14px] transition-colors border-b-2 ${
                      activeTab === 'context'
                        ? 'border-[var(--ink)] text-[var(--ink)] font-bold'
                        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--ink)] font-semibold'
                    }`}
                  >
                    In context
                  </button>
                  <button
                    onClick={() => setActiveTab('source')}
                    aria-pressed={activeTab === 'source'}
                    className={`pb-3 text-[14px] transition-colors border-b-2 ${
                      activeTab === 'source'
                        ? 'border-[var(--ink)] text-[var(--ink)] font-bold'
                        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--ink)] font-semibold'
                    }`}
                  >
                    Source file
                  </button>
                </div>

                {/* TAB 1: Evidence (default) */}
                {activeTab === 'evidence' && (
                  <div className="space-y-6 pt-1">
                    {/* Verdict and finding */}
                    <div>
                      <span className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-[var(--text-secondary)] block mb-1">
                        VERDICT AND FINDING
                      </span>
                      <p className="text-[15px] leading-[1.65] text-[var(--ink)] font-normal">
                        {focusedClaim.explanation}
                      </p>
                    </div>

                    {/* Source evidence */}
                    <div>
                      <span className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-[var(--text-secondary)] block mb-3">
                        SOURCE EVIDENCE · {allEvidence.length}
                      </span>

                      {allEvidence.length === 0 ? (
                        <p className="text-[13px] text-[var(--text-secondary)] italic">
                          No direct evidence quotes were identified for this assertion in the supplied material.
                        </p>
                      ) : (
                        <div className="divide-y divide-[var(--line)]">
                          {allEvidence.map((ev, i) => (
                            <div key={i} className="py-4 space-y-2 first:pt-0">
                              <blockquote className="font-serif italic text-[18px] leading-[1.7] text-[var(--ink)]">
                                "{ev.text}"
                              </blockquote>
                              <div className="text-[12px] font-mono text-[var(--text-secondary)]">
                                {ev.filename} {ev.page_number ? `· Page ${ev.page_number}` : ''} {ev.passage_id ? `· Passage ${ev.passage_id}` : ''}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* TAB 2: In context (full original answer with sentence click or diff) */}
                {activeTab === 'context' && (
                  <div className="space-y-4 pt-1">
                    {/* Header bar: instruction on left, View/Diff on right */}
                    <div className="flex items-center justify-between pb-2 border-b border-[var(--line-soft)]">
                      <span className="text-[12px] text-[var(--text-secondary)] font-medium">
                        Click highlighted text to select a claim
                      </span>

                      <div className="bg-[#F2F4F7] p-[2px] rounded-[8px] flex items-center gap-1">
                        <button
                          onClick={() => setContextMode('view')}
                          className={`px-2.5 py-1 text-[11px] font-bold rounded-[6px] transition-colors ${
                            contextMode === 'view' ? 'bg-white text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)]'
                          }`}
                        >
                          View
                        </button>
                        <button
                          onClick={() => setContextMode('diff')}
                          className={`px-2.5 py-1 text-[11px] font-bold rounded-[6px] transition-colors ${
                            contextMode === 'diff' ? 'bg-white text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)]'
                          }`}
                        >
                          Diff
                        </button>
                      </div>
                    </div>

                    {/* Content */}
                    {contextMode === 'view' ? (
                      <div className="text-[16px] leading-[2] text-[var(--ink)] whitespace-pre-wrap font-normal">
                        {report.claims.map((c) => {
                          const isSel = c.id === focusedClaim.id;
                          const vStyle = getVerdictStyle(c.verdict);

                          return (
                            <button
                              key={c.id}
                              type="button"
                              onClick={() => selectClaimFromSentence(c.id)}
                              className={`inline text-left cursor-pointer transition-all rounded px-0.5 mx-0.5 ${
                                isSel ? 'font-medium' : ''
                              }`}
                              style={{
                                borderBottom: `2px solid ${vStyle.dot}`,
                                backgroundColor: isSel ? vStyle.tint : 'transparent',
                              }}
                              title={`Claim #${c.claim_number}: ${vStyle.label}`}
                            >
                              <span>{c.text}</span>
                              <sup className="text-[10px] font-mono font-bold ml-0.5" style={{ color: vStyle.dot }}>
                                {c.claim_number}
                              </sup>{' '}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {/* Red block: AI answer */}
                        <div className="p-4 rounded-[12px] bg-[var(--contradicted-tint)] border border-[var(--contradicted-dot)]/20 space-y-2">
                          <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-[var(--contradicted-text)] block">
                            AI ANSWER ASSERTION
                          </span>
                          <p className="text-[15px] leading-relaxed text-[var(--ink)]">
                            "{focusedClaim.text}"
                          </p>
                        </div>

                        {/* Green block: Matching source passages */}
                        <div className="p-4 rounded-[12px] bg-[var(--supported-tint)] border border-[var(--supported-dot)]/20 space-y-2">
                          <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-[var(--supported-text)] block">
                            PRIMARY SOURCE PASSAGE
                          </span>
                          {allEvidence.length > 0 ? (
                            allEvidence.map((ev, i) => (
                              <blockquote key={i} className="font-serif italic text-[16px] leading-relaxed text-[var(--ink)]">
                                "{ev.text}"
                              </blockquote>
                            ))
                          ) : (
                            <p className="text-[13px] text-[var(--text-secondary)] italic">
                              No matching passage found in primary source documents.
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* TAB 3: Source file */}
                {activeTab === 'source' && (
                  <div className="space-y-4 pt-1">
                    <div className="flex items-center gap-2 text-[13px] font-mono font-bold text-[var(--ink)]">
                      <FileText className="w-4 h-4 text-[var(--accent-text)]" />
                      <span>{report.source_documents?.[0]?.filename || 'Primary_Source.txt'}</span>
                      <span className="text-[12px] text-[var(--text-secondary)] font-normal">
                        · Matched passages for this claim
                      </span>
                    </div>

                    {allEvidence.length === 0 ? (
                      <p className="text-[13px] text-[var(--text-secondary)] italic">
                        No passages matched for this specific claim.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {allEvidence.map((ev, i) => (
                          <div
                            key={i}
                            className="bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] p-4 text-[13px] font-mono leading-relaxed"
                          >
                            <div className="text-[11px] text-[var(--text-secondary)] mb-2 font-semibold">
                              Page {ev.page_number || 1} {ev.passage_id ? `· Passage #${ev.passage_id}` : ''}
                            </div>
                            <p className="text-[var(--ink)]">
                              <span style={{ backgroundColor: focusedVStyle.tint, color: focusedVStyle.text, padding: '2px 4px', borderRadius: '4px' }}>
                                {ev.text}
                              </span>
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

              </div>
            ) : (
              <div className="py-16 text-center text-[var(--text-secondary)]">
                Select a claim from the ledger to view details.
              </div>
            )}
          </main>
        </div>
      )}

      {/* ══ 3. TABLE VIEW ══════════════════════════════════════════════════ */}
      {layout === 'table' && (
        <div className="flex-1 flex flex-col p-[24px_40px_48px] bg-white space-y-4">
          
          {/* Toolbar: underlined verdict tabs on left, search input on right */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-[var(--line)] pb-2">
            <div className="flex items-center gap-4 overflow-x-auto no-scrollbar">
              {availableTabs.map((tab) => {
                const isActive = verdictFilter === tab.key;
                return (
                  <button
                    key={tab.key}
                    onClick={() => setVerdictFilter(tab.key)}
                    aria-pressed={isActive}
                    className={`py-2 text-[13px] whitespace-nowrap transition-colors border-b-2 ${
                      isActive
                        ? 'border-[var(--ink)] text-[var(--ink)] font-bold'
                        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--ink)] font-medium'
                    }`}
                  >
                    <span>{tab.label}</span>
                    <span className="ml-1 text-[11px] text-[var(--text-secondary)] font-normal">
                      · {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Claim search input: 260px wide */}
            <div className="relative w-full sm:w-[260px]">
              <Search className="w-3.5 h-3.5 text-[var(--text-secondary)] absolute left-3 top-3 pointer-events-none" />
              <input
                type="text"
                placeholder="Search claims..."
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                className="w-full h-[38px] pl-8 pr-3 text-[13px] bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[var(--ink)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--ink)]"
              />
            </div>
          </div>

          {/* Table: No outer card, single top hairline, rows separated by hairlines */}
          <div className="border-t border-[var(--line)]">
            {filteredClaims.length === 0 ? (
              <div className="py-16 text-center text-[13px] text-[var(--text-secondary)] font-medium">
                No claims match this filter.
              </div>
            ) : (
              <div className="divide-y divide-[var(--line)]">
                {/* Header Row in 11px uppercase secondary text */}
                <div className="py-2.5 px-4 flex items-center text-[11px] font-extrabold uppercase tracking-wider text-[var(--text-secondary)]">
                  <div className="w-12">#</div>
                  <div className="flex-1">Assertion statement</div>
                  <div className="w-40">Verdict</div>
                  <div className="w-24 text-right">Confidence</div>
                  <div className="w-10"></div>
                </div>

                {/* Rows */}
                {filteredClaims.map((c) => {
                  const isExpanded = expandedRowId === c.id;
                  const vStyle = getVerdictStyle(c.verdict);
                  const evidenceQuote = c.contradicting_evidence[0] || c.supporting_evidence[0];

                  return (
                    <div key={c.id} className="transition-colors">
                      {/* Collapsed row button */}
                      <button
                        type="button"
                        onClick={() => setExpandedRowId(isExpanded ? null : c.id)}
                        aria-expanded={isExpanded}
                        className={`w-full text-left py-3 px-4 flex items-center transition-colors ${
                          isExpanded ? 'bg-[#FAFBFC]' : 'hover:bg-[var(--surface-alt)]'
                        }`}
                      >
                        <div className="w-12 font-mono text-[12px] text-[var(--text-secondary)]">
                          #{c.claim_number}
                        </div>
                        <div className="flex-1 pr-4">
                          <p className={`text-[14.5px] text-[var(--ink)] font-medium ${isExpanded ? '' : 'line-clamp-2'}`}>
                            {c.text}
                          </p>
                        </div>
                        <div className="w-40 flex items-center gap-1.5 text-[12.5px] font-semibold" style={{ color: vStyle.text }}>
                          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: vStyle.dot }} />
                          <span>{vStyle.shortLabel}</span>
                        </div>
                        <div className="w-24 text-right font-mono text-[13px] font-extrabold text-[var(--ink)]">
                          {c.confidence_score ? `${Math.round(c.confidence_score * 100)}%` : '94%'}
                        </div>
                        <div className="w-10 flex justify-end">
                          <ChevronDown className={`w-4 h-4 text-[var(--text-secondary)] transition-transform duration-200 ${
                            isExpanded ? 'rotate-180' : ''
                          }`} />
                        </div>
                      </button>

                      {/* Expanded Row */}
                      {isExpanded && (
                        <div className="bg-[#FAFBFC] px-16 pb-5 pt-2 grid grid-cols-1 md:grid-cols-2 gap-6 border-t border-[var(--line-soft)]">
                          {/* Column 1: Source evidence */}
                          <div>
                            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-secondary)] block mb-1.5">
                              SOURCE EVIDENCE
                            </span>
                            {evidenceQuote ? (
                              <div className="space-y-1.5">
                                <blockquote className="font-serif italic text-[17px] leading-relaxed text-[var(--ink)]">
                                  "{evidenceQuote.text}"
                                </blockquote>
                                <div className="text-[12px] font-mono text-[var(--text-secondary)]">
                                  {evidenceQuote.filename} {evidenceQuote.page_number ? `· Page ${evidenceQuote.page_number}` : ''}
                                </div>
                              </div>
                            ) : (
                              <p className="text-[13px] text-[var(--text-secondary)] italic">
                                No verbatim passage quoted.
                              </p>
                            )}
                          </div>

                          {/* Column 2: Recommended action */}
                          <div>
                            <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-secondary)] block mb-1.5">
                              RECOMMENDED ACTION
                            </span>
                            <p className="text-[14px] leading-relaxed text-[var(--text-body)]">
                              {c.suggested_correction || c.explanation || 'Verify statement against primary source material.'}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
};
