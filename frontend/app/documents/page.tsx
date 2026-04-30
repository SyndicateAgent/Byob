"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
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
    await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents/text`, {
      method: "POST",
      body: JSON.stringify({ name, content, file_type: "txt" }),
    });
    setName("");
    setContent("");
    await loadDocuments();
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    const formData = new FormData();
    formData.set("file", file);
    await apiRequest<DocumentItem>(`/api/v1/knowledge-bases/${kbId}/documents`, {
      method: "POST",
      body: formData,
    });
    setFile(null);
    await loadDocuments();
  }

  async function reprocessDocument(documentId: string) {
    await apiRequest<DocumentItem>(`/api/v1/documents/${documentId}/reprocess`, {
      method: "POST",
    });
    await loadDocuments();
  }

  async function deleteDocument(documentId: string) {
    await apiRequest<void>(`/api/v1/documents/${documentId}`, {
      method: "DELETE",
    });
    await loadDocuments();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-slate-500">Upload text and monitor ingestion status.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Upload Text Document</CardTitle>
          <CardDescription>Text upload queues the Phase 3 ingestion pipeline.</CardDescription>
        </CardHeader>
        <form className="space-y-3" onSubmit={uploadText}>
          <select
            className="h-10 rounded-md border border-slate-300 px-3 text-sm"
            value={kbId}
            onChange={(event) => setKbId(event.target.value)}
          >
            {kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Document name" required />
          <Textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Content" required />
          <Button type="submit" disabled={!kbId}>
            Upload
          </Button>
        </form>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Upload File</CardTitle>
          <CardDescription>PDF, DOCX, Markdown, TXT, and HTML are stored in MinIO.</CardDescription>
        </CardHeader>
        <form className="flex gap-3" onSubmit={uploadFile}>
          <Input
            type="file"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
          <Button type="submit" disabled={!kbId || !file}>
            Upload File
          </Button>
        </form>
      </Card>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-4">
        {documents.map((document) => (
          <Card key={document.id}>
            <div className="flex justify-between gap-4">
              <div>
                <h2 className="font-semibold">{document.name}</h2>
                <p className="text-sm text-slate-500">
                  {document.source_type} / {document.file_type ?? "unknown"}
                </p>
                {document.error_message && (
                  <p className="mt-2 text-sm text-red-600">{document.error_message}</p>
                )}
              </div>
              <div className="text-right text-sm">
                <p>{document.status}</p>
                <p>{document.chunk_count} chunks</p>
                <div className="mt-3 flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => reprocessDocument(document.id)}
                  >
                    Reprocess
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => deleteDocument(document.id)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
