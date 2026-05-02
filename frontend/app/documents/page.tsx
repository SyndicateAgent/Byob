"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, Clock3, Copy, FileText, FileUp, History, RefreshCcw, ShieldCheck, Trash2, Type, Upload } from "lucide-react";
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
import type { ChunkItem, DocumentAuditLogItem, DocumentBatchUploadResponse, DocumentContent, DocumentItem, DocumentVersionItem, KnowledgeBase } from "@/lib/types";

type UploadMode = "text" | "files" | null;
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
const GOVERNANCE_SOURCE_OPTIONS = [
  { value: "official_law", label: "Official law", level: "L1" },
  { value: "official_guidance", label: "Official guidance", level: "L2" },
  { value: "internal_sop", label: "Internal SOP", level: "L3" },
  { value: "expert_summary", label: "Reviewed expert summary", level: "L4" },
  { value: "chat_record", label: "Chat record", level: "L5" },
  { value: "video_transcript", label: "Video transcript", level: "L5" },
  { value: "other", label: "Other", level: "L5" },
] as const;
const REVIEW_STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "reviewed", label: "Reviewed" },
  { value: "published", label: "Published" },
  { value: "deprecated", label: "Deprecated" },
] as const;

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
  return GOVERNANCE_SOURCE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function reviewStatusVariant(status: string) {
  if (status === "published") return "success" as const;
  if (status === "reviewed") return "info" as const;
  if (status === "deprecated") return "muted" as const;
  return "warning" as const;
}

function authorityLabel(level: number) {
  const labels: Record<number, string> = {
    1: "L1 official",
    2: "L2 authoritative",
    3: "L3 SOP",
    4: "L4 reviewed",
    5: "L5 raw",
  };
  return labels[level] ?? `L${level}`;
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
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
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
  const [governanceForm, setGovernanceForm] = useState({
    governance_source_type: "",
    authority_level: "",
    review_status: "",
    change_summary: "",
  });
  const [versions, setVersions] = useState<DocumentVersionItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<DocumentAuditLogItem[]>([]);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [governanceError, setGovernanceError] = useState<string | null>(null);

  const governanceReady = Boolean(governanceSourceType && authorityLevel && reviewStatus);

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

  const activeDocuments = useMemo(() => documents.filter(isActiveDocument), [documents]);
  const latestActiveDocument = activeDocuments[0];
  const latestProgress = latestActiveDocument
    ? documentProgress(latestActiveDocument, progressByRun[documentProgressKey(latestActiveDocument)])
    : 0;

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
          governance_source_type: governanceSourceType,
          authority_level: Number(authorityLevel),
          review_status: reviewStatus,
        }),
      });
      setProgressByRun((current) => ({ ...current, [documentProgressKey(document)]: 22 }));
      setUploadProgress(100);
      setName("");
      setContent("");
      await loadDocuments();
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
      formData.append("governance_source_type", governanceSourceType);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch upload failed");
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

  async function openGovernance(document: DocumentItem) {
    setGovernanceDocument(document);
    setGovernanceForm({
      governance_source_type: document.governance_source_type,
      authority_level: String(document.authority_level),
      review_status: document.review_status,
      change_summary: "",
    });
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
          governance_source_type: governanceForm.governance_source_type,
          authority_level: Number(governanceForm.authority_level),
          review_status: governanceForm.review_status,
          change_summary: governanceForm.change_summary || null,
        }),
      });
      setGovernanceDocument(updated);
      setGovernanceForm((current) => ({ ...current, change_summary: "" }));
      await loadDocuments();
      await openGovernance(updated);
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Update governance failed");
    } finally {
      setGovernanceLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="Upload content and watch parsing, embedding, and indexing progress in real time."
        action={
          <div className="w-64 space-y-1">
          <Label>Knowledge base</Label>
          <Select value={kbId} onChange={(event) => setKbId(event.target.value)}>
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

      {(uploading || latestActiveDocument) && (
        <Card className="animate-soft-pop border-cyan-100 bg-cyan-50/70">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-cyan-200 bg-white text-cyan-700 shadow-sm">
                {latestActiveDocument ? <Clock3 className="h-5 w-5" /> : <Upload className="h-5 w-5" />}
              </div>
              <div>
                <p className="font-semibold text-cyan-950">
                  {latestActiveDocument ? latestActiveDocument.name : uploading === "files" ? "Uploading files" : "Uploading text"}
                </p>
                <p className="text-sm text-cyan-700">
                  {latestActiveDocument
                    ? documentStage(latestActiveDocument, latestProgress)
                    : uploading === "files"
                      ? `Queueing ${formatNumber(files.length)} files`
                      : "Creating the document record and queueing ingestion"}
                </p>
              </div>
            </div>
            <div className="w-full lg:max-w-md">
              <ProgressBar
                value={latestActiveDocument ? latestProgress : uploadProgress}
                tone={latestActiveDocument ? documentProgressTone(latestActiveDocument) : "blue"}
                indeterminate={Boolean(latestActiveDocument && latestProgress < 100)}
                label={latestActiveDocument ? "Embedding pipeline" : "Upload request"}
                detail={latestActiveDocument ? latestActiveDocument.status : "Sending to API"}
              />
            </div>
          </div>
          {latestActiveDocument && (
            <StepRail className="mt-4" steps={progressSteps(latestActiveDocument, latestProgress)} />
          )}
        </Card>
      )}
      {importSummary && <p className="rounded bg-emerald-50 p-3 text-sm text-emerald-700">{importSummary}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="animate-fade-up hover:shadow-md">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                <Type className="h-4 w-4" />
              </div>
              <div>
                <CardTitle>Upload text</CardTitle>
                <CardDescription>Send text directly to the ingestion pipeline.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <form className="space-y-3" onSubmit={uploadText}>
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
            />
            <GovernanceFields
              sourceType={governanceSourceType}
              authorityLevel={authorityLevel}
              reviewStatus={reviewStatus}
              onSourceTypeChange={setGovernanceSourceType}
              onAuthorityLevelChange={setAuthorityLevel}
              onReviewStatusChange={setReviewStatus}
            />
            <Button type="submit" disabled={!kbId || uploading !== null || !governanceReady} className="gap-2">
              <Upload className="h-4 w-4" /> {uploading === "text" ? "Queueing..." : "Upload text"}
            </Button>
          </form>
        </Card>

        <Card className="animate-fade-up hover:shadow-md" style={{ animationDelay: "80ms" }}>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                <FileUp className="h-4 w-4" />
              </div>
              <div>
                <CardTitle>Batch import files</CardTitle>
                <CardDescription>PDF, DOCX, Markdown, TXT, and HTML are stored in MinIO; duplicates are skipped.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <form className="space-y-3" onSubmit={uploadFiles}>
            <Input
              key={fileInputKey}
              type="file"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
              required
            />
            {files.length > 0 && (
              <p className="text-xs text-slate-500">
                {formatNumber(files.length)} selected
              </p>
            )}
            <GovernanceFields
              sourceType={governanceSourceType}
              authorityLevel={authorityLevel}
              reviewStatus={reviewStatus}
              onSourceTypeChange={setGovernanceSourceType}
              onAuthorityLevelChange={setAuthorityLevel}
              onReviewStatusChange={setReviewStatus}
            />
            <Button type="submit" disabled={!kbId || files.length === 0 || uploading !== null || !governanceReady} className="gap-2">
              <Upload className="h-4 w-4" /> {uploading === "files" ? "Queueing..." : "Import files"}
            </Button>
          </form>
        </Card>
      </div>

      <Card className="animate-fade-up p-0" style={{ animationDelay: "120ms" }}>
        <CardHeader className="px-6 pt-6">
          <CardTitle>Documents</CardTitle>
          <CardDescription>
            Documents in the selected knowledge base. Active rows refresh automatically while embedding runs.
          </CardDescription>
        </CardHeader>
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
            {documents.map((document) => {
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
                      >
                        <FileText className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => openGovernance(document)}
                        title="Governance"
                      >
                        <ShieldCheck className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => reprocessDocument(document.id)}
                        title="Reprocess"
                      >
                        <RefreshCcw className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        onClick={() => deleteDocument(document)}
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TD>
                </TR>
              );
            })}
            {documents.length === 0 && (
              <TR>
                <TD colSpan={8} className="text-center text-sm text-slate-500">
                  {kbId ? "No documents yet." : "Select a knowledge base to view documents."}
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Card>

      <Modal
        open={previewDocument !== null}
        onClose={() => setPreviewDocument(null)}
        title={previewDocument?.name ?? "Document content"}
        description={previewDocument ? `${previewDocument.source_type} / ${previewDocument.file_type ?? "-"}` : undefined}
        className="max-h-[88vh] max-w-6xl overflow-hidden"
      >
        <div className="flex max-h-[calc(88vh-8rem)] flex-col gap-4">
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
        className="max-h-[88vh] max-w-5xl overflow-hidden"
      >
        <div className="grid max-h-[calc(88vh-8rem)] gap-5 overflow-auto lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <form className="space-y-4" onSubmit={updateGovernance}>
            <GovernanceFields
              sourceType={governanceForm.governance_source_type}
              authorityLevel={governanceForm.authority_level}
              reviewStatus={governanceForm.review_status}
              onSourceTypeChange={(value) => setGovernanceForm((current) => ({ ...current, governance_source_type: value }))}
              onAuthorityLevelChange={(value) => setGovernanceForm((current) => ({ ...current, authority_level: value }))}
              onReviewStatusChange={(value) => setGovernanceForm((current) => ({ ...current, review_status: value }))}
            />
            <div className="space-y-1">
              <Label htmlFor="governance-summary">Change summary</Label>
              <Textarea
                id="governance-summary"
                value={governanceForm.change_summary}
                onChange={(event) => setGovernanceForm((current) => ({ ...current, change_summary: event.target.value }))}
                placeholder="Why this label changed"
              />
            </div>
            {governanceError && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{governanceError}</p>}
            <Button
              type="submit"
              disabled={
                governanceLoading ||
                !governanceForm.governance_source_type ||
                !governanceForm.authority_level ||
                !governanceForm.review_status
              }
              className="gap-2"
            >
              <ShieldCheck className="h-4 w-4" /> {governanceLoading ? "Saving..." : "Save governance"}
            </Button>
          </form>

          <div className="space-y-4">
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
      </Modal>
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
}: {
  sourceType: string;
  authorityLevel: string;
  reviewStatus: string;
  onSourceTypeChange: (value: string) => void;
  onAuthorityLevelChange: (value: string) => void;
  onReviewStatusChange: (value: string) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="space-y-1">
        <Label>Source type</Label>
        <Select value={sourceType} onChange={(event) => onSourceTypeChange(event.target.value)} required>
          <option value="">Select source</option>
          {GOVERNANCE_SOURCE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.level} · {option.label}
            </option>
          ))}
        </Select>
      </div>
      <div className="space-y-1">
        <Label>Authority</Label>
        <Select value={authorityLevel} onChange={(event) => onAuthorityLevelChange(event.target.value)} required>
          <option value="">Select level</option>
          {[1, 2, 3, 4, 5].map((level) => (
            <option key={level} value={String(level)}>
              {authorityLabel(level)}
            </option>
          ))}
        </Select>
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
