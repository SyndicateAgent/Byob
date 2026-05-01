"use client";

import { FormEvent, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/select";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiRequest } from "@/lib/api";
import { formatDate, formatNumber, statusVariant } from "@/lib/utils";
import type { KnowledgeBase } from "@/lib/types";

export default function KnowledgeBasesPage() {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  async function load() {
    const response = await apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases");
    setItems(response.data);
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  async function createKb(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError(null);
    try {
      await apiRequest<KnowledgeBase>("/api/v1/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ name, description: description || null }),
      });
      setName("");
      setDescription("");
      setOpen(false);
      await load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function deleteKb(item: KnowledgeBase) {
    if (!window.confirm(`Delete ${item.name} and all its documents?`)) return;
    try {
      await apiRequest(`/api/v1/knowledge-bases/${item.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Bases"
        description="Each knowledge base maps to a dedicated Qdrant collection in this self-hosted instance."
        action={
          <Button className="gap-2" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> New knowledge base
          </Button>
        }
      />
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <Card className="animate-fade-up p-0">
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Collection</TH>
              <TH className="text-right">Documents</TH>
              <TH className="text-right">Chunks</TH>
              <TH>Status</TH>
              <TH>Created</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((item) => (
              <TR key={item.id}>
                <TD>
                  <p className="font-medium">{item.name}</p>
                  {item.description && (
                    <p className="text-xs text-slate-500">{item.description}</p>
                  )}
                </TD>
                <TD className="font-mono text-xs text-slate-500">{item.qdrant_collection}</TD>
                <TD className="text-right">{formatNumber(item.document_count)}</TD>
                <TD className="text-right">{formatNumber(item.chunk_count)}</TD>
                <TD>
                  <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                </TD>
                <TD className="text-slate-500">{formatDate(item.created_at)}</TD>
                <TD className="text-right">
                  <Button variant="destructive" onClick={() => deleteKb(item)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TD>
              </TR>
            ))}
            {items.length === 0 && (
              <TR>
                <TD colSpan={7} className="text-center text-sm text-slate-500">
                  No knowledge bases yet.
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Create knowledge base"
        description="A new Qdrant collection will be provisioned with the default chunking and embedding settings."
      >
        <form className="space-y-4" onSubmit={createKb}>
          <div className="space-y-1">
            <Label htmlFor="kb-name">Name</Label>
            <Input
              id="kb-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="kb-description">Description</Label>
            <Textarea
              id="kb-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional"
            />
          </div>
          {createError && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{createError}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit">Create</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
