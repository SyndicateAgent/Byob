"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, Database, FileText, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiRequest } from "@/lib/api";
import { formatNumber, statusVariant } from "@/lib/utils";
import type { KnowledgeBase } from "@/lib/types";

export default function DashboardPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases")
      .then((response) => setKbs(response.data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  const documentCount = kbs.reduce((total, kb) => total + kb.document_count, 0);
  const chunkCount = kbs.reduce((total, kb) => total + kb.chunk_count, 0);
  const activeCount = kbs.filter((kb) => kb.status === "active").length;

  const stats = [
    {
      label: "Knowledge bases",
      value: formatNumber(kbs.length),
      hint: `${formatNumber(activeCount)} active collections`,
      icon: BookOpen,
    },
    {
      label: "Documents",
      value: formatNumber(documentCount),
      hint: "Managed source files and text entries",
      icon: FileText,
    },
    {
      label: "Chunks",
      value: formatNumber(chunkCount),
      hint: "Searchable source-of-truth chunks",
      icon: Database,
    },
    {
      label: "Retrieval",
      value: "Ready",
      hint: "Direct API for local AI Agents",
      icon: Search,
    },
  ];

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-slate-500">
            Local overview for your self-hosted vector database and retrieval API.
          </p>
        </div>
      </header>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{stat.label}</p>
                <Icon className="h-4 w-4 text-slate-400" />
              </div>
              <p className="mt-3 text-2xl font-semibold">{stat.value}</p>
              <p className="text-xs text-slate-500">{stat.hint}</p>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent knowledge bases</CardTitle>
          <CardDescription>Latest Qdrant-backed collections in this instance.</CardDescription>
        </CardHeader>
        {kbs.length === 0 ? (
          <p className="text-sm text-slate-500">
            No knowledge bases yet. {" "}
            <Link className="font-medium text-blue-600" href="/knowledge-bases">
              Create one
            </Link>
            .
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {kbs.slice(0, 6).map((kb) => (
              <li key={kb.id} className="flex items-center justify-between py-3">
                <div>
                  <Link href="/knowledge-bases" className="font-medium hover:underline">
                    {kb.name}
                  </Link>
                  <p className="text-xs text-slate-500">{kb.description || kb.qdrant_collection}</p>
                </div>
                <div className="flex items-center gap-3 text-sm text-slate-500">
                  <span>{formatNumber(kb.document_count)} docs</span>
                  <span>{formatNumber(kb.chunk_count)} chunks</span>
                  <Badge variant={statusVariant(kb.status)}>{kb.status}</Badge>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
