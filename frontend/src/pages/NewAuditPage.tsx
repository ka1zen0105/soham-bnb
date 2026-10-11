import React, { useState, useEffect } from 'react';
import { 
  Upload, 
  FileText, 
  Trash2, 
  Play, 
  Clock, 
  AlertCircle, 
  FileCode, 
  BookOpen, 
  Settings2,
  Copy
} from 'lucide-react';
import { uploadSourceFile, createAudit, fetchAudit, fetchDemoDataset, fetchAuditInputs } from '../services/api';
import type { AuditOptions } from '../types';

interface NewAuditPageProps {
  navigate: (route: string) => void;
}

interface UploadedDoc {
  id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  preview_snippet: string;
}

export const NewAuditPage: React.FC<NewAuditPageProps> = ({ navigate }) => {
  const [title, setTitle] = useState('');
  const [answerText, setAnswerText] = useState('');
  const [sourceMode, setSourceMode] = useState<'upload' | 'paste'>('upload');
  const [pastedSource, setPastedSource] = useState('');
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDoc[]>([]);
  
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [options, setOptions] = useState<AuditOptions>({
    verify_sources: true,
    reasoning_checks: true,
    safety_review: true,
    external_verification: false
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [activeStepText, setActiveStepText] = useState('');
  const [progressPct, setProgressPct] = useState(0);

  const [fromAuditId, setFromAuditId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const fromId = params.get('from');
      if (fromId) {
        setFromAuditId(fromId);
        fetchAuditInputs(fromId).then(inputs => {
          setTitle(inputs.title ? `${inputs.title} (Copy)` : '');
          setAnswerText(inputs.answer_text || '');
          if (inputs.source_documents && inputs.source_documents.length > 0) {
            setSourceMode('upload');
            setUploadedDocs(
              inputs.source_documents.map(d => ({
                id: d.id,
                filename: d.filename,
                size_bytes: d.size_bytes,
                page_count: d.page_count,
                preview_snippet: d.extracted_text ? d.extracted_text.slice(0, 300) : ''
              }))
            );
          }
          if (inputs.options) {
            setOptions(inputs.options);
          }
        }).catch(err => {
          console.warn('Could not load source audit inputs:', err);
        });
      }
    } catch {
      // Ignore URL parsing errors
    }
  }, []);

  const wordCount = answerText.trim() ? answerText.trim().split(/\s+/).length : 0;
  const charCount = answerText.length;
  const paragraphCount = answerText.trim() ? answerText.trim().split(/\n\s*\n/).length : 0;

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    try {
      setUploading(true);
      setUploadError(null);
      const res = await uploadSourceFile(file);
      const newDoc: UploadedDoc = {
        id: res.id,
        filename: res.filename,
        size_bytes: res.size_bytes,
        page_count: res.page_count,
        preview_snippet: res.preview_snippet || ''
      };
      setUploadedDocs(prev => [...prev, newDoc]);
    } catch (err: any) {
      setUploadError(err.message || 'File upload failed');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const removeDoc = (id: string) => {
    setUploadedDocs(prev => prev.filter(d => d.id !== id));
  };

  const loadDemo = async (demoId: 'earnings' | 'cybersecurity') => {
    try {
      const demo = await fetchDemoDataset(demoId);
      setTitle(demo.title);
      setAnswerText(demo.answer_text);
      setSourceMode('paste');
      setPastedSource(demo.source_text);
    } catch (err: any) {
      alert(`Failed to load preset: ${err.message}`);
    }
  };

  const handleRunAudit = async () => {
    if (!answerText.trim()) {
      setSubmitError('Please provide target AI output text to audit.');
      return;
    }

    if (sourceMode === 'upload' && uploadedDocs.length === 0) {
      setSubmitError('Please upload at least one source document or switch to Paste mode.');
      return;
    }

    if (sourceMode === 'paste' && !pastedSource.trim()) {
      setSubmitError('Please paste primary ground-truth source text.');
      return;
    }

    try {
      setIsSubmitting(true);
      setSubmitError(null);
      setActiveStepText('Submitting audit request...');
      setProgressPct(5);

      const audit = await createAudit({
        title: title.trim() || undefined,
        answer_text: answerText,
        source_text: sourceMode === 'paste' ? pastedSource : undefined,
        source_document_ids: sourceMode === 'upload' ? uploadedDocs.map(d => d.id) : [],
        options
      });

      const auditId = audit.id;
      let completed = false;
      let attempts = 0;

      while (!completed && attempts < 100) {
        await new Promise(r => setTimeout(r, 500));
        attempts++;
        const statusReport = await fetchAudit(auditId);
        
        setActiveStepText(statusReport.current_step || 'Processing...');
        setProgressPct(statusReport.progress_percentage || 20);

        if (statusReport.status === 'COMPLETED') {
          completed = true;
          navigate(`/audit/${auditId}`);
          return;
        } else if (statusReport.status === 'FAILED') {
          throw new Error(statusReport.error_message || 'Audit execution failed');
        }
      }
    } catch (err: any) {
      setSubmitError(err.message || 'Audit failed');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-[1200px] mx-auto px-6 lg:px-10 py-9 space-y-7">
      
      {/* Page Title & Presets */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-extrabold text-[var(--ink)] tracking-tight">
            New Audit Submission
          </h1>
          <p className="text-[14px] text-[var(--text-secondary)] mt-1 font-medium">
            Verify AI-generated answers against primary reference documentation with traceable citations.
          </p>
        </div>

        {/* Playfield Demo Data Pills */}
        <div className="flex items-center gap-2 text-[13px]">
          <span className="text-[var(--text-secondary)] font-medium hidden sm:inline">Presets:</span>
          <button
            type="button"
            onClick={() => loadDemo('earnings')}
            className="h-[38px] px-3.5 font-bold bg-[var(--surface)] hover:bg-[var(--surface-hover)] border border-[var(--line)] rounded-[10px] text-[var(--ink)] transition-colors"
          >
            BioCorp Q3 SEC
          </button>
          <button
            type="button"
            onClick={() => loadDemo('cybersecurity')}
            className="h-[38px] px-3.5 font-bold bg-[var(--surface)] hover:bg-[var(--surface-hover)] border border-[var(--line)] rounded-[10px] text-[var(--ink)] transition-colors"
          >
            Cloud Security
          </button>
        </div>
      </div>

      {fromAuditId && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 px-4 py-3 rounded-[12px] text-[13px] flex items-center justify-between shadow-2xs">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>
              Pre-filled from audit <strong className="font-mono">#{fromAuditId}</strong>. You can edit any inputs below and launch a new audit.
            </span>
          </div>
          <button
            type="button"
            onClick={() => navigate(`/audit/${fromAuditId}`)}
            className="text-emerald-700 hover:text-emerald-950 font-bold underline text-[12px]"
          >
            View original audit
          </button>
        </div>
      )}

      {submitError && (
        <div className="p-4 bg-[var(--contradicted-tint)] border border-[var(--line)] rounded-[12px] text-[13px] text-[var(--contradicted-text)] flex items-center gap-2.5 font-medium">
          <AlertCircle className="w-4 h-4 shrink-0 text-[var(--contradicted-dot)]" />
          <span>{submitError}</span>
        </div>
      )}

      {/* Audit Title Input Card */}
      <div className="bg-[var(--surface)] rounded-[16px] p-5 border border-[var(--line)] flex flex-col sm:flex-row sm:items-center gap-4">
        <label className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-secondary)] shrink-0 sm:w-44">
          Audit Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. BioCorp Clinical Trial BC-902 & SEC 10-Q Financial Verification"
          className="flex-1 h-[40px] px-4 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[13.5px] font-medium text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--ink)]"
        />
        <span className="text-[12px] text-[var(--text-secondary)] font-medium shrink-0 hidden sm:inline">
          Auto-generated if blank
        </span>
      </div>

      {/* Two-Column Document Submission Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Left Column: AI-Generated Answer */}
        <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-[16px] font-bold text-[var(--ink)] flex items-center gap-2">
                <FileCode className="w-4 h-4 text-[var(--accent-text)]" />
                Target AI Output Text
              </h2>
              {answerText && (
                <button
                  type="button"
                  onClick={() => setAnswerText('')}
                  className="text-[12px] text-[var(--contradicted-text)] hover:underline font-bold"
                >
                  Clear editor
                </button>
              )}
            </div>
            <p className="text-[13px] text-[var(--text-secondary)] mb-3 font-medium">
              The AI response or report to be audited for discrepancies and hallucinations.
            </p>

            <textarea
              rows={16}
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              placeholder="Paste the full AI-generated response, analysis, or claims here..."
              className="w-full p-4 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[13.5px] font-sans leading-relaxed focus:outline-none focus:ring-2 focus:ring-[var(--ink)] resize-y min-h-[380px] text-[var(--ink)]"
            />
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-[var(--line)] text-[12px] text-[var(--text-secondary)] font-mono">
            <span>{wordCount} words · {paragraphCount} paragraphs</span>
            <span>{charCount} characters</span>
          </div>
        </div>

        {/* Right Column: Primary Source Material */}
        <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-[16px] font-bold text-[var(--ink)] flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-[var(--accent-text)]" />
                Primary Source Ground Truth
              </h2>

              {/* Segmented Control */}
              <div className="flex rounded-[10px] bg-[#F2F4F7] p-1 text-[12px]">
                <button
                  type="button"
                  onClick={() => setSourceMode('upload')}
                  aria-pressed={sourceMode === 'upload'}
                  className={`px-3 py-1 rounded-[8px] font-bold transition-all ${
                    sourceMode === 'upload' ? 'bg-[var(--surface)] text-[var(--ink)]' : 'text-[var(--text-secondary)] hover:text-[var(--ink)]'
                  }`}
                >
                  Upload Files
                </button>
                <button
                  type="button"
                  onClick={() => setSourceMode('paste')}
                  aria-pressed={sourceMode === 'paste'}
                  className={`px-3 py-1 rounded-[8px] font-bold transition-all ${
                    sourceMode === 'paste' ? 'bg-[var(--surface)] text-[var(--ink)]' : 'text-[var(--text-secondary)] hover:text-[var(--ink)]'
                  }`}
                >
                  Paste Text
                </button>
              </div>
            </div>

            <p className="text-[13px] text-[var(--text-secondary)] mb-3 font-medium">
              Reference documentation used for verbatim citation extraction and mathematical cross-checks.
            </p>

            {sourceMode === 'upload' ? (
              <div className="space-y-4">
                {/* Upload Drag & Drop Area */}
                <label className="border border-dashed border-[var(--line)] hover:border-[var(--accent)] rounded-[12px] p-8 flex flex-col items-center justify-center cursor-pointer bg-[var(--surface-alt)] transition-colors">
                  <Upload className="w-7 h-7 text-[var(--text-secondary)] mb-2" />
                  <span className="text-[13.5px] font-bold text-[var(--ink)]">
                    Select source document or drag & drop files
                  </span>
                  <span className="text-[11px] text-[var(--text-secondary)] mt-1 font-mono text-center">
                    PDF, Word (.docx), Plain Text (.txt, .md)
                  </span>
                  <input
                    type="file"
                    accept=".pdf,.docx,.doc,.txt,.md"
                    className="hidden"
                    onChange={handleFileUpload}
                    disabled={uploading}
                  />
                </label>

                {uploading && (
                  <div className="flex items-center gap-2 text-[12px] text-[var(--accent-text)] p-3 bg-[var(--accent-tint)] rounded-[10px] border border-[var(--line)] font-semibold">
                    <Clock className="w-4 h-4 animate-spin text-[var(--accent)]" />
                    <span>Extracting pages and chunking passages with stable character offsets...</span>
                  </div>
                )}

                {uploadError && (
                  <div className="p-3 bg-[var(--contradicted-tint)] border border-[var(--line)] rounded-[10px] text-[12px] text-[var(--contradicted-text)] font-medium">
                    {uploadError}
                  </div>
                )}

                {/* Uploaded Documents List */}
                {uploadedDocs.length > 0 && (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    <span className="text-[11px] font-bold text-[var(--text-secondary)] uppercase tracking-wider block">
                      Parsed Source Documents ({uploadedDocs.length}):
                    </span>
                    {uploadedDocs.map(doc => (
                      <div key={doc.id} className="p-3 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[12px] flex items-start justify-between gap-3">
                        <div className="overflow-hidden">
                          <div className="flex items-center gap-2 font-bold text-[var(--ink)]">
                            <FileText className="w-4 h-4 text-[var(--accent)] shrink-0" />
                            <span className="truncate">{doc.filename}</span>
                          </div>
                          <div className="text-[11px] text-[var(--text-secondary)] font-mono mt-0.5">
                            {doc.page_count} page(s) · {Math.round(doc.size_bytes / 1024)} KB
                          </div>
                          {doc.preview_snippet && (
                            <p className="text-[12px] text-[var(--text-body)] font-serif italic mt-1 line-clamp-2">
                              "{doc.preview_snippet}"
                            </p>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={() => removeDoc(doc.id)}
                          aria-label="Remove document"
                          className="text-[var(--text-secondary)] hover:text-[var(--contradicted-text)] p-1.5 rounded-[8px] hover:bg-[var(--contradicted-tint)] transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <textarea
                  rows={16}
                  value={pastedSource}
                  onChange={(e) => setPastedSource(e.target.value)}
                  placeholder="Paste verified ground-truth documentation, trial notes, financial ledger, or specification text here..."
                  className="w-full p-4 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[13.5px] font-sans leading-relaxed focus:outline-none focus:ring-2 focus:ring-[var(--ink)] resize-y min-h-[380px] text-[var(--ink)]"
                />
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-[var(--line)] flex items-center justify-between text-[12px] text-[var(--text-secondary)] font-medium">
            <span>Mode: <strong className="text-[var(--ink)]">Strict Grounding</strong></span>
            <span className="font-mono text-[11px] text-[var(--text-secondary)]">Neutralizes embedded prompt injections</span>
          </div>
        </div>
      </div>

      {/* Verification Parameters & Run Action */}
      <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[16px] font-bold text-[var(--ink)]">
            <Settings2 className="w-4 h-4 text-[var(--accent-text)]" />
            <span>Auditing Parameters</span>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-[13px] text-[var(--text-body)] font-medium">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.verify_sources}
                onChange={(e) => setOptions(prev => ({ ...prev, verify_sources: e.target.checked }))}
                className="w-4 h-4 rounded text-[var(--accent)] accent-[var(--accent)] border-[var(--line)]"
              />
              <span>Verify against sources</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.reasoning_checks}
                onChange={(e) => setOptions(prev => ({ ...prev, reasoning_checks: e.target.checked }))}
                className="w-4 h-4 rounded text-[var(--accent)] accent-[var(--accent)] border-[var(--line)]"
              />
              <span>Reasoning logic checks</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.safety_review}
                onChange={(e) => setOptions(prev => ({ ...prev, safety_review: e.target.checked }))}
                className="w-4 h-4 rounded text-[var(--accent)] accent-[var(--accent)] border-[var(--line)]"
              />
              <span>Safety & directive review</span>
            </label>
          </div>
        </div>

        <button
          type="button"
          onClick={handleRunAudit}
          disabled={isSubmitting}
          className={`
            h-[42px] px-6 rounded-[10px] text-[13px] font-bold flex items-center gap-2 transition-all shrink-0
            ${isSubmitting 
              ? 'bg-[#EEF0F3] text-[var(--text-secondary)] cursor-not-allowed' 
              : 'bg-[var(--accent)] hover:opacity-90 text-[var(--ink)]'}
          `}
        >
          {isSubmitting ? (
            <>
              <Clock className="w-4 h-4 animate-spin text-[var(--ink)]" />
              <span>Auditing Pipeline Running...</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              <span>Launch Audit</span>
            </>
          )}
        </button>
      </div>

      {/* Live Processing Pipeline Overlay / Progress Tracker */}
      {isSubmitting && (
        <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] space-y-4">
          <div className="flex items-center justify-between text-[13px]">
            <div className="flex items-center gap-2 font-bold text-[var(--ink)]">
              <Clock className="w-4 h-4 animate-spin text-[var(--accent)]" />
              <span>{activeStepText || 'Auditing in progress...'}</span>
            </div>
            <span className="font-mono text-[13px] text-[var(--accent-text)] font-extrabold">{progressPct}%</span>
          </div>

          <div className="w-full bg-[#EEF0F3] h-2 rounded-full overflow-hidden">
            <div 
              className="bg-[var(--accent)] h-full transition-all duration-300 rounded-full"
              style={{ width: `${progressPct}%` }}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 text-[12px] pt-1 text-[var(--text-secondary)] font-medium">
            <div className={`p-2.5 rounded-[10px] text-center border transition-colors ${progressPct >= 15 ? 'text-[var(--accent-text)] font-bold bg-[var(--accent-tint)] border-[var(--accent)]' : 'border-[var(--line)]'}`}>
              1. Processing Sources
            </div>
            <div className={`p-2.5 rounded-[10px] text-center border transition-colors ${progressPct >= 35 ? 'text-[var(--accent-text)] font-bold bg-[var(--accent-tint)] border-[var(--accent)]' : 'border-[var(--line)]'}`}>
              2. Extracting Claims
            </div>
            <div className={`p-2.5 rounded-[10px] text-center border transition-colors ${progressPct >= 55 ? 'text-[var(--accent-text)] font-bold bg-[var(--accent-tint)] border-[var(--accent)]' : 'border-[var(--line)]'}`}>
              3. Retrieving Evidence
            </div>
            <div className={`p-2.5 rounded-[10px] text-center border transition-colors ${progressPct >= 75 ? 'text-[var(--accent-text)] font-bold bg-[var(--accent-tint)] border-[var(--accent)]' : 'border-[var(--line)]'}`}>
              4. Verifying Claims
            </div>
            <div className={`p-2.5 rounded-[10px] text-center border transition-colors ${progressPct >= 95 ? 'text-[var(--accent-text)] font-bold bg-[var(--accent-tint)] border-[var(--accent)]' : 'border-[var(--line)]'}`}>
              5. Assembling Ledger
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
