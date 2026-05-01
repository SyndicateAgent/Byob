"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, Database, FileText, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader, MetricTile } from "@/components/ui/page-header";
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
      icon: <BookOpen className="h-4 w-4" />,
      accent: "blue" as const,
    },
    {
      label: "Documents",
      value: formatNumber(documentCount),
      hint: "Managed source files and text entries",
      icon: <FileText className="h-4 w-4" />,
      accent: "cyan" as const,
    },
    {
      label: "Chunks",
      value: formatNumber(chunkCount),
      hint: "Searchable source-of-truth chunks",
      icon: <Database className="h-4 w-4" />,
      accent: "emerald" as const,
    },
    {
      label: "Retrieval",
      value: "Ready",
      hint: "Direct API for local AI Agents",
      icon: <Search className="h-4 w-4" />,
      accent: "amber" as const,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Local overview for your self-hosted vector database and retrieval API."
      />
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat, index) => (
          <div key={stat.label} style={{ animationDelay: `${index * 55}ms` }}>
            <MetricTile {...stat} />
          </div>
        ))}
      </div>

      <Card className="animate-fade-up overflow-hidden p-0" style={{ animationDelay: "140ms" }}>
        <CardHeader className="px-6 pt-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>Recent knowledge bases</CardTitle>
              <CardDescription>Latest Qdrant-backed collections in this instance.</CardDescription>
            </div>
            <Badge variant="info">{formatNumber(kbs.length)} total</Badge>
          </div>
        </CardHeader>
        {kbs.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-slate-500">
            No knowledge bases yet. {" "}
            <Link className="font-medium text-blue-600" href="/knowledge-bases">
              Create one
            </Link>
            .
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 px-6 pb-2">
            {kbs.slice(0, 6).map((kb, index) => (
              <li
                key={kb.id}
                className="animate-fade-up flex items-center justify-between py-3"
                style={{ animationDelay: `${index * 45}ms` }}
              >
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
