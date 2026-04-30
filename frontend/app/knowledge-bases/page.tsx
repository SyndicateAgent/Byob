"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import type { KnowledgeBase } from "@/lib/types";

export default function KnowledgeBasesPage() {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases");
    setItems(response.data);
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  async function createKb(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    await apiRequest<KnowledgeBase>("/api/v1/knowledge-bases", {
      method: "POST",
      body: JSON.stringify({ name, description: description || null }),
    });
    setName("");
    setDescription("");
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Knowledge Bases</h1>
        <p className="text-slate-500">Create and inspect tenant-scoped knowledge bases.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Create Knowledge Base</CardTitle>
          <CardDescription>Each knowledge base maps to one Qdrant collection.</CardDescription>
        </CardHeader>
        <form className="grid gap-3 md:grid-cols-[1fr_2fr_auto]" onSubmit={createKb}>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" required />
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Description"
          />
          <Button type="submit">Create</Button>
        </form>
      </Card>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-4">
        {items.map((item) => (
          <Card key={item.id}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold">{item.name}</h2>
                <p className="text-sm text-slate-500">{item.description || "No description"}</p>
                <p className="mt-2 text-xs text-slate-500">{item.qdrant_collection}</p>
              </div>
              <div className="text-right text-sm">
                <p>{item.document_count} documents</p>
                <p>{item.chunk_count} chunks</p>
                <p className="text-slate-500">{item.status}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
