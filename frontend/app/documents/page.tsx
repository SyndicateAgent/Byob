"use client";

import { FormEvent, useEffect, useState } from "react";
import { RefreshCcw, Trash2, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label, Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiRequest } from "@/lib/api";
import { formatDate, statusVariant } from "@/lib/utils";
import type { DocumentItem, KnowledgeBase } from "@/lib/types";

export default function DocumentsPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [kbId, setKbId] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    loadKnowledgeBases().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : "Load failed"),
    );
  }, []);

  useEffect(() => {
    loadDocuments().catch(() => undefined);
  }, [kbId]);

  async function uploadText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents/text`, {
        method: "POST",
        body: JSON.stringify({ name, content, file_type: "txt" }),
      });
      setName("");
      setContent("");
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setError(null);
    try {
      const formData = new FormData();
      formData.set("file", file);
      await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents`, {
        method: "POST",
        body: formData,
      });
      setFile(null);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function reprocessDocument(documentId: string) {
    try {
      await apiRequest<DocumentItem>(`/api/v1/documents/${documentId}/reprocess`, {
        method: "POST",
      });
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
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="text-sm text-slate-500">Upload content and monitor ingestion status per knowledge base.</p>
        </div>
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
      </header>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Upload text</CardTitle>
            <CardDescription>Send text directly to the ingestion pipeline.</CardDescription>
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
            <Button type="submit" disabled={!kbId} className="gap-2">
              <Upload className="h-4 w-4" /> Upload text
            </Button>
          </form>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Upload file</CardTitle>
            <CardDescription>PDF, DOCX, Markdown, TXT, and HTML are stored in MinIO.</CardDescription>
          </CardHeader>
          <form className="space-y-3" onSubmit={uploadFile}>
            <Input
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              required
            />
            <Button type="submit" disabled={!kbId || !file} className="gap-2">
              <Upload className="h-4 w-4" /> Upload file
            </Button>
          </form>
        </Card>
      </div>

      <Card className="p-0">
        <CardHeader className="px-6 pt-6">
          <CardTitle>Documents</CardTitle>
          <CardDescription>Documents in the selected knowledge base.</CardDescription>
        </CardHeader>
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Source</TH>
              <TH>Status</TH>
              <TH className="text-right">Chunks</TH>
              <TH>Created</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {documents.map((document) => (
              <TR key={document.id}>
                <TD>
                  <p className="font-medium">{document.name}</p>
                  {document.error_message && (
                    <p className="text-xs text-red-600">{document.error_message}</p>
                  )}
                </TD>
                <TD className="text-slate-500">
                  {document.source_type} / {document.file_type ?? "—"}
                </TD>
                <TD>
                  <Badge variant={statusVariant(document.status)}>{document.status}</Badge>
                </TD>
                <TD className="text-right">{document.chunk_count}</TD>
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
            ))}
            {documents.length === 0 && (
              <TR>
                <TD colSpan={6} className="text-center text-sm text-slate-500">
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
