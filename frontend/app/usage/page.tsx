"use client";

import { useEffect, useState } from "react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiRequest } from "@/lib/api";
import type { UsageDaily } from "@/lib/types";

export default function UsagePage() {
  const [items, setItems] = useState<UsageDaily[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<{ data: UsageDaily[] }>("/api/v1/usage")
      .then((response) => setItems(response.data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  const totals = items.reduce(
    (acc, item) => ({
      apiCalls: acc.apiCalls + item.api_calls,
      retrievalCalls: acc.retrievalCalls + item.retrieval_calls,
      documents: acc.documents + item.documents_uploaded,
      chunks: acc.chunks + item.chunks_created,
    }),
    { apiCalls: 0, retrievalCalls: 0, documents: 0, chunks: 0 },
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Usage</h1>
        <p className="text-slate-500">Daily tenant usage from API, ingestion, and retrieval activity.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardTitle>{totals.apiCalls}</CardTitle>
          <CardDescription>API calls</CardDescription>
        </Card>
        <Card>
          <CardTitle>{totals.retrievalCalls}</CardTitle>
          <CardDescription>Retrieval calls</CardDescription>
        </Card>
        <Card>
          <CardTitle>{totals.documents}</CardTitle>
          <CardDescription>Documents</CardDescription>
        </Card>
        <Card>
          <CardTitle>{totals.chunks}</CardTitle>
          <CardDescription>Chunks</CardDescription>
        </Card>
      </div>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <Card>
        <CardHeader>
          <CardTitle>Daily Breakdown</CardTitle>
          <CardDescription>Most recent usage rows returned by the backend.</CardDescription>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="py-2">Date</th>
                <th>API</th>
                <th>Retrieval</th>
                <th>Docs</th>
                <th>Chunks</th>
                <th>Storage</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.date} className="border-t border-slate-100">
                  <td className="py-2">{item.date}</td>
                  <td>{item.api_calls}</td>
                  <td>{item.retrieval_calls}</td>
                  <td>{item.documents_uploaded}</td>
                  <td>{item.chunks_created}</td>
                  <td>{item.storage_bytes} bytes</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
