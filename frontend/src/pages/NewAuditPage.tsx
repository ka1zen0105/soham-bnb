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
  Copy,
  Eye,
  Globe,
  AlertTriangle,
  RotateCcw,
  Presentation,
  Table,
  Image,
  Archive,
  X
} from 'lucide-react';
import { uploadSourceFile, createAudit, fetchAudit, fetchDemoDataset, fetchAuditInputs, fetchPaperByDoiOrUrl } from '../services/api';
import { saveAuditToStorage } from '../services/auditStorage';
import type { AuditOptions } from '../types';

interface NewAuditPageProps {
  navigate: (route: string) => void;
}

interface UploadedDoc {
  id: string;
  filename: string;
  file_type?: string;
  size_bytes: number;
  page_count: number;
  word_count?: number;
  preview_snippet: string;
  full_text?: string;
  warnings?: string[];
}

interface FileProgressItem {
  name: string;
  status: 'uploading' | 'done' | 'error';
  progressText: string;
  errorText?: string;
  file?: File;
}

export const NewAuditPage: React.FC<NewAuditPageProps> = ({ navigate }) => {
  const [title, setTitle] = useState('');
  const [answerText, setAnswerText] = useState('');
  const [sourceMode, setSourceMode] = useState<'upload' | 'paper' | 'paste'>('upload');
  const [pastedSource, setPastedSource] = useState('');
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDoc[]>([]);
  
  // Multi-file upload progress tracking
  const [fileProgressList, setFileProgressList] = useState<Record<string, FileProgressItem>>({});
  const [isUploading, setIsUploading] = useState(false);

  // DOI / arXiv / URL input
  const [paperQuery, setPaperQuery] = useState('');
  const [fetchingPaper, setFetchingPaper] = useState(false);
  const [paperError, setPaperError] = useState<string | null>(null);

  // Preview text modal
  const [previewDoc, setPreviewDoc] = useState<UploadedDoc | null>(null);

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
                file_type: d.file_type,
                size_bytes: d.size_bytes,
                page_count: d.page_count,
                word_count: d.extracted_text ? d.extracted_text.trim().split(/\s+/).filter(Boolean).length : 0,
                preview_snippet: d.extracted_text ? d.extracted_text.slice(0, 300) : '',
                full_text: d.extracted_text || '',
                warnings: d.warnings || []
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

  const getDocTypeInfo = (filename: string, file_type?: string) => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    if (ext === 'pdf') return { label: 'PDF', icon: FileText, color: 'text-red-700 bg-red-50 border-red-200' };
    if (['pptx', 'ppt', 'odp'].includes(ext)) return { label: 'Slides', icon: Presentation, color: 'text-orange-700 bg-orange-50 border-orange-200' };
    if (['xlsx', 'xls', 'csv', 'tsv'].includes(ext)) return { label: 'Data', icon: Table, color: 'text-emerald-700 bg-emerald-50 border-emerald-200' };
    if (['docx', 'doc', 'rtf', 'odt'].includes(ext)) return { label: 'Word', icon: FileText, color: 'text-blue-700 bg-blue-50 border-blue-200' };
    if (['json', 'jsonl', 'xml', 'yaml', 'yml'].includes(ext)) return { label: 'Data', icon: FileCode, color: 'text-purple-700 bg-purple-50 border-purple-200' };
    if (['bib', 'ris', 'tex', 'epub', 'doi'].includes(ext)) return { label: 'Citation', icon: BookOpen, color: 'text-indigo-700 bg-indigo-50 border-indigo-200' };
    if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return { label: 'Image', icon: Image, color: 'text-amber-700 bg-amber-50 border-amber-200' };
    if (['zip'].includes(ext)) return { label: 'ZIP', icon: Archive, color: 'text-stone-700 bg-stone-50 border-stone-200' };
    return { label: 'Document', icon: FileText, color: 'text-gray-700 bg-gray-50 border-gray-200' };
  };

  const processSingleFile = async (file: File) => {
    const fileKey = `${file.name}_${file.size}_${file.lastModified}`;
    setFileProgressList(prev => ({
      ...prev,
      [fileKey]: {
        name: file.name,
        status: 'uploading',
        progressText: 'Reading and parsing units...',
        file
      }
    }));

    try {
      const res = await uploadSourceFile(file);
      const words = (res.preview_snippet || '').trim().split(/\s+/).filter(Boolean).length;
      const newDoc: UploadedDoc = {
        id: res.id,
        filename: res.filename,
        file_type: res.file_type,
        size_bytes: res.size_bytes,
        page_count: res.page_count,
        word_count: words,
        preview_snippet: res.preview_snippet || '',
        full_text: res.preview_snippet || '',
        warnings: res.warnings || []
      };
      setUploadedDocs(prev => [...prev, newDoc]);
      setFileProgressList(prev => {
        const next = { ...prev };
        delete next[fileKey];
        return next;
      });
    } catch (err: any) {
      setFileProgressList(prev => ({
        ...prev,
        [fileKey]: {
          name: file.name,
          status: 'error',
          progressText: 'Upload failed',
          errorText: err.message || 'Parsing failed',
          file
        }
      }));
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const files = Array.from(e.target.files);
    e.target.value = '';
    setIsUploading(true);

    for (let i = 0; i < files.length; i++) {
      await processSingleFile(files[i]);
    }
    setIsUploading(false);
  };

  const handleDropFiles = async (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    if (!e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
    const files = Array.from(e.dataTransfer.files);
    setIsUploading(true);

    for (let i = 0; i < files.length; i++) {
      await processSingleFile(files[i]);
    }
    setIsUploading(false);
  };

  const handleRetryFile = async (fileKey: string) => {
    const item = fileProgressList[fileKey];
    if (item && item.file) {
      await processSingleFile(item.file);
    }
  };

  const handleDismissProgress = (fileKey: string) => {
    setFileProgressList(prev => {
      const next = { ...prev };
      delete next[fileKey];
      return next;
    });
  };

  const handleFetchPaper = async () => {
    if (!paperQuery.trim()) return;
    try {
      setFetchingPaper(true);
      setPaperError(null);
      const res = await fetchPaperByDoiOrUrl(paperQuery.trim());
      const words = (res.preview_snippet || '').trim().split(/\s+/).filter(Boolean).length;
      const newDoc: UploadedDoc = {
        id: res.id,
        filename: res.filename,
        file_type: res.file_type,
        size_bytes: res.size_bytes,
        page_count: res.page_count,
        word_count: words,
        preview_snippet: res.preview_snippet || '',
        full_text: res.preview_snippet || '',
        warnings: res.warnings || []
      };
      setUploadedDocs(prev => [...prev, newDoc]);
      setPaperQuery('');
    } catch (err: any) {
      setPaperError(err.message || 'Failed to fetch paper.');
    } finally {
      setFetchingPaper(false);
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

    if (sourceMode !== 'paste' && uploadedDocs.length === 0) {
      setSubmitError('Please provide at least one source document (upload or via DOI/URL), or switch to Paste mode.');
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
        source_document_ids: sourceMode !== 'paste' ? uploadedDocs.map(d => d.id) : [],
        source_documents_data: sourceMode !== 'paste'
          ? uploadedDocs.map(d => ({
              id: d.id,
              filename: d.filename,
              text: d.full_text || d.preview_snippet
            }))
          : undefined,
        options
      });

      // Save full result in sessionStorage and localStorage
      saveAuditToStorage(audit);

      if (audit.status === 'COMPLETED') {
        setProgressPct(100);
        setActiveStepText('Audit completed successfully.');
        navigate(`/audit/${audit.id}`);
        return;
      } else if (audit.status === 'FAILED') {
        throw new Error(audit.error_message || 'Audit execution failed');
      }

      const auditId = audit.id;
      let completed = false;
      let attempts = 0;

      while (!completed && attempts < 100) {
        await new Promise(r => setTimeout(r, 500));
        attempts++;
        const statusReport = await fetchAudit(auditId);
        saveAuditToStorage(statusReport);
        
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
    <div className="space-y-6 max-w-7xl mx-auto pb-16 font-sans">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-extrabold text-[var(--ink)] tracking-tight">
            Launch New Audit
          </h1>
          <p className="text-[14px] text-[var(--text-secondary)] mt-1 font-medium">
            Cross-examine synthetic AI outputs against universal primary sources with deterministic verification.
          </p>
        </div>

        {/* Quick Presets */}
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-[var(--text-secondary)] font-semibold uppercase tracking-wider mr-1">
            Presets:
          </span>
          <button
            type="button"
            onClick={() => loadDemo('earnings')}
            className="px-3 py-1.5 rounded-[8px] border border-[var(--line)] bg-[var(--surface)] text-[12.5px] font-bold text-[var(--ink)] hover:bg-[var(--surface-alt)] transition-colors"
          >
            BioCorp Q3 Update
          </button>
          <button
            type="button"
            onClick={() => loadDemo('cybersecurity')}
            className="px-3 py-1.5 rounded-[8px] border border-[var(--line)] bg-[var(--surface)] text-[12.5px] font-bold text-[var(--ink)] hover:bg-[var(--surface-alt)] transition-colors"
          >
            SecOps Policy
          </button>
        </div>
      </div>

      {fromAuditId && (
        <div className="bg-[#ECFDF5] border border-[#A7F3D0] rounded-[10px] p-3.5 flex items-center justify-between text-[13px] text-[#065F46]">
          <div className="flex items-center gap-2">
            <span className="font-bold">Prefilled from previous run:</span>
            <code className="font-mono text-[12px] bg-white px-2 py-0.5 rounded border border-[#A7F3D0]">
              {fromAuditId}
            </code>
          </div>
          <button
            type="button"
            onClick={() => navigate(`/audit/${fromAuditId}`)}
            className="text-[12px] font-bold text-[#12C56E] hover:underline"
          >
            View original results →
          </button>
        </div>
      )}

      {/* Title Input */}
      <div>
        <label className="block text-[13px] font-bold text-[var(--ink)] mb-1">
          Audit Title <span className="text-[var(--text-secondary)] font-normal">(Optional)</span>
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Q3 Clinical Claims Review, ISO Policy Audit..."
          className="w-full px-4 py-2.5 rounded-[10px] border border-[var(--line)] bg-[var(--surface)] text-[14px] text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--ink)] transition-all font-medium"
        />
      </div>

      {/* Main Two-Panel Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left Panel: Target AI Output Text */}
        <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-[var(--accent)]" />
              <h2 className="text-[15px] font-extrabold text-[var(--ink)]">
                Target AI Output Text
              </h2>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-mono text-[var(--text-secondary)]">
              <span>{wordCount} words</span>
              <span>·</span>
              <span>{charCount} chars</span>
              <span>·</span>
              <span>{paragraphCount} paras</span>
            </div>
          </div>

          <p className="text-[13px] text-[var(--text-secondary)] font-medium">
            Paste the LLM answer, summary, or report you want to audit for hallucinations and contradictions.
          </p>

          <textarea
            rows={16}
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            placeholder="Paste generated response text to be audited..."
            className="w-full p-4 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[13.5px] font-sans leading-relaxed focus:outline-none focus:ring-2 focus:ring-[var(--ink)] resize-y min-h-[380px] text-[var(--ink)]"
          />

          <div className="pt-2 flex items-center justify-between text-[12px] text-[var(--text-secondary)] font-medium">
            <span>Discrete assertions will be extracted automatically.</span>
            {answerText && (
              <button
                type="button"
                onClick={() => setAnswerText('')}
                className="text-[var(--contradicted-text)] hover:underline text-[12px] font-bold"
              >
                Clear editor
              </button>
            )}
          </div>
        </div>

        {/* Right Panel: Primary Source Ground Truth */}
        <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[var(--verified-border)]" />
                <h2 className="text-[15px] font-extrabold text-[var(--ink)]">
                  Primary Source Ground Truth
                </h2>
              </div>

              {/* Mode Toggle Tabs */}
              <div className="flex items-center gap-1 bg-[var(--surface-alt)] p-1 rounded-[10px] border border-[var(--line)] text-[12px]">
                <button
                  type="button"
                  onClick={() => setSourceMode('upload')}
                  aria-pressed={sourceMode === 'upload'}
                  className={`px-3 py-1 rounded-[8px] font-bold transition-all ${
                    sourceMode === 'upload' ? 'bg-[var(--surface)] text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)] hover:text-[var(--ink)]'
                  }`}
                >
                  Upload Files
                </button>
                <button
                  type="button"
                  onClick={() => setSourceMode('paper')}
                  aria-pressed={sourceMode === 'paper'}
                  className={`px-3 py-1 rounded-[8px] font-bold transition-all ${
                    sourceMode === 'paper' ? 'bg-[var(--surface)] text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)] hover:text-[var(--ink)]'
                  }`}
                >
                  DOI / arXiv / URL
                </button>
                <button
                  type="button"
                  onClick={() => setSourceMode('paste')}
                  aria-pressed={sourceMode === 'paste'}
                  className={`px-3 py-1 rounded-[8px] font-bold transition-all ${
                    sourceMode === 'paste' ? 'bg-[var(--surface)] text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)] hover:text-[var(--ink)]'
                  }`}
                >
                  Paste Text
                </button>
              </div>
            </div>

            <p className="text-[13px] text-[var(--text-secondary)] mb-3 font-medium">
              Reference documentation used for verbatim citation extraction and mathematical cross-checks.
            </p>

            {/* TAB 1: Universal File Upload */}
            {sourceMode === 'upload' && (
              <div className="space-y-4">
                <label 
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDropFiles}
                  className="border border-dashed border-[var(--line)] hover:border-[var(--accent)] rounded-[12px] p-6 flex flex-col items-center justify-center cursor-pointer bg-[var(--surface-alt)] transition-colors text-center"
                >
                  <Upload className="w-7 h-7 text-[var(--text-secondary)] mb-2" />
                  <span className="text-[13.5px] font-bold text-[var(--ink)]">
                    Select source document or drag & drop files
                  </span>
                  <span className="text-[11.5px] text-[var(--text-secondary)] mt-1 font-sans">
                    PDF, Word, PowerPoint, Excel, CSV, JSON, HTML, Markdown, text, images, ZIP
                  </span>
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.docx,.doc,.rtf,.odt,.txt,.md,.html,.htm,.pptx,.ppt,.odp,.json,.jsonl,.csv,.tsv,.xlsx,.xls,.xml,.yaml,.yml,.bib,.ris,.tex,.epub,.png,.jpg,.jpeg,.webp,.zip"
                    className="hidden"
                    onChange={handleFileUpload}
                    disabled={isUploading}
                  />
                </label>

                {/* Per-File Upload Progress & Errors */}
                {Object.keys(fileProgressList).length > 0 && (
                  <div className="space-y-2">
                    {Object.entries(fileProgressList).map(([k, item]) => (
                      <div key={k} className="p-3 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[12px] flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 overflow-hidden">
                          {item.status === 'uploading' ? (
                            <Clock className="w-4 h-4 animate-spin text-[var(--accent)] shrink-0" />
                          ) : (
                            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                          )}
                          <div className="truncate">
                            <span className="font-bold text-[var(--ink)] mr-2">{item.name}</span>
                            <span className={item.status === 'error' ? 'text-red-600 font-medium' : 'text-[var(--text-secondary)] font-mono'}>
                              {item.errorText || item.progressText}
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          {item.status === 'error' && (
                            <button
                              type="button"
                              onClick={() => handleRetryFile(k)}
                              className="text-[11px] font-bold text-[#12C56E] hover:underline flex items-center gap-1"
                            >
                              <RotateCcw className="w-3 h-3" /> Retry
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDismissProgress(k)}
                            className="text-[var(--text-secondary)] hover:text-[var(--ink)] p-1"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: Add by DOI / arXiv / URL */}
            {sourceMode === 'paper' && (
              <div className="space-y-4">
                <div className="p-4 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[12px] space-y-3">
                  <div className="flex items-center gap-2 font-bold text-[13px] text-[var(--ink)]">
                    <Globe className="w-4 h-4 text-[var(--accent)]" />
                    <span>Add by DOI, arXiv ID, or URL</span>
                  </div>
                  <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed">
                    Fetch open-access abstracts and citations automatically from Crossref, arXiv, or public documentation URLs.
                  </p>
                  
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={paperQuery}
                      onChange={(e) => setPaperQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleFetchPaper()}
                      placeholder="e.g. 10.1038/s41586-020-2649-2, arXiv:2303.08774, or https://..."
                      className="flex-1 px-3.5 py-2 rounded-[8px] border border-[var(--line)] bg-white text-[13px] text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--ink)]"
                    />
                    <button
                      type="button"
                      onClick={handleFetchPaper}
                      disabled={fetchingPaper || !paperQuery.trim()}
                      className="px-4 py-2 bg-[#12C56E] text-white rounded-[8px] font-bold text-[12.5px] hover:bg-[#0fa85e] transition-colors disabled:opacity-50 shrink-0 flex items-center gap-1.5"
                    >
                      {fetchingPaper ? <Clock className="w-3.5 h-3.5 animate-spin" /> : null}
                      <span>Fetch Paper</span>
                    </button>
                  </div>

                  {paperError && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-[8px] text-[12px] text-red-700 flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{paperError}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 3: Paste Text */}
            {sourceMode === 'paste' && (
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

            {/* Ingested Source Documents List */}
            {uploadedDocs.length > 0 && sourceMode !== 'paste' && (
              <div className="space-y-2 mt-4 pt-4 border-t border-[var(--line)] max-h-72 overflow-y-auto">
                <span className="text-[11px] font-extrabold text-[var(--text-secondary)] uppercase tracking-wider block">
                  Ingested Source Documents ({uploadedDocs.length}):
                </span>
                {uploadedDocs.map(doc => {
                  const typeInfo = getDocTypeInfo(doc.filename, doc.file_type);
                  const Icon = typeInfo.icon;
                  return (
                    <div key={doc.id} className="p-3 bg-[var(--surface-alt)] border border-[var(--line)] rounded-[10px] text-[12px] flex items-start justify-between gap-3">
                      <div className="overflow-hidden flex-1">
                        <div className="flex items-center gap-2 font-bold text-[var(--ink)]">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border uppercase shrink-0 ${typeInfo.color}`}>
                            {typeInfo.label}
                          </span>
                          <span className="truncate">{doc.filename}</span>
                        </div>
                        
                        <div className="text-[11px] text-[var(--text-secondary)] font-mono mt-1 flex items-center gap-2 flex-wrap">
                          <span>{doc.page_count} unit(s)</span>
                          <span>·</span>
                          <span>{doc.word_count || 0} words</span>
                          <span>·</span>
                          <span>{Math.round(doc.size_bytes / 1024)} KB</span>
                        </div>

                        {/* Warning Chips */}
                        {doc.warnings && doc.warnings.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {doc.warnings.map((w, wIdx) => (
                              <span key={wIdx} className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-[6px]">
                                <AlertTriangle className="w-3 h-3 text-amber-600" />
                                {w}
                              </span>
                            ))}
                          </div>
                        )}

                        {doc.preview_snippet && (
                          <p className="text-[12px] text-[var(--text-body)] font-serif italic mt-1 line-clamp-2">
                            "{doc.preview_snippet}"
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => setPreviewDoc(doc)}
                          title="Preview extracted text"
                          className="text-[var(--text-secondary)] hover:text-[var(--ink)] p-1.5 rounded-[8px] hover:bg-[var(--surface)] transition-colors"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => removeDoc(doc.id)}
                          aria-label="Remove document"
                          className="text-[var(--text-secondary)] hover:text-red-600 p-1.5 rounded-[8px] hover:bg-red-50 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-[var(--line)] flex items-center justify-between text-[12px] text-[var(--text-secondary)] font-medium">
            <span>Mode: <strong className="text-[var(--ink)]">Universal Grounding</strong></span>
            <span className="font-mono text-[11px] text-[var(--text-secondary)]">Prompt injections neutralized</span>
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
                className="w-4 h-4 rounded text-[#12C56E] accent-[#12C56E] border-[var(--line)]"
              />
              <span>Verify against sources</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.reasoning_checks}
                onChange={(e) => setOptions(prev => ({ ...prev, reasoning_checks: e.target.checked }))}
                className="w-4 h-4 rounded text-[#12C56E] accent-[#12C56E] border-[var(--line)]"
              />
              <span>Reasoning checks</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={options.safety_review}
                onChange={(e) => setOptions(prev => ({ ...prev, safety_review: e.target.checked }))}
                className="w-4 h-4 rounded text-[#12C56E] accent-[#12C56E] border-[var(--line)]"
              />
              <span>Safety review</span>
            </label>
          </div>
        </div>

        <button
          type="button"
          onClick={handleRunAudit}
          disabled={isSubmitting}
          className="w-full sm:w-auto px-7 py-3 bg-[#12C56E] text-white rounded-[10px] font-bold text-[14px] hover:bg-[#0fa85e] transition-colors disabled:opacity-50 flex items-center justify-center gap-2 shadow-xs cursor-pointer"
        >
          {isSubmitting ? (
            <>
              <Clock className="w-4 h-4 animate-spin" />
              <span>Auditing...</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-white" />
              <span>Launch Audit</span>
            </>
          )}
        </button>
      </div>

      {/* Submission Progress / Status Card */}
      {isSubmitting && (
        <div className="bg-[var(--surface)] rounded-[16px] p-6 border border-[var(--line)] space-y-3">
          <div className="flex items-center justify-between text-[13px] font-bold text-[var(--ink)]">
            <span className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-[var(--accent)] animate-spin" />
              <span>{activeStepText || 'Executing multi-stage audit...'}</span>
            </span>
            <span className="font-mono text-[var(--text-secondary)]">{progressPct}%</span>
          </div>
          <div className="w-full bg-[var(--surface-alt)] h-2 rounded-full overflow-hidden">
            <div 
              className="bg-[#12C56E] h-full transition-all duration-300 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {submitError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-[12px] text-[13.5px] text-red-700 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{submitError}</span>
        </div>
      )}

      {/* Preview Extracted Text Modal */}
      {previewDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-[16px] border border-[#E8EAEE] max-w-2xl w-full max-h-[85vh] flex flex-col shadow-xl">
            <div className="p-5 border-b border-[#E8EAEE] flex items-center justify-between">
              <div>
                <h3 className="text-[16px] font-extrabold text-[var(--ink)] truncate max-w-lg">
                  {previewDoc.filename}
                </h3>
                <span className="text-[12px] text-[var(--text-secondary)] font-mono">
                  {previewDoc.page_count} unit(s) · {previewDoc.word_count || 0} words
                </span>
              </div>
              <button
                type="button"
                onClick={() => setPreviewDoc(null)}
                className="p-1.5 rounded-[8px] hover:bg-[#F2F4F7] text-[var(--text-secondary)]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 overflow-y-auto flex-1 font-mono text-[12.5px] leading-relaxed text-[var(--ink)] bg-[#F8F9FA] whitespace-pre-wrap select-text">
              {previewDoc.full_text || previewDoc.preview_snippet || '[No text extracted]'}
            </div>
            <div className="p-4 border-t border-[#E8EAEE] flex justify-end">
              <button
                type="button"
                onClick={() => setPreviewDoc(null)}
                className="px-4 py-2 bg-[#F2F4F7] text-[var(--ink)] rounded-[8px] font-bold text-[13px] hover:bg-[#E5E7EB]"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
