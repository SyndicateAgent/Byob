"use client";

import { type FormEvent, type ReactNode, useEffect, useId, useMemo, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Copy,
  Database,
  FileText,
  FileUp,
  Globe2,
  History,
  Layers3,
  ListFilter,
  RefreshCcw,
  Search,
  ShieldCheck,
  Trash2,
  Type,
  Upload,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DocumentContentViewer } from "@/components/document-content-viewer";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDialog } from "@/components/ui/dialog-provider";
import { Input, Textarea } from "@/components/ui/input";
import { InlineSpinner } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar, StepRail, type StepItem } from "@/components/ui/progress";
import { Label, Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, apiRequest } from "@/lib/api";
import { mergeChunkContent } from "@/lib/chunk-overlap";
import { formatDate, formatNumber, statusVariant } from "@/lib/utils";
import type {
  ChunkItem,
  DocumentAuditLogItem,
  DocumentBatchUploadResponse,
  DocumentContent,
  DocumentItem,
  DocumentVersionItem,
  KnowledgeBase,
} from "@/lib/types";

type UploadMode = "text" | "files" | "url" | null;
type DocumentFilter = "all" | "published" | "reviewed" | "draft" | "deprecated" | "active" | "failed";
type DocumentWorkspaceView = "overview" | "import" | "library" | "activity";
type GovernanceWorkspaceView = "overview" | "policy" | "content" | "monitor";
type GovernanceContentSource = "parsed" | "chunks" | "empty";
type IngestionProgress = {
  stage?: string;
  progress?: number;
  status?: string;
  detail?: string;
  started_at?: string;
  updated_at?: string;
};

const ACTIVE_DOCUMENT_STATUSES = new Set(["pending", "processing"]);
const DOCUMENT_PROGRESS_STORAGE_KEY = "byob_document_progress";
const REVIEW_STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "reviewed", label: "Reviewed" },
  { value: "published", label: "Published" },
  { value: "deprecated", label: "Deprecated" },
] as const;
const DOCUMENT_FILTERS: { value: DocumentFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "published", label: "Published" },
  { value: "reviewed", label: "Reviewed" },
  { value: "draft", label: "Draft" },
  { value: "deprecated", label: "Deprecated" },
  { value: "active", label: "Active" },
  { value: "failed", label: "Failed" },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clampProgress(value: number) {
  return Math.max(0, Math.min(100, value));
}

function documentIngestionProgress(document: DocumentItem): IngestionProgress | null {
  const progress = document.metadata?.ingestion_progress;
  if (!isRecord(progress)) return null;
  return {
    stage: typeof progress.stage === "string" ? progress.stage : undefined,
    progress: typeof progress.progress === "number" ? clampProgress(progress.progress) : undefined,
    status: typeof progress.status === "string" ? progress.status : undefined,
    detail: typeof progress.detail === "string" ? progress.detail : undefined,
    started_at: typeof progress.started_at === "string" ? progress.started_at : undefined,
    updated_at: typeof progress.updated_at === "string" ? progress.updated_at : undefined,
  };
}

function documentProgressKey(document: DocumentItem) {
  const progress = documentIngestionProgress(document);
  return `${document.id}:${progress?.started_at ?? document.updated_at ?? document.created_at}`;
}

function backendDocumentProgress(document: DocumentItem) {
  return documentIngestionProgress(document)?.progress;
}

function readStoredProgress() {
  if (typeof window === "undefined") return {};
  try {
    const value = JSON.parse(window.sessionStorage.getItem(DOCUMENT_PROGRESS_STORAGE_KEY) ?? "{}");
    if (!isRecord(value)) return {};
    return Object.fromEntries(
      Object.entries(value)
        .filter((entry): entry is [string, number] => typeof entry[1] === "number")
        .map(([key, progress]) => [key, clampProgress(progress)]),
    );
  } catch {
    return {};
  }
}

function writeStoredProgress(progressByRun: Record<string, number>) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(DOCUMENT_PROGRESS_STORAGE_KEY, JSON.stringify(progressByRun));
}

function isActiveDocument(document: DocumentItem) {
  return ACTIVE_DOCUMENT_STATUSES.has(document.status.toLowerCase());
}

function governanceSourceLabel(value: string) {
  return value;
}

function reviewStatusVariant(status: string) {
  if (status === "published") return "success" as const;
  if (status === "reviewed") return "info" as const;
  if (status === "deprecated") return "muted" as const;
  return "warning" as const;
}

function authorityLabel(level: number) {
  return `Authority ${level}`;
}

function isValidAuthorityLevel(value: string) {
  const level = Number(value);
  return Number.isInteger(level) && level >= 1;
}

function editableFileType(fileType: string | null) {
  return fileType === "txt" ? "txt" : "md";
}

function governanceContentSourceLabel(source: GovernanceContentSource) {
  if (source === "parsed") return "Parsed snapshot";
  if (source === "chunks") return "Chunk fallback";
  return "No content loaded";
}

function matchesDocumentFilter(document: DocumentItem, filter: DocumentFilter) {
  if (filter === "all") return true;
  if (filter === "active") return isActiveDocument(document);
  if (filter === "failed") return document.status.toLowerCase() === "failed";
  return document.review_status === filter;
}

function searchableDocumentText(document: DocumentItem) {
  return [
    document.name,
    document.source_type,
    document.file_type ?? "",
    document.status,
    document.review_status,
    governanceSourceLabel(document.governance_source_type),
    document.error_message ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

function documentProgress(document: DocumentItem, optimisticValue: number | undefined) {
  const status = document.status.toLowerCase();
  const backendProgress = backendDocumentProgress(document);
  if (status === "completed") return 100;
  if (status === "failed") return 100;
  if (status === "pending") return Math.max(backendProgress ?? 0, optimisticValue ?? 0, 18);
  if (status === "processing") return Math.max(backendProgress ?? 0, optimisticValue ?? 0, 44);
  return Math.max(backendProgress ?? 0, optimisticValue ?? 0);
}

function documentProgressTone(document: DocumentItem) {
  const status = document.status.toLowerCase();
  if (status === "completed") return "emerald" as const;
  if (status === "failed") return "red" as const;
  if (status === "pending") return "amber" as const;
  return "cyan" as const;
}

function documentStage(document: DocumentItem, progress: number) {
  const status = document.status.toLowerCase();
  if (status === "failed") return "Failed during ingestion";
  if (status === "completed") return `${document.chunk_count} chunks indexed`;
  const persistedProgress = documentIngestionProgress(document);
  if (persistedProgress?.detail) return persistedProgress.detail;
  if (status === "pending") return "Queued for worker";
  if (progress < 55) return "Parsing and chunking";
  if (progress < 82) return "Embedding chunks";
  return "Writing vectors to Qdrant";
}

function progressSteps(document: DocumentItem, progress: number): StepItem[] {
  const status = document.status.toLowerCase();
  const failed = status === "failed";
  const completed = status === "completed";

  return [
    { label: "Queued", state: failed ? "error" : progress >= 18 ? "done" : "active" },
    {
      label: "Parse",
      state: failed ? "error" : completed || progress >= 55 ? "done" : status === "processing" ? "active" : "idle",
    },
    {
      label: "Embed",
      state: failed ? "error" : completed || progress >= 82 ? "done" : progress >= 55 ? "active" : "idle",
    },
    {
      label: "Index",
      state: failed ? "error" : completed ? "done" : progress >= 82 ? "active" : "idle",
    },
  ];
}

export default function DocumentsPage() {
  const { confirm } = useDialog();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [kbId, setKbId] = useState("");
  const [activeView, setActiveView] = useState<DocumentWorkspaceView>("overview");
  const [documentSearch, setDocumentSearch] = useState("");
  const [documentFilter, setDocumentFilter] = useState<DocumentFilter>("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [webPageTitle, setWebPageTitle] = useState("");
  const [webPageUrl, setWebPageUrl] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [governanceSourceType, setGovernanceSourceType] = useState("");
  const [authorityLevel, setAuthorityLevel] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [importSummary, setImportSummary] = useState<string | null>(null);
  const [uploading, setUploading] = useState<UploadMode>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [progressByRun, setProgressByRun] = useState<Record<string, number>>(() => readStoredProgress());
  const [previewDocument, setPreviewDocument] = useState<DocumentItem | null>(null);
  const [previewChunks, setPreviewChunks] = useState<ChunkItem[]>([]);
  const [previewContent, setPreviewContent] = useState("");
  const [previewContentSource, setPreviewContentSource] = useState<"parsed" | "chunks">("chunks");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewCopied, setPreviewCopied] = useState(false);
  const [governanceDocument, setGovernanceDocument] = useState<DocumentItem | null>(null);
  const [governanceView, setGovernanceView] = useState<GovernanceWorkspaceView>("overview");
  const [governanceForm, setGovernanceForm] = useState({
    governance_source_type: "",
    authority_level: "",
    review_status: "",
    change_summary: "",
  });
  const [contentForm, setContentForm] = useState({
    content: "",
    file_type: "md",
    change_summary: "",
  });
  const [governanceContentSource, setGovernanceContentSource] = useState<GovernanceContentSource>("empty");
  const [versions, setVersions] = useState<DocumentVersionItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<DocumentAuditLogItem[]>([]);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [contentSaving, setContentSaving] = useState(false);
  const [governanceError, setGovernanceError] = useState<string | null>(null);

  const governanceReady = Boolean(governanceSourceType.trim() && isValidAuthorityLevel(authorityLevel) && reviewStatus);

  async function loadKnowledgeBases() {
    const response = await apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases");
    setKbs(response.data);
    if (!kbId && response.data.length > 0) setKbId(response.data[0].id);
  }

  async function loadDocuments(selectedKbId = kbId) {
    if (!selectedKbId) return;
    const response = await apiRequest<{ data: DocumentItem[] }>(
      `/api/v1/knowledge-bases/${selectedKbId}/documents`,
    );
    setDocuments(response.data);
  }

  function selectKnowledgeBase(nextKbId: string) {
    setKbId(nextKbId);
    setDocumentSearch("");
    setDocumentFilter("all");
    setSourceFilter("all");
  }

  const activeDocuments = useMemo(() => documents.filter(isActiveDocument), [documents]);
  const documentStats = useMemo(() => {
    const byFilter = DOCUMENT_FILTERS.reduce(
      (counts, filter) => ({
        ...counts,
        [filter.value]: documents.filter((document) => matchesDocumentFilter(document, filter.value)).length,
      }),
      {} as Record<DocumentFilter, number>,
    );
    return {
      byFilter,
      total: documents.length,
      chunks: documents.reduce((sum, document) => sum + document.chunk_count, 0),
      active: documents.filter(isActiveDocument).length,
      failed: documents.filter((document) => document.status.toLowerCase() === "failed").length,
      published: documents.filter((document) => document.review_status === "published").length,
      draftLike: documents.filter((document) => ["draft", "reviewed"].includes(document.review_status)).length,
    };
  }, [documents]);
  const sourceOptions = useMemo(
    () =>
      Array.from(new Set(documents.map((document) => document.governance_source_type)))
        .filter(Boolean)
        .sort(),
    [documents],
  );
  const filteredDocuments = useMemo(() => {
    const query = documentSearch.trim().toLowerCase();
    return documents.filter((document) => {
      if (!matchesDocumentFilter(document, documentFilter)) return false;
      if (sourceFilter !== "all" && document.governance_source_type !== sourceFilter) return false;
      if (query && !searchableDocumentText(document).includes(query)) return false;
      return true;
    });
  }, [documents, documentFilter, documentSearch, sourceFilter]);
  const currentKnowledgeBase = useMemo(() => kbs.find((kb) => kb.id === kbId) ?? null, [kbId, kbs]);
  const latestActiveDocument = activeDocuments[0];
  const latestProgress = latestActiveDocument
    ? documentProgress(latestActiveDocument, progressByRun[documentProgressKey(latestActiveDocument)])
    : 0;
  const governanceProgress = governanceDocument
    ? documentProgress(governanceDocument, progressByRun[documentProgressKey(governanceDocument)])
    : 0;
  const governanceIngestionProgress = governanceDocument ? documentIngestionProgress(governanceDocument) : null;

  useEffect(() => {
    writeStoredProgress(progressByRun);
  }, [progressByRun]);

  useEffect(() => {
    loadKnowledgeBases().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : "Load failed"),
    );
  }, []);

  useEffect(() => {
    loadDocuments().catch(() => undefined);
  }, [kbId]);

  useEffect(() => {
    if (!uploading) return;
    setUploadProgress(14);
    const timer = window.setInterval(() => {
      setUploadProgress((current) => Math.min(88, current + 9));
    }, 260);
    return () => window.clearInterval(timer);
  }, [uploading]);

  useEffect(() => {
    setProgressByRun((current) => {
      const next = { ...current };
      for (const document of documents) {
        const key = documentProgressKey(document);
        next[key] = documentProgress(document, next[key]);
      }
      return next;
    });
  }, [documents]);

  useEffect(() => {
    if (!kbId || activeDocuments.length === 0) return;
    const timer = window.setInterval(() => {
      setProgressByRun((current) => {
        const next = { ...current };
        for (const document of activeDocuments) {
          const key = documentProgressKey(document);
          const status = document.status.toLowerCase();
          const ceiling = status === "pending" ? 38 : 94;
          const step = status === "pending" ? 4 : 7;
          next[key] = Math.min(ceiling, documentProgress(document, next[key]) + step);
        }
        return next;
      });
      loadDocuments(kbId).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeDocuments, kbId]);

  async function uploadText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setImportSummary(null);
    setUploading("text");
    try {
      const document = await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents/text`, {
        method: "POST",
        body: JSON.stringify({
          name,
          content,
          file_type: "txt",
          governance_source_type: governanceSourceType.trim(),
          authority_level: Number(authorityLevel),
          review_status: reviewStatus,
        }),
      });
      setProgressByRun((current) => ({ ...current, [documentProgressKey(document)]: 22 }));
      setUploadProgress(100);
      setName("");
      setContent("");
      await loadDocuments();
      setActiveView("activity");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      window.setTimeout(() => {
        setUploading(null);
        setUploadProgress(0);
      }, 650);
    }
  }

  async function uploadFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (files.length === 0) return;
    setError(null);
    setImportSummary(null);
    setUploading("files");
    try {
      const formData = new FormData();
      for (const selectedFile of files) {
        formData.append("files", selectedFile);
      }
      formData.append("governance_source_type", governanceSourceType.trim());
      formData.append("authority_level", authorityLevel);
      formData.append("review_status", reviewStatus);
      const response = await apiRequest<DocumentBatchUploadResponse>(`/api/v1/knowledge-bases/${kbId}/documents/batch`, {
        method: "POST",
        body: formData,
      });
      const createdDocuments = response.items
        .map((item) => (item.status === "created" ? item.document : null))
        .filter((document): document is DocumentItem => document !== null);
      setProgressByRun((current) => {
        const next = { ...current };
        for (const document of createdDocuments) {
          next[documentProgressKey(document)] = 22;
        }
        return next;
      });
      setImportSummary(
        `${formatNumber(response.created_count)} queued, ${formatNumber(response.skipped_count)} skipped`,
      );
      setUploadProgress(100);
      setFiles([]);
      setFileInputKey((current) => current + 1);
      await loadDocuments();
      setActiveView("activity");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch upload failed");
    } finally {
      window.setTimeout(() => {
        setUploading(null);
        setUploadProgress(0);
      }, 650);
    }
  }

  async function uploadWebPage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setImportSummary(null);
    setUploading("url");
    try {
      const document = await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents/url`, {
        method: "POST",
        body: JSON.stringify({
          name: webPageTitle.trim() || null,
          url: webPageUrl.trim(),
          governance_source_type: governanceSourceType.trim(),
          authority_level: Number(authorityLevel),
          review_status: reviewStatus,
        }),
      });
      setProgressByRun((current) => ({ ...current, [documentProgressKey(document)]: 22 }));
      setImportSummary(`Queued web page: ${document.name}`);
      setUploadProgress(100);
      setWebPageTitle("");
      setWebPageUrl("");
      await loadDocuments();
      setActiveView("activity");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Web page import failed");
    } finally {
      window.setTimeout(() => {
        setUploading(null);
        setUploadProgress(0);
      }, 650);
    }
  }

  async function reprocessDocument(documentId: string) {
    try {
      const document = await apiRequest<DocumentItem>(`/api/v1/documents/${documentId}/reprocess`, {
        method: "POST",
      });
      setProgressByRun((current) => ({ ...current, [documentProgressKey(document)]: 18 }));
      await loadDocuments();
      setActiveView("activity");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reprocess failed");
    }
  }

  async function openDocumentPreview(document: DocumentItem) {
    setPreviewDocument(document);
    setPreviewChunks([]);
    setPreviewContent("");
    setPreviewContentSource("chunks");
    setPreviewError(null);
    setPreviewCopied(false);
    setPreviewLoading(true);
    try {
      const response = await apiRequest<{ data: ChunkItem[] }>(`/api/v1/documents/${document.id}/chunks`);
      setPreviewChunks(response.data);
      try {
        const contentResponse = await apiRequest<DocumentContent>(`/api/v1/documents/${document.id}/content`);
        setPreviewContent(contentResponse.content);
        setPreviewContentSource("parsed");
      } catch (contentError) {
        if (!(contentError instanceof ApiError && contentError.status === 404)) {
          throw contentError;
        }
        setPreviewContent(mergeChunkContent(response.data).content);
        setPreviewContentSource("chunks");
      }
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Load content failed");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function copyPreviewContent() {
    if (!previewContent) return;
    await navigator.clipboard.writeText(previewContent);
    setPreviewCopied(true);
    window.setTimeout(() => setPreviewCopied(false), 1200);
  }

  async function deleteDocument(document: DocumentItem) {
    const accepted = await confirm({
      title: `Delete ${document.name}?`,
      description: "The document record, stored chunks, and vector entries will be removed.",
      confirmLabel: "Delete document",
      cancelLabel: "Keep",
      variant: "destructive",
    });
    if (!accepted) return;
    try {
      await apiRequest<void>(`/api/v1/documents/${document.id}`, { method: "DELETE" });
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function openGovernance(document: DocumentItem, nextView: GovernanceWorkspaceView = "overview") {
    setGovernanceDocument(document);
    setGovernanceView(nextView);
    setGovernanceForm({
      governance_source_type: document.governance_source_type,
      authority_level: String(document.authority_level),
      review_status: document.review_status,
      change_summary: "",
    });
    setContentForm({
      content: "",
      file_type: editableFileType(document.file_type),
      change_summary: "",
    });
    setGovernanceContentSource("empty");
    setVersions([]);
    setAuditLogs([]);
    setGovernanceError(null);
    setGovernanceLoading(true);
    try {
      const [versionResponse, auditResponse] = await Promise.all([
        apiRequest<{ data: DocumentVersionItem[] }>(`/api/v1/documents/${document.id}/versions`),
        apiRequest<{ data: DocumentAuditLogItem[] }>(`/api/v1/documents/${document.id}/audit-logs`),
      ]);
      setVersions(versionResponse.data);
      setAuditLogs(auditResponse.data);
      try {
        const contentResponse = await apiRequest<DocumentContent>(`/api/v1/documents/${document.id}/content`);
        setContentForm((current) => ({
          ...current,
          content: contentResponse.content,
          file_type: contentResponse.content_type.includes("text/plain") ? "txt" : editableFileType(document.file_type),
        }));
        setGovernanceContentSource("parsed");
      } catch (contentError) {
        if (!(contentError instanceof ApiError && contentError.status === 404)) {
          throw contentError;
        }
        const chunkResponse = await apiRequest<{ data: ChunkItem[] }>(`/api/v1/documents/${document.id}/chunks`);
        setContentForm((current) => ({
          ...current,
          content: mergeChunkContent(chunkResponse.data).content,
          file_type: editableFileType(document.file_type),
        }));
        setGovernanceContentSource(chunkResponse.data.length > 0 ? "chunks" : "empty");
      }
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Load governance history failed");
    } finally {
      setGovernanceLoading(false);
    }
  }

  async function updateGovernance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!governanceDocument) return;
    setGovernanceError(null);
    setGovernanceLoading(true);
    try {
      const updated = await apiRequest<DocumentItem>(`/api/v1/documents/${governanceDocument.id}/governance`, {
        method: "PATCH",
        body: JSON.stringify({
          governance_source_type: governanceForm.governance_source_type.trim(),
          authority_level: Number(governanceForm.authority_level),
          review_status: governanceForm.review_status,
          change_summary: governanceForm.change_summary || null,
        }),
      });
      setGovernanceDocument(updated);
      setGovernanceForm((current) => ({ ...current, change_summary: "" }));
      await loadDocuments();
      await openGovernance(updated, "monitor");
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Update governance failed");
    } finally {
      setGovernanceLoading(false);
    }
  }

  async function updateDocumentContent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!governanceDocument) return;
    const accepted = await confirm({
      title: "Save edited content?",
      description: "BYOB will replace the retrievable source text, delete old vectors, and queue this document for re-indexing.",
      confirmLabel: "Save and re-index",
      cancelLabel: "Cancel",
    });
    if (!accepted) return;
    setGovernanceError(null);
    setContentSaving(true);
    try {
      const updated = await apiRequest<DocumentItem>(`/api/v1/documents/${governanceDocument.id}/content`, {
        method: "PATCH",
        body: JSON.stringify({
          content: contentForm.content,
          file_type: contentForm.file_type,
          change_summary: contentForm.change_summary || null,
        }),
      });
      setGovernanceDocument(updated);
      setProgressByRun((current) => ({ ...current, [documentProgressKey(updated)]: 18 }));
      setContentForm((current) => ({ ...current, change_summary: "" }));
      await loadDocuments();
      await openGovernance(updated, "monitor");
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Update content failed");
    } finally {
      setContentSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        className="flex-col items-start sm:flex-row sm:items-end"
        title="Documents"
        description="Operate source ingestion, governance, and vector indexing from one production RAG workspace."
        action={
          <div className="w-full rounded-lg border border-slate-200 bg-white p-3 shadow-sm sm:w-72">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
              <Database className="h-3.5 w-3.5" /> Knowledge base
            </div>
            <Select value={kbId} onChange={(event) => selectKnowledgeBase(event.target.value)}>
              {kbs.length === 0 && <option value="">No knowledge bases</option>}
              {kbs.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <Card className="animate-fade-up p-2">
        <div className="grid gap-2 md:grid-cols-4">
          <WorkspaceNavButton
            active={activeView === "overview"}
            icon={<Layers3 className="h-4 w-4" />}
            title="Overview"
            detail="Workspace status"
            onClick={() => setActiveView("overview")}
          />
          <WorkspaceNavButton
            active={activeView === "import"}
            icon={<Upload className="h-4 w-4" />}
            title="Import"
            detail="Add sources"
            onClick={() => setActiveView("import")}
          />
          <WorkspaceNavButton
            active={activeView === "library"}
            icon={<ListFilter className="h-4 w-4" />}
            title="Library"
            detail="Manage documents"
            onClick={() => setActiveView("library")}
          />
          <WorkspaceNavButton
            active={activeView === "activity"}
            icon={<Activity className="h-4 w-4" />}
            title="Activity"
            detail="Track indexing"
            onClick={() => setActiveView("activity")}
          />
        </div>
      </Card>

      {activeView === "overview" && (
      <>
      <Card className="animate-fade-up overflow-hidden p-0">
        <div className="border-b border-slate-200 bg-white px-6 py-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700">
                <Layers3 className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium uppercase text-slate-500">Workspace overview</p>
                <h2 className="text-lg font-semibold text-slate-950">
                  {currentKnowledgeBase?.name ?? "Select a knowledge base"}
                </h2>
                <p className="text-sm text-slate-500">Published sources are available to Agent retrieval by default.</p>
              </div>
            </div>
            <Badge variant={activeDocuments.length > 0 ? "info" : documentStats.failed > 0 ? "warning" : "success"}>
              {activeDocuments.length > 0
                ? `${formatNumber(activeDocuments.length)} indexing`
                : documentStats.failed > 0
                  ? `${formatNumber(documentStats.failed)} failed`
                  : "healthy"}
            </Badge>
          </div>
        </div>
        <div className="grid gap-0 divide-y divide-slate-100 bg-slate-50/50 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-5">
          <MetricTile label="Documents" value={formatNumber(documentStats.total)} detail={`${formatNumber(documentStats.chunks)} chunks`} />
          <MetricTile label="Published" value={formatNumber(documentStats.published)} detail="retrieval ready" tone="success" />
          <MetricTile label="Review queue" value={formatNumber(documentStats.draftLike)} detail="draft or reviewed" tone="warning" />
          <MetricTile label="Indexing" value={formatNumber(documentStats.active)} detail="worker activity" tone="info" />
          <MetricTile label="Failed" value={formatNumber(documentStats.failed)} detail="requires action" tone={documentStats.failed > 0 ? "danger" : "muted"} />
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        <WorkspaceModuleCard
          icon={<Upload className="h-5 w-5" />}
          title="Import sources"
          detail="Create text documents or batch import files with a required governance policy."
          meta={governanceReady ? "Policy ready" : "Policy required"}
          onClick={() => setActiveView("import")}
        />
        <WorkspaceModuleCard
          icon={<ListFilter className="h-5 w-5" />}
          title="Document library"
          detail="Search, preview, govern, reprocess, and delete indexed source documents."
          meta={`${formatNumber(filteredDocuments.length)} visible`}
          onClick={() => setActiveView("library")}
        />
        <WorkspaceModuleCard
          icon={<Activity className="h-5 w-5" />}
          title="Indexing activity"
          detail="Monitor running ingestion jobs and inspect failed document pipelines."
          meta={activeDocuments.length > 0 ? `${formatNumber(activeDocuments.length)} running` : "Idle"}
          onClick={() => setActiveView("activity")}
        />
      </div>
      </>
      )}

      {activeView === "import" && importSummary && <p className="rounded bg-emerald-50 p-3 text-sm text-emerald-700">{importSummary}</p>}

      {activeView === "import" && (
      <Card className="animate-fade-up overflow-hidden p-0">
        <div className="border-b border-slate-200 px-6 py-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>Ingestion workbench</CardTitle>
              <CardDescription>Set source governance once, then import text, files, or web pages into the selected knowledge base.</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => setActiveView("overview")} className="gap-2">
                <ArrowLeft className="h-4 w-4" /> Overview
              </Button>
              <Badge variant={governanceReady ? "success" : "warning"}>
                {governanceReady ? "policy ready" : "policy required"}
              </Badge>
            </div>
          </div>
        </div>
        <div className="grid lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="grid divide-y divide-slate-100 xl:grid-cols-3 xl:divide-x xl:divide-y-0">
            <form className="space-y-4 p-6" onSubmit={uploadText}>
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-100 bg-blue-50 text-blue-700">
                  <Type className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-semibold text-slate-950">Direct text</p>
                  <p className="text-sm text-slate-500">Create a managed text document.</p>
                </div>
              </div>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Document name"
                required
              />
              <Textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="Content"
                required
                className="min-h-40"
              />
              <Button type="submit" disabled={!kbId || uploading !== null || !governanceReady} className="gap-2">
                <Upload className="h-4 w-4" /> {uploading === "text" ? "Queueing" : "Upload text"}
              </Button>
            </form>

            <form className="space-y-4 p-6" onSubmit={uploadFiles}>
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-100 bg-emerald-50 text-emerald-700">
                  <FileUp className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-semibold text-slate-950">Batch files</p>
                  <p className="text-sm text-slate-500">Import PDF, DOCX, PPT, PPTX, XLSX, Markdown, TXT, HTML, JPEG, or PNG.</p>
                </div>
              </div>
              <Input
                key={fileInputKey}
                type="file"
                multiple
                accept=".pdf,.docx,.ppt,.pptx,.xlsx,.md,.markdown,.txt,.html,.jpg,.jpeg,.png"
                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                required
              />
              {files.length > 0 && (
                <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                  {files.slice(0, 4).map((file) => (
                    <Badge key={`${file.name}-${file.size}`} variant="muted" className="max-w-48 truncate">
                      {file.name}
                    </Badge>
                  ))}
                  {files.length > 4 && <Badge variant="muted">+{formatNumber(files.length - 4)} more</Badge>}
                </div>
              )}
              <Button type="submit" disabled={!kbId || files.length === 0 || uploading !== null || !governanceReady} className="gap-2">
                <Upload className="h-4 w-4" /> {uploading === "files" ? "Queueing" : "Import files"}
              </Button>
            </form>

            <form className="space-y-4 p-6" onSubmit={uploadWebPage}>
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-violet-100 bg-violet-50 text-violet-700">
                  <Globe2 className="h-4 w-4" />
                </div>
                <div>
                  <p className="font-semibold text-slate-950">Web page</p>
                  <p className="text-sm text-slate-500">Fetch an article or page by URL.</p>
                </div>
              </div>
              <Input
                type="url"
                value={webPageUrl}
                onChange={(event) => setWebPageUrl(event.target.value)}
                placeholder="https://example.com/article"
                required
              />
              <Input
                value={webPageTitle}
                onChange={(event) => setWebPageTitle(event.target.value)}
                placeholder="Optional title"
              />
              <Button type="submit" disabled={!kbId || uploading !== null || !governanceReady || !webPageUrl.trim()} className="gap-2">
                <Upload className="h-4 w-4" /> {uploading === "url" ? "Queueing" : "Import page"}
              </Button>
            </form>
          </div>

          <aside className="border-t border-slate-200 bg-slate-50/70 p-6 lg:border-l lg:border-t-0">
            <div className="space-y-5">
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700">
                    <ShieldCheck className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="font-semibold text-slate-950">Import policy</p>
                    <p className="text-sm text-slate-500">Applied to every new source.</p>
                  </div>
                </div>
                <GovernanceFields
                  sourceType={governanceSourceType}
                  authorityLevel={authorityLevel}
                  reviewStatus={reviewStatus}
                  onSourceTypeChange={setGovernanceSourceType}
                  onAuthorityLevelChange={setAuthorityLevel}
                  onReviewStatusChange={setReviewStatus}
                  sourceOptions={sourceOptions}
                  compact
                />
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700">
                    <Activity className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-950">Track after queueing</p>
                    <p className="mt-1 text-sm text-slate-500">Open Activity to monitor parsing, embedding, and vector indexing.</p>
                    <Button type="button" variant="outline" onClick={() => setActiveView("activity")} className="mt-3 gap-2">
                      Open activity <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </Card>
      )}

      {activeView === "activity" && (
      <Card className="animate-fade-up overflow-hidden p-0">
        <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5 sm:flex sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700">
              <Activity className="h-4 w-4" />
            </div>
            <div>
              <CardTitle>Indexing activity</CardTitle>
              <CardDescription>Track running ingestion jobs and identify documents that need operator action.</CardDescription>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setActiveView("overview")} className="gap-2">
              <ArrowLeft className="h-4 w-4" /> Overview
            </Button>
            <Button type="button" variant="outline" onClick={() => setActiveView("import")} className="gap-2">
              <Upload className="h-4 w-4" /> Import sources
            </Button>
          </div>
        </CardHeader>
        <div className="grid gap-0 divide-y divide-slate-100 lg:grid-cols-[minmax(0,1fr)_20rem] lg:divide-x lg:divide-y-0">
          <div className="p-6">
            {latestActiveDocument ? (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="font-semibold text-slate-950">{latestActiveDocument.name}</p>
                    <p className="mt-1 text-sm text-slate-500">{documentStage(latestActiveDocument, latestProgress)}</p>
                  </div>
                  <Badge variant={statusVariant(latestActiveDocument.status)}>{latestActiveDocument.status}</Badge>
                </div>
                <ProgressBar
                  value={latestProgress}
                  tone={documentProgressTone(latestActiveDocument)}
                  indeterminate={latestProgress < 100}
                  label="Embedding pipeline"
                  detail={latestActiveDocument.status}
                />
                <StepRail steps={progressSteps(latestActiveDocument, latestProgress)} />
              </div>
            ) : uploading ? (
              <div className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="font-semibold text-slate-950">
                      {uploading === "files" ? "Uploading files" : uploading === "url" ? "Importing web page" : "Uploading text"}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {uploading === "files"
                        ? `Queueing ${formatNumber(files.length)} files`
                        : uploading === "url"
                          ? webPageUrl || "Creating URL document record"
                          : "Creating document record"}
                    </p>
                  </div>
                  <Badge variant="info">requesting</Badge>
                </div>
                <ProgressBar value={uploadProgress} tone="blue" label="Upload request" detail="Sending to API" />
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
                <p className="font-medium text-slate-950">No active ingestion job</p>
                <p className="mt-1 text-sm text-slate-500">Start an import to watch parsing, embedding, and indexing progress here.</p>
              </div>
            )}
          </div>
          <aside className="bg-slate-50/70 p-6">
            <p className="text-sm font-semibold text-slate-950">Queue summary</p>
            <div className="mt-4 space-y-3">
              <QueueSummaryRow label="Running" value={formatNumber(documentStats.active)} tone="info" />
              <QueueSummaryRow label="Failed" value={formatNumber(documentStats.failed)} tone={documentStats.failed > 0 ? "danger" : "muted"} />
              <QueueSummaryRow label="Completed" value={formatNumber(documentStats.byFilter.all - documentStats.active - documentStats.failed)} tone="success" />
            </div>
          </aside>
        </div>
      </Card>
      )}

      {activeView === "library" && (
      <Card className="animate-fade-up overflow-hidden p-0" style={{ animationDelay: "120ms" }}>
        <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5 sm:flex sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700">
              <ListFilter className="h-4 w-4" />
            </div>
            <div>
              <CardTitle>Document registry</CardTitle>
              <CardDescription>
                {formatNumber(filteredDocuments.length)} visible of {formatNumber(documents.length)} documents.
              </CardDescription>
            </div>
          </div>
          <Badge variant={activeDocuments.length > 0 ? "info" : "muted"}>
            {activeDocuments.length > 0 ? `${formatNumber(activeDocuments.length)} processing` : "idle"}
          </Badge>
          <Button type="button" variant="outline" onClick={() => setActiveView("overview")} className="gap-2">
            <ArrowLeft className="h-4 w-4" /> Overview
          </Button>
        </CardHeader>
        <div className="border-b border-slate-100 bg-slate-50/60 px-6 py-4">
          <div className="grid gap-3 xl:grid-cols-[minmax(16rem,1fr)_14rem_16rem] xl:items-end">
            <div className="space-y-1">
              <Label>Search</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={documentSearch}
                  onChange={(event) => setDocumentSearch(event.target.value)}
                  placeholder="Search documents"
                  className="pl-9"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Status</Label>
              <Select value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value as DocumentFilter)}>
                {DOCUMENT_FILTERS.map((filter) => (
                  <option key={filter.value} value={filter.value}>
                    {filter.label} ({formatNumber(documentStats.byFilter[filter.value])})
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Source type</Label>
              <Select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
                <option value="all">All source types</option>
                {sourceOptions.map((source) => (
                  <option key={source} value={source}>
                    {governanceSourceLabel(source)}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </div>
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Source</TH>
              <TH>Governance</TH>
              <TH>Status</TH>
              <TH>Embedding progress</TH>
              <TH className="text-right">Chunks</TH>
              <TH>Created</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {filteredDocuments.map((document) => {
              const progress = documentProgress(document, progressByRun[documentProgressKey(document)]);
              const failed = document.status.toLowerCase() === "failed";
              const completed = document.status.toLowerCase() === "completed";

              return (
                <TR key={document.id} className="animate-fade-up">
                  <TD>
                    <div className="flex items-start gap-2">
                      {failed ? (
                        <CircleAlert className="mt-0.5 h-4 w-4 text-red-500" />
                      ) : completed ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-500" />
                      ) : (
                        <Clock3 className="mt-0.5 h-4 w-4 text-cyan-500" />
                      )}
                      <div className="min-w-0">
                        <p className="truncate font-medium">{document.name}</p>
                        {document.error_message && (
                          <p className="max-w-md truncate text-xs text-red-600">{document.error_message}</p>
                        )}
                      </div>
                    </div>
                  </TD>
                  <TD className="text-slate-500">
                    {document.source_type} / {document.file_type ?? "-"}
                  </TD>
                  <TD>
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant={reviewStatusVariant(document.review_status)}>{document.review_status}</Badge>
                        <Badge variant="muted">{authorityLabel(document.authority_level)}</Badge>
                      </div>
                      <span className="text-xs text-slate-500">{governanceSourceLabel(document.governance_source_type)} · v{document.current_version}</span>
                    </div>
                  </TD>
                  <TD>
                    <Badge variant={statusVariant(document.status)}>{document.status}</Badge>
                  </TD>
                  <TD className="min-w-56">
                    <ProgressBar
                      value={progress}
                      tone={documentProgressTone(document)}
                      label={documentStage(document, progress)}
                      indeterminate={isActiveDocument(document)}
                      showValue
                    />
                  </TD>
                  <TD className="text-right tabular-nums">{document.chunk_count}</TD>
                  <TD className="text-slate-500">{formatDate(document.created_at)}</TD>
                  <TD className="text-right">
                    <div className="inline-flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => openDocumentPreview(document)}
                        title="View content"
                        aria-label={`View ${document.name}`}
                        className="h-9 w-9 p-0"
                      >
                        <FileText className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => openGovernance(document)}
                        title="Governance"
                        aria-label={`Edit governance for ${document.name}`}
                        className="h-9 w-9 p-0"
                      >
                        <ShieldCheck className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => reprocessDocument(document.id)}
                        title="Reprocess"
                        aria-label={`Reprocess ${document.name}`}
                        className="h-9 w-9 p-0"
                      >
                        <RefreshCcw className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        onClick={() => deleteDocument(document)}
                        title="Delete"
                        aria-label={`Delete ${document.name}`}
                        className="h-9 w-9 p-0"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TD>
                </TR>
              );
            })}
            {filteredDocuments.length === 0 && (
              <TR>
                <TD colSpan={8} className="text-center text-sm text-slate-500">
                  {documents.length === 0
                    ? kbId
                      ? "No documents yet."
                      : "Select a knowledge base to view documents."
                    : "No documents match the current filters."}
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Card>
      )}

      <Modal
        open={previewDocument !== null}
        onClose={() => setPreviewDocument(null)}
        title={previewDocument?.name ?? "Document content"}
        description={previewDocument ? `${previewDocument.source_type} / ${previewDocument.file_type ?? "-"}` : undefined}
        className="flex h-[calc(100vh-2rem)] max-h-[56rem] max-w-6xl flex-col overflow-hidden"
      >
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
          {previewDocument && (
            <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={statusVariant(previewDocument.status)}>{previewDocument.status}</Badge>
                <Badge variant="muted">{formatNumber(previewChunks.length)} chunks</Badge>
                <Badge variant={previewContentSource === "parsed" ? "success" : "warning"}>
                  {previewContentSource === "parsed" ? "Parsed snapshot" : "Chunk fallback"}
                </Badge>
                <Badge variant={reviewStatusVariant(previewDocument.review_status)}>{previewDocument.review_status}</Badge>
                <Badge variant="muted">{authorityLabel(previewDocument.authority_level)}</Badge>
                <span className="text-xs text-slate-500">Created {formatDate(previewDocument.created_at)}</span>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={copyPreviewContent}
                disabled={!previewContent || previewLoading}
                className="gap-2"
              >
                <Copy className="h-4 w-4" /> {previewCopied ? "Copied" : "Copy"}
              </Button>
            </div>
          )}

          {previewLoading && (
            <div className="flex min-h-48 items-center justify-center rounded-lg border border-dashed border-slate-200 text-sm text-slate-500">
              <InlineSpinner className="mr-2 text-blue-600" /> Loading content
            </div>
          )}

          {!previewLoading && previewError && (
            <div className="rounded-lg border border-red-100 bg-red-50 p-4 text-sm text-red-700">
              {previewError}
            </div>
          )}

          {!previewLoading && !previewError && previewChunks.length === 0 && !previewContent && (
            <div className="rounded-lg border border-amber-100 bg-amber-50 p-4 text-sm text-amber-800">
              No parsed content is available yet.
            </div>
          )}

          {!previewLoading && !previewError && (previewContent || previewChunks.length > 0) && (
            <DocumentContentViewer
              content={previewContent}
              chunks={previewChunks}
              fileType={previewDocument?.file_type ?? null}
            />
          )}
        </div>
      </Modal>

      <Modal
        open={governanceDocument !== null}
        onClose={() => setGovernanceDocument(null)}
        title={governanceDocument ? `Governance - ${governanceDocument.name}` : "Governance"}
        description="Control which sources can enter formal Agent retrieval and keep an audit trail."
        className="flex h-[calc(100vh-2rem)] max-h-[56rem] max-w-6xl flex-col overflow-hidden"
      >
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
          {governanceDocument && (
            <div className="shrink-0 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={statusVariant(governanceDocument.status)}>{governanceDocument.status}</Badge>
                <Badge variant={reviewStatusVariant(governanceDocument.review_status)}>{governanceDocument.review_status}</Badge>
                <Badge variant="muted">{authorityLabel(governanceDocument.authority_level)}</Badge>
                <Badge variant="muted">v{governanceDocument.current_version}</Badge>
                <Badge variant="muted">{formatNumber(governanceDocument.chunk_count)} chunks</Badge>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                {governanceSourceLabel(governanceDocument.governance_source_type)} · updated {formatDate(governanceDocument.updated_at)}
              </p>
            </div>
          )}

          {governanceError && <p className="shrink-0 rounded bg-red-50 p-3 text-sm text-red-700">{governanceError}</p>}

          <div className="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[18rem_minmax(0,1fr)]">
            <aside className="min-h-0 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-2">
              <GovernanceLevelButton
                active={governanceView === "overview"}
                icon={<Layers3 className="h-4 w-4" />}
                title="Overview"
                detail="Status and next step"
                onClick={() => setGovernanceView("overview")}
              />
              <GovernanceLevelButton
                active={governanceView === "policy"}
                icon={<ShieldCheck className="h-4 w-4" />}
                title="Policy"
                detail="Source and review labels"
                onClick={() => setGovernanceView("policy")}
              />
              <GovernanceLevelButton
                active={governanceView === "content"}
                icon={<FileText className="h-4 w-4" />}
                title="Content"
                detail="Edit source and re-index"
                onClick={() => setGovernanceView("content")}
              />
              <GovernanceLevelButton
                active={governanceView === "monitor"}
                icon={<Activity className="h-4 w-4" />}
                title="Monitor"
                detail="Progress, versions, audit"
                onClick={() => setGovernanceView("monitor")}
              />
            </aside>

            <section className="min-h-0 overflow-y-auto pr-1">
              {governanceView === "overview" && governanceDocument && (
                <div className="space-y-4">
                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-medium text-slate-950">Document state</p>
                        <p className="mt-1 text-sm text-slate-500">{documentStage(governanceDocument, governanceProgress)}</p>
                      </div>
                      {governanceLoading && <InlineSpinner className="text-blue-600" />}
                    </div>
                    <ProgressBar
                      value={governanceProgress}
                      tone={documentProgressTone(governanceDocument)}
                      label="Indexing progress"
                      detail={governanceIngestionProgress?.stage ?? governanceDocument.status}
                      indeterminate={isActiveDocument(governanceDocument)}
                    />
                    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      <QueueSummaryRow label="Source" value={governanceSourceLabel(governanceDocument.governance_source_type)} tone="muted" />
                      <QueueSummaryRow label="Review" value={governanceDocument.review_status} tone="info" />
                      <QueueSummaryRow label="Version" value={`v${governanceDocument.current_version}`} tone="info" />
                      <QueueSummaryRow label="Chunks" value={formatNumber(governanceDocument.chunk_count)} tone="success" />
                    </div>
                  </div>

                  <div className="grid gap-3 lg:grid-cols-3">
                    <WorkspaceModuleCard
                      icon={<ShieldCheck className="h-5 w-5" />}
                      title="Policy"
                      detail="Adjust authority and release status."
                      meta={governanceDocument.review_status}
                      onClick={() => setGovernanceView("policy")}
                    />
                    <WorkspaceModuleCard
                      icon={<FileText className="h-5 w-5" />}
                      title="Content"
                      detail="Update retrievable source text."
                      meta={governanceContentSourceLabel(governanceContentSource)}
                      onClick={() => setGovernanceView("content")}
                    />
                    <WorkspaceModuleCard
                      icon={<History className="h-5 w-5" />}
                      title="Monitor"
                      detail="Review progress and audit records."
                      meta={`${formatNumber(versions.length)} versions`}
                      onClick={() => setGovernanceView("monitor")}
                    />
                  </div>
                </div>
              )}

              {governanceView === "policy" && (
                <form className="rounded-lg border border-slate-200 bg-white p-4" onSubmit={updateGovernance}>
                  <div className="mb-4 flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-slate-500" />
                    <p className="font-medium text-slate-900">Governance policy</p>
                  </div>
                  <div className="space-y-4">
                    <GovernanceFields
                      sourceType={governanceForm.governance_source_type}
                      authorityLevel={governanceForm.authority_level}
                      reviewStatus={governanceForm.review_status}
                      onSourceTypeChange={(value) => setGovernanceForm((current) => ({ ...current, governance_source_type: value }))}
                      onAuthorityLevelChange={(value) => setGovernanceForm((current) => ({ ...current, authority_level: value }))}
                      onReviewStatusChange={(value) => setGovernanceForm((current) => ({ ...current, review_status: value }))}
                      sourceOptions={sourceOptions}
                    />
                    <div className="space-y-1">
                      <Label htmlFor="governance-summary">Change summary</Label>
                      <Textarea
                        id="governance-summary"
                        value={governanceForm.change_summary}
                        onChange={(event) => setGovernanceForm((current) => ({ ...current, change_summary: event.target.value }))}
                        placeholder="Why this label changed"
                        className="min-h-28"
                      />
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
                      <Button type="button" variant="outline" onClick={() => setGovernanceView("overview")} className="gap-2">
                        <ArrowLeft className="h-4 w-4" /> Overview
                      </Button>
                      <Button
                        type="submit"
                        disabled={
                          governanceLoading ||
                          !governanceForm.governance_source_type.trim() ||
                          !isValidAuthorityLevel(governanceForm.authority_level) ||
                          !governanceForm.review_status
                        }
                        className="gap-2"
                      >
                        <ShieldCheck className="h-4 w-4" /> {governanceLoading ? "Saving..." : "Save policy"}
                      </Button>
                    </div>
                  </div>
                </form>
              )}

              {governanceView === "content" && (
                <form className="rounded-lg border border-slate-200 bg-white p-4" onSubmit={updateDocumentContent}>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-slate-500" />
                      <p className="font-medium text-slate-900">Editable source content</p>
                    </div>
                    <Badge variant={governanceContentSource === "parsed" ? "success" : governanceContentSource === "chunks" ? "warning" : "muted"}>
                      {governanceContentSourceLabel(governanceContentSource)}
                    </Badge>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-[8rem_minmax(0,1fr)]">
                    <div className="space-y-1">
                      <Label htmlFor="content-file-type">Type</Label>
                      <Select
                        id="content-file-type"
                        value={contentForm.file_type}
                        onChange={(event) => setContentForm((current) => ({ ...current, file_type: event.target.value }))}
                      >
                        <option value="md">Markdown</option>
                        <option value="txt">Plain text</option>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="content-summary">Edit summary</Label>
                      <Input
                        id="content-summary"
                        value={contentForm.change_summary}
                        onChange={(event) => setContentForm((current) => ({ ...current, change_summary: event.target.value }))}
                        placeholder="What changed in the source"
                      />
                    </div>
                  </div>
                  <Textarea
                    value={contentForm.content}
                    onChange={(event) => setContentForm((current) => ({ ...current, content: event.target.value }))}
                    placeholder="Load or edit document content"
                    className="mt-3 min-h-[24rem] font-mono text-xs leading-5"
                  />
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:justify-between">
                    <Button type="button" variant="outline" onClick={() => setGovernanceView("overview")} className="gap-2">
                      <ArrowLeft className="h-4 w-4" /> Overview
                    </Button>
                    <Button type="submit" disabled={contentSaving || governanceLoading || !contentForm.content.trim()} className="gap-2">
                      <RefreshCcw className="h-4 w-4" /> {contentSaving ? "Queueing..." : "Save and re-index"}
                    </Button>
                  </div>
                </form>
              )}

              {governanceView === "monitor" && (
                <div className="space-y-4">
                  {governanceDocument && (
                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Activity className="h-4 w-4 text-slate-500" />
                          <p className="font-medium text-slate-900">Processing monitor</p>
                        </div>
                        <Badge variant={statusVariant(governanceDocument.status)}>{governanceDocument.status}</Badge>
                      </div>
                      <ProgressBar
                        value={governanceProgress}
                        tone={documentProgressTone(governanceDocument)}
                        label="Current ingestion run"
                        detail={documentStage(governanceDocument, governanceProgress)}
                        indeterminate={isActiveDocument(governanceDocument)}
                      />
                      <StepRail steps={progressSteps(governanceDocument, governanceProgress)} className="mt-3" />
                      <div className="mt-4 grid gap-2 sm:grid-cols-2">
                        <QueueSummaryRow label="Chunks" value={formatNumber(governanceDocument.chunk_count)} tone="success" />
                        <QueueSummaryRow label="Version" value={`v${governanceDocument.current_version}`} tone="info" />
                        <QueueSummaryRow label="Stage" value={governanceIngestionProgress?.stage ?? "-"} tone="muted" />
                        <QueueSummaryRow label="Updated" value={governanceIngestionProgress?.updated_at ? formatDate(governanceIngestionProgress.updated_at) : "-"} tone="muted" />
                      </div>
                      {governanceDocument.error_message && (
                        <p className="mt-3 rounded bg-red-50 p-3 text-sm text-red-700">{governanceDocument.error_message}</p>
                      )}
                    </div>
                  )}

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <div className="mb-3 flex items-center gap-2">
                        <History className="h-4 w-4 text-slate-500" />
                        <p className="font-medium text-slate-900">Version history</p>
                      </div>
                      <div className="space-y-2">
                        {versions.map((version) => (
                          <div key={version.id} className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="muted">v{version.version_number}</Badge>
                              <Badge variant={reviewStatusVariant(version.review_status)}>{version.review_status}</Badge>
                              <Badge variant="muted">{authorityLabel(version.authority_level)}</Badge>
                            </div>
                            <p className="mt-2 text-slate-700">{version.change_summary ?? "No summary"}</p>
                            <p className="mt-1 text-xs text-slate-500">
                              {governanceSourceLabel(version.governance_source_type)} · {version.created_by_email ?? "system"} · {formatDate(version.created_at)}
                            </p>
                          </div>
                        ))}
                        {!governanceLoading && versions.length === 0 && (
                          <p className="text-sm text-slate-500">No versions recorded yet.</p>
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <p className="mb-3 font-medium text-slate-900">Audit log</p>
                      <div className="space-y-2">
                        {auditLogs.map((entry) => (
                          <div key={entry.id} className="rounded-md border border-slate-200 p-3 text-sm">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <Badge variant="info">{entry.action}</Badge>
                              <span className="text-xs text-slate-500">{formatDate(entry.created_at)}</span>
                            </div>
                            <p className="mt-2 text-slate-700">{entry.summary ?? "No summary"}</p>
                            <p className="mt-1 text-xs text-slate-500">Actor: {entry.actor_email ?? "system"}</p>
                          </div>
                        ))}
                        {!governanceLoading && auditLogs.length === 0 && (
                          <p className="text-sm text-slate-500">No audit entries recorded yet.</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function MetricTile({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "success" | "warning" | "info" | "danger" | "muted";
}) {
  const tones = {
    default: "bg-slate-400",
    success: "bg-emerald-500",
    warning: "bg-amber-500",
    info: "bg-sky-500",
    danger: "bg-red-500",
    muted: "bg-slate-300",
  };

  return (
    <div className="bg-white/80 px-5 py-4">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${tones[tone]}`} />
        <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-950">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  );
}

function WorkspaceNavButton({
  active,
  icon,
  title,
  detail,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-3 rounded-md px-3 py-2 text-left transition-all duration-200 ${
        active
          ? "border border-blue-200 bg-blue-50 text-blue-950 shadow-sm"
          : "border border-transparent text-slate-700 hover:border-slate-200 hover:bg-slate-50"
      }`}
    >
      <span className={active ? "text-blue-700" : "text-slate-500"}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className={active ? "block text-xs text-blue-700" : "block text-xs text-slate-500"}>{detail}</span>
      </span>
    </button>
  );
}

function GovernanceLevelButton({
  active,
  icon,
  title,
  detail,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`mb-1 flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left transition-all duration-200 ${
        active
          ? "border-blue-200 bg-white text-blue-950 shadow-sm"
          : "border-transparent text-slate-700 hover:border-slate-200 hover:bg-white"
      }`}
    >
      <span className={active ? "text-blue-700" : "text-slate-500"}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className={active ? "block text-xs text-blue-700" : "block text-xs text-slate-500"}>{detail}</span>
      </span>
    </button>
  );
}

function WorkspaceModuleCard({
  icon,
  title,
  detail,
  meta,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  meta: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-lg border border-slate-200 bg-white p-5 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 group-hover:border-blue-200 group-hover:bg-blue-50 group-hover:text-blue-700">
          {icon}
        </div>
        <ArrowRight className="h-4 w-4 text-slate-400 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-blue-600" />
      </div>
      <p className="mt-4 font-semibold text-slate-950">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{detail}</p>
      <p className="mt-4 text-xs font-medium uppercase text-slate-500">{meta}</p>
    </button>
  );
}

function QueueSummaryRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "info" | "danger" | "muted";
}) {
  const tones = {
    success: "bg-emerald-500",
    info: "bg-sky-500",
    danger: "bg-red-500",
    muted: "bg-slate-300",
  };

  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${tones[tone]}`} />
        <span className="text-sm text-slate-600">{label}</span>
      </div>
      <span className="font-medium tabular-nums text-slate-950">{value}</span>
    </div>
  );
}

function GovernanceFields({
  sourceType,
  authorityLevel,
  reviewStatus,
  onSourceTypeChange,
  onAuthorityLevelChange,
  onReviewStatusChange,
  sourceOptions = [],
  compact = false,
}: {
  sourceType: string;
  authorityLevel: string;
  reviewStatus: string;
  onSourceTypeChange: (value: string) => void;
  onAuthorityLevelChange: (value: string) => void;
  onReviewStatusChange: (value: string) => void;
  sourceOptions?: string[];
  compact?: boolean;
}) {
  const sourceDatalistId = useId();

  return (
    <div className={compact ? "grid gap-3" : "grid gap-3 sm:grid-cols-3"}>
      <div className="space-y-1">
        <Label>Source type</Label>
        <Input
          value={sourceType}
          onChange={(event) => onSourceTypeChange(event.target.value)}
          list={sourceOptions.length > 0 ? sourceDatalistId : undefined}
          placeholder="Source type"
          maxLength={100}
          required
        />
        {sourceOptions.length > 0 && (
          <datalist id={sourceDatalistId}>
            {sourceOptions.map((source) => (
              <option key={source} value={source} />
            ))}
          </datalist>
        )}
      </div>
      <div className="space-y-1">
        <Label>Authority</Label>
        <Input
          type="number"
          min={1}
          step={1}
          inputMode="numeric"
          value={authorityLevel}
          onChange={(event) => onAuthorityLevelChange(event.target.value)}
          placeholder="1"
          required
        />
      </div>
      <div className="space-y-1">
        <Label>Review status</Label>
        <Select value={reviewStatus} onChange={(event) => onReviewStatusChange(event.target.value)} required>
          <option value="">Select status</option>
          {REVIEW_STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}
