"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, Clock3, FileUp, RefreshCcw, Trash2, Type, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar, StepRail, type StepItem } from "@/components/ui/progress";
import { Label, Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiRequest } from "@/lib/api";
import { formatDate, statusVariant } from "@/lib/utils";
import type { DocumentItem, KnowledgeBase } from "@/lib/types";

type UploadMode = "text" | "file" | null;

const ACTIVE_DOCUMENT_STATUSES = new Set(["pending", "processing"]);

function isActiveDocument(document: DocumentItem) {
  return ACTIVE_DOCUMENT_STATUSES.has(document.status.toLowerCase());
}

function documentProgress(document: DocumentItem, optimisticValue: number | undefined) {
  const status = document.status.toLowerCase();
  if (status === "completed") return 100;
  if (status === "failed") return 100;
  if (status === "pending") return Math.max(optimisticValue ?? 18, 18);
  if (status === "processing") return Math.max(optimisticValue ?? 44, 44);
  return optimisticValue ?? 0;
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
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [kbId, setKbId] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<UploadMode>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [progressByDocument, setProgressByDocument] = useState<Record<string, number>>({});

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
    ? documentProgress(latestActiveDocument, progressByDocument[latestActiveDocument.id])
    : 0;

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
    setProgressByDocument((current) => {
      const next = { ...current };
      for (const document of documents) {
        next[document.id] = documentProgress(document, next[document.id]);
      }
      return next;
    });
  }, [documents]);

  useEffect(() => {
    if (!kbId || activeDocuments.length === 0) return;
    const timer = window.setInterval(() => {
      setProgressByDocument((current) => {
        const next = { ...current };
        for (const document of activeDocuments) {
          const status = document.status.toLowerCase();
          const ceiling = status === "pending" ? 38 : 94;
          const step = status === "pending" ? 4 : 7;
          next[document.id] = Math.min(ceiling, documentProgress(document, next[document.id]) + step);
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
    setUploading("text");
    try {
      const document = await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents/text`, {
        method: "POST",
        body: JSON.stringify({ name, content, file_type: "txt" }),
      });
      setProgressByDocument((current) => ({ ...current, [document.id]: 22 }));
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

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setError(null);
    setUploading("file");
    try {
      const formData = new FormData();
      formData.set("file", file);
      const document = await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents`, {
        method: "POST",
        body: formData,
      });
      setProgressByDocument((current) => ({ ...current, [document.id]: 22 }));
      setUploadProgress(100);
      setFile(null);
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

  async function reprocessDocument(documentId: string) {
    try {
      const document = await apiRequest<DocumentItem>(`/api/v1/documents/${documentId}/reprocess`, {
        method: "POST",
      });
      setProgressByDocument((current) => ({ ...current, [document.id]: 18 }));
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reprocess failed");
    }
  }

  async function deleteDocument(document: DocumentItem) {
    if (!window.confirm(`Delete ${document.name}?`)) return;
    try {
      await apiRequest<void>(`/api/v1/documents/${document.id}`, { method: "DELETE" });
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
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
                  {latestActiveDocument ? latestActiveDocument.name : uploading === "file" ? "Uploading file" : "Uploading text"}
                </p>
                <p className="text-sm text-cyan-700">
                  {latestActiveDocument
                    ? documentStage(latestActiveDocument, latestProgress)
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
            <Button type="submit" disabled={!kbId || uploading !== null} className="gap-2">
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
                <CardTitle>Upload file</CardTitle>
                <CardDescription>PDF, DOCX, Markdown, TXT, and HTML are stored in MinIO.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <form className="space-y-3" onSubmit={uploadFile}>
            <Input
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              required
            />
            <Button type="submit" disabled={!kbId || !file || uploading !== null} className="gap-2">
              <Upload className="h-4 w-4" /> {uploading === "file" ? "Queueing..." : "Upload file"}
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
              <TH>Status</TH>
              <TH>Embedding progress</TH>
              <TH className="text-right">Chunks</TH>
              <TH>Created</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {documents.map((document) => {
              const progress = documentProgress(document, progressByDocument[document.id]);
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
                <TD colSpan={7} className="text-center text-sm text-slate-500">
                  {kbId ? "No documents yet." : "Select a knowledge base to view documents."}
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Card>
    </div>
  );
}
