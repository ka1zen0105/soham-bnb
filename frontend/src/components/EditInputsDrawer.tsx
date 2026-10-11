import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  X,
  Upload,
  FileText,
  Trash2,
  Play,
  RotateCcw,
  AlertCircle,
  FileEdit,
  ChevronDown,
  ChevronUp,
  Check,
  Plus
} from 'lucide-react';
import type { AuditInputsResponse, SourceDocument, AuditOptions, EditedDocumentInput } from '../types';
import { uploadSourceFile, rerunAudit, fetchAudit, pasteSourceText } from '../services/api';

interface EditInputsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  auditId: string;
  initialInputs: AuditInputsResponse | null;
  initialSection?: 'target' | 'source';
  navigate: (route: string) => void;
}

interface DraftDoc {
  id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  extracted_text: string;
  isEdited?: boolean;
}

export const EditInputsDrawer: React.FC<EditInputsDrawerProps> = ({
  isOpen,
  onClose,
  auditId,
  initialInputs,
  initialSection = 'target',
  navigate
}) => {
  const [answerText, setAnswerText] = useState('');
  const [title, setTitle] = useState('');
  const [docs, setDocs] = useState<DraftDoc[]>([]);
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [editingDocText, setEditingDocText] = useState('');

  // Source upload / paste tabs
  const [sourceTab, setSourceTab] = useState<'upload' | 'paste'>('upload');
  const [pastedText, setPastedText] = useState('');
  const [pastedFilename, setPastedFilename] = useState('');

  const [uploading, setUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Submitting re-run
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeStepText, setActiveStepText] = useState('');
  const [progressPct, setProgressPct] = useState(0);

  const targetSectionRef = useRef<HTMLDivElement>(null);
  const sourceSectionRef = useRef<HTMLDivElement>(null);

  const storageKey = `so_audit_draft_${auditId}`;

  // Load from initialInputs or sessionStorage
  useEffect(() => {
    if (!isOpen) return;

    let loadedDraft = false;
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed && typeof parsed.answerText === 'string') {
          setAnswerText(parsed.answerText);
          setTitle(parsed.title || '');
          setDocs(parsed.docs || []);
          setPastedText(parsed.pastedText || '');
          loadedDraft = true;
        }
      }
    } catch {
      // Ignore storage read errors
    }

    if (!loadedDraft && initialInputs) {
      setAnswerText(initialInputs.answer_text || '');
      setTitle(initialInputs.title || '');
      setDocs(
        (initialInputs.source_documents || []).map(d => ({
          id: d.id,
          filename: d.filename,
          size_bytes: d.size_bytes,
          page_count: d.page_count,
          extracted_text: d.extracted_text || '',
          isEdited: false
        }))
      );
      setPastedText('');
    }
  }, [isOpen, auditId, initialInputs, storageKey]);

  // Save to sessionStorage on every change
  useEffect(() => {
    if (!isOpen) return;
    try {
      const draftData = {
        answerText,
        title,
        docs,
        pastedText
      };
      sessionStorage.setItem(storageKey, JSON.stringify(draftData));
    } catch {
      // Ignore storage write errors
    }
  }, [answerText, title, docs, pastedText, isOpen, storageKey]);

  // Auto-scroll to requested section when opening
  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => {
      if (initialSection === 'source' && sourceSectionRef.current) {
        sourceSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else if (targetSectionRef.current) {
        targetSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [isOpen, initialSection]);

  // Has unsaved changes compared to initial stored audit inputs
  const hasUnsavedChanges = useMemo(() => {
    if (!initialInputs) return false;
    if (answerText !== (initialInputs.answer_text || '')) return true;
    if (pastedText.trim().length > 0) return true;

    const origIds = (initialInputs.source_documents || []).map(d => d.id).sort().join(',');
    const curIds = docs.map(d => d.id).sort().join(',');
    if (origIds !== curIds) return true;

    if (docs.some(d => d.isEdited)) return true;
    return false;
  }, [initialInputs, answerText, pastedText, docs]);

  const wordCount = answerText.trim() ? answerText.trim().split(/\s+/).length : 0;
  const charCount = answerText.length;

  const handleClearEditor = () => {
    if (confirm('Clear the Target AI Output Text?')) {
      setAnswerText('');
    }
  };

  const handleRemoveDoc = (id: string) => {
    setDocs(prev => prev.filter(d => d.id !== id));
    if (editingDocId === id) {
      setEditingDocId(null);
      setEditingDocText('');
    }
  };

  const handleOpenDocEdit = (doc: DraftDoc) => {
    if (editingDocId === doc.id) {
      setEditingDocId(null);
      setEditingDocText('');
    } else {
      setEditingDocId(doc.id);
      setEditingDocText(doc.extracted_text || '');
    }
  };

  const handleSaveDocText = (docId: string) => {
    setDocs(prev =>
      prev.map(d =>
        d.id === docId
          ? { ...d, extracted_text: editingDocText, isEdited: true }
          : d
      )
    );
    setEditingDocId(null);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    try {
      setUploading(true);
      setErrorMsg(null);
      const res = await uploadSourceFile(file);
      const newDoc: DraftDoc = {
        id: res.id,
        filename: res.filename,
        size_bytes: res.size_bytes,
        page_count: res.page_count,
        extracted_text: res.preview_snippet || '',
        isEdited: false
      };
      setDocs(prev => [...prev, newDoc]);
    } catch (err: any) {
      setErrorMsg(err.message || 'File upload failed');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleAddPastedText = async () => {
    if (!pastedText.trim()) {
      setErrorMsg('Please enter source text to add.');
      return;
    }
    try {
      setUploading(true);
      setErrorMsg(null);
      const filename = pastedFilename.trim() || `Pasted_Source_${docs.length + 1}.txt`;
      const res = await pasteSourceText(pastedText.trim(), filename);
      const newDoc: DraftDoc = {
        id: res.id,
        filename: res.filename,
        size_bytes: res.size_bytes,
        page_count: res.page_count,
        extracted_text: pastedText.trim(),
        isEdited: false
      };
      setDocs(prev => [...prev, newDoc]);
      setPastedText('');
      setPastedFilename('');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to add source text');
    } finally {
      setUploading(false);
    }
  };

  const handleRunRerun = async () => {
    if (!answerText.trim()) {
      setErrorMsg('Target AI output text is required.');
      return;
    }

    if (docs.length === 0 && !pastedText.trim()) {
      setErrorMsg('At least one source document is required.');
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMsg(null);
      setActiveStepText('Initiating re-run...');
      setProgressPct(10);

      // Kept unedited documents
      const keptIds = docs.filter(d => !d.isEdited).map(d => d.id);

      // Edited documents
      const editedDocs: EditedDocumentInput[] = docs
        .filter(d => d.isEdited)
        .map(d => ({
          id: d.id,
          filename: d.filename,
          text: d.extracted_text
        }));

      const newAudit = await rerunAudit(auditId, {
        title: title.trim() || undefined,
        answer_text: answerText,
        source_document_ids: keptIds,
        source_text: pastedText.trim() || undefined,
        edited_documents: editedDocs
      });

      const newId = newAudit.id;
      let completed = false;
      let attempts = 0;

      while (!completed && attempts < 100) {
        await new Promise(r => setTimeout(r, 500));
        attempts++;
        const statusReport = await fetchAudit(newId);

        setActiveStepText(statusReport.current_step || 'Auditing assertions...');
        setProgressPct(statusReport.progress_percentage || 25);

        if (statusReport.status === 'COMPLETED') {
          completed = true;
          try {
            sessionStorage.removeItem(storageKey);
          } catch {
            // Ignore
          }
          onClose();
          navigate(`/audit/${newId}`);
          return;
        } else if (statusReport.status === 'FAILED') {
          throw new Error(statusReport.error_message || 'Audit execution failed');
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Re-run audit failed');
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden font-sans">
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/40 transition-opacity"
        onClick={() => {
          if (!isSubmitting) onClose();
        }}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-6 sm:pl-10">
        <div className="w-screen max-w-[640px] bg-white border-l border-[#E8EAEE] shadow-2xl flex flex-col h-full">
          
          {/* Header */}
          <div className="px-6 py-4.5 border-b border-[#E8EAEE] flex items-center justify-between bg-white shrink-0">
            <div className="flex items-center gap-2.5">
              <h2 className="text-[17px] font-extrabold text-[var(--ink)] tracking-tight">
                Edit & Re-run Audit
              </h2>
              {hasUnsavedChanges && (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                  <span>Unsaved changes</span>
                </span>
              )}
            </div>

            <button
              onClick={onClose}
              disabled={isSubmitting}
              className="w-8 h-8 rounded-[8px] border border-[#E8EAEE] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--ink)] hover:bg-[#F2F4F7] transition-colors"
              aria-label="Close drawer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Progress Banner (if submitting) */}
          {isSubmitting && (
            <div className="bg-[#F7F8F6] border-b border-[#E8EAEE] p-4 shrink-0">
              <div className="flex items-center justify-between text-[12px] font-bold text-[var(--ink)] mb-2">
                <span>{activeStepText || 'Auditing assertions against sources...'}</span>
                <span>{progressPct}%</span>
              </div>
              <div className="w-full bg-[#E8EAEE] h-2 rounded-full overflow-hidden">
                <div
                  className="bg-[#12C56E] h-full transition-all duration-300 rounded-full"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          {/* Error Banner */}
          {errorMsg && (
            <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-[10px] text-[12px] flex items-center gap-2 shrink-0">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Scrollable Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">

            {/* Audit Title Input */}
            <div className="space-y-1.5">
              <label className="text-[12px] font-bold uppercase tracking-wider text-[var(--text-secondary)]">
                Audit Title
              </label>
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="Audit Review Title"
                className="w-full px-3.5 py-2.5 text-[13px] border border-[#E8EAEE] rounded-[10px] focus:outline-none focus:border-[#12C56E] transition-colors bg-white font-medium text-[var(--ink)]"
              />
            </div>

            {/* ══ Panel 1: Target AI Output Text ══ */}
            <div ref={targetSectionRef} className="space-y-2 pt-2 border-t border-[#E8EAEE]">
              <div className="flex items-center justify-between">
                <label className="text-[13px] font-bold text-[var(--ink)] flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[#12C56E]" />
                  <span>Target AI Output Text</span>
                </label>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-[var(--text-secondary)] font-mono">
                    {wordCount} words · {charCount} chars
                  </span>
                  <button
                    type="button"
                    onClick={handleClearEditor}
                    className="text-[11px] font-semibold text-red-600 hover:text-red-700 underline"
                  >
                    Clear editor
                  </button>
                </div>
              </div>

              <textarea
                rows={9}
                value={answerText}
                onChange={e => setAnswerText(e.target.value)}
                placeholder="Paste the AI-generated response text you want to audit..."
                className="w-full p-3.5 text-[13px] leading-relaxed border border-[#E8EAEE] rounded-[12px] focus:outline-none focus:border-[#12C56E] transition-colors resize-y bg-white text-[var(--ink)] font-normal"
              />
            </div>

            {/* ══ Panel 2: Primary Source Ground Truth ══ */}
            <div ref={sourceSectionRef} className="space-y-3 pt-2 border-t border-[#E8EAEE]">
              <div className="flex items-center justify-between">
                <label className="text-[13px] font-bold text-[var(--ink)] flex items-center gap-2">
                  <Upload className="w-4 h-4 text-[#12C56E]" />
                  <span>Primary Source Ground Truth</span>
                </label>
                <span className="text-[11px] text-[var(--text-secondary)] font-mono">
                  {docs.length} source file{docs.length !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Existing Documents List */}
              {docs.length > 0 && (
                <div className="space-y-2">
                  {docs.map(doc => (
                    <div
                      key={doc.id}
                      className="border border-[#E8EAEE] rounded-[10px] bg-white overflow-hidden transition-all"
                    >
                      <div className="p-3 flex items-center justify-between gap-3">
                        <div
                          onClick={() => handleOpenDocEdit(doc)}
                          className="flex items-center gap-2.5 min-w-0 cursor-pointer flex-1 group"
                          title="Click to view and edit document text"
                        >
                          <FileText className="w-4 h-4 text-[#12C56E] shrink-0" />
                          <div className="min-w-0">
                            <p className="text-[12px] font-bold text-[var(--ink)] truncate group-hover:text-[#12C56E] transition-colors">
                              {doc.filename}
                            </p>
                            <p className="text-[11px] text-[var(--text-secondary)] font-mono">
                              {doc.page_count} page{doc.page_count !== 1 ? 's' : ''} · {(doc.size_bytes / 1024).toFixed(1)} KB
                              {doc.isEdited && (
                                <span className="ml-2 text-emerald-600 font-bold font-sans">
                                  (Edited)
                                </span>
                              )}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleOpenDocEdit(doc)}
                            className="p-1.5 text-[var(--text-secondary)] hover:text-[var(--ink)] rounded-[6px] hover:bg-[#F2F4F7]"
                            title="Edit full text"
                          >
                            <FileEdit className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemoveDoc(doc.id)}
                            className="p-1.5 text-[var(--text-secondary)] hover:text-red-600 rounded-[6px] hover:bg-red-50"
                            title="Remove document"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* Inline Document Text Editor */}
                      {editingDocId === doc.id && (
                        <div className="p-3 border-t border-[#E8EAEE] bg-[#F7F8F6] space-y-2.5">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-bold text-[var(--ink)]">Editing: {doc.filename}</span>
                            <span className="text-[var(--text-secondary)] font-mono">
                              {editingDocText.length} characters
                            </span>
                          </div>
                          <textarea
                            rows={8}
                            value={editingDocText}
                            onChange={e => setEditingDocText(e.target.value)}
                            className="w-full p-2.5 text-[12px] font-mono leading-relaxed border border-[#E8EAEE] rounded-[8px] bg-white focus:outline-none focus:border-[#12C56E]"
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setEditingDocId(null)}
                              className="px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] hover:text-[var(--ink)]"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSaveDocText(doc.id)}
                              className="px-3 py-1 bg-[#12C56E] hover:bg-[#0fa95d] text-white text-[11px] font-bold rounded-[6px] flex items-center gap-1"
                            >
                              <Check className="w-3 h-3" />
                              <span>Apply Edits</span>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Add New Source Section (Tabs: Upload Files / Paste Text) */}
              <div className="border border-[#E8EAEE] rounded-[12px] p-4 bg-white space-y-3">
                <div className="flex items-center gap-2 border-b border-[#E8EAEE] pb-2.5">
                  <span className="text-[12px] font-bold text-[var(--ink)]">Add Document:</span>
                  <div className="flex items-center gap-1 bg-[#F2F4F7] p-0.5 rounded-[8px] text-[11px] font-bold">
                    <button
                      type="button"
                      onClick={() => setSourceTab('upload')}
                      className={`px-2.5 py-1 rounded-[6px] transition-colors ${
                        sourceTab === 'upload' ? 'bg-white text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)]'
                      }`}
                    >
                      Upload File
                    </button>
                    <button
                      type="button"
                      onClick={() => setSourceTab('paste')}
                      className={`px-2.5 py-1 rounded-[6px] transition-colors ${
                        sourceTab === 'paste' ? 'bg-white text-[var(--ink)] shadow-xs' : 'text-[var(--text-secondary)]'
                      }`}
                    >
                      Paste Text
                    </button>
                  </div>
                </div>

                {sourceTab === 'upload' ? (
                  <label className="border-2 border-dashed border-[#E8EAEE] hover:border-[#12C56E] rounded-[10px] p-5 flex flex-col items-center justify-center cursor-pointer transition-colors bg-[#FAFAFA]">
                    <Upload className="w-5 h-5 text-[var(--text-secondary)] mb-1.5" />
                    <span className="text-[12px] font-bold text-[var(--ink)]">
                      {uploading ? 'Processing document...' : 'Click to upload PDF, DOCX, or TXT'}
                    </span>
                    <span className="text-[11px] text-[var(--text-secondary)] mt-0.5">
                      Max file size 25MB
                    </span>
                    <input
                      type="file"
                      disabled={uploading}
                      onChange={handleFileUpload}
                      accept=".pdf,.docx,.doc,.txt,.md"
                      className="hidden"
                    />
                  </label>
                ) : (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={pastedFilename}
                      onChange={e => setPastedFilename(e.target.value)}
                      placeholder="Optional filename (e.g. Reference_Manual.txt)"
                      className="w-full px-3 py-1.5 text-[12px] border border-[#E8EAEE] rounded-[8px] focus:outline-none focus:border-[#12C56E]"
                    />
                    <textarea
                      rows={4}
                      value={pastedText}
                      onChange={e => setPastedText(e.target.value)}
                      placeholder="Paste reference text here..."
                      className="w-full p-2.5 text-[12px] border border-[#E8EAEE] rounded-[8px] focus:outline-none focus:border-[#12C56E]"
                    />
                    <button
                      type="button"
                      disabled={uploading || !pastedText.trim()}
                      onClick={handleAddPastedText}
                      className="w-full py-2 bg-[#F2F4F7] hover:bg-[#E8EAEE] text-[var(--ink)] text-[12px] font-bold rounded-[8px] transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Attach Pasted Text</span>
                    </button>
                  </div>
                )}
              </div>

            </div>

          </div>

          {/* ══ Footer ══ */}
          <div className="p-4 border-t border-[#E8EAEE] bg-white flex items-center justify-between shrink-0">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={onClose}
              className="px-4 py-2 border border-[#E8EAEE] hover:bg-[#F2F4F7] text-[var(--ink)] text-[12px] font-bold rounded-[10px] transition-colors"
            >
              Cancel
            </button>

            <button
              type="button"
              disabled={isSubmitting || !answerText.trim() || docs.length === 0}
              onClick={handleRunRerun}
              className="px-5 py-2.5 bg-[#12C56E] hover:bg-[#0fa95d] text-white text-[13px] font-bold rounded-[10px] shadow-xs flex items-center gap-2 transition-all disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isSubmitting ? 'animate-spin' : ''}`} />
              <span>{isSubmitting ? 'Running audit...' : 'Re-run audit'}</span>
            </button>
          </div>

        </div>
      </div>
    </div>
  );
};
