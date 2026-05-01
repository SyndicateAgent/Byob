"use client";

import { FormEvent, useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Label, Select } from "@/components/ui/select";
import { apiRequest } from "@/lib/api";
import type { KnowledgeBase, RetrievalResult } from "@/lib/types";

interface SearchResponse {
  request_id: string;
  results: RetrievalResult[];
  stats: {
    total_latency_ms: number;
    cache_hit: boolean;
  };
}

export default function RetrievalPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState("");
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases")
      .then((result) => {
        setKbs(result.data);
        if (result.data.length > 0) setKbId(result.data[0].id);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const result = await apiRequest<SearchResponse>("/api/v1/retrieval/search/advanced", {
        method: "POST",
        auth: "none",
        body: JSON.stringify({
          query,
          kb_ids: [kbId],
          top_k: 5,
          enhancements: {
            query_rewrite: true,
            hyde: false,
            decompose: false,
          },
        }),
      });
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Retrieval Console</h1>
        <p className="text-sm text-slate-500">Test direct hybrid dense+sparse search for local AI Agents.</p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Search</CardTitle>
          <CardDescription>Retrieval endpoints are direct local APIs for your AI Agent runtime.</CardDescription>
        </CardHeader>
        <form className="space-y-3" onSubmit={runSearch}>
          <div className="space-y-1">
            <Label htmlFor="retrieval-kb">Knowledge base</Label>
            <Select id="retrieval-kb" value={kbId} onChange={(event) => setKbId(event.target.value)}>
              {kbs.length === 0 && <option value="">No knowledge bases</option>}
              {kbs.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="retrieval-query">Query</Label>
            <Textarea
              id="retrieval-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask a question"
              required
            />
          </div>
          <Button type="submit" disabled={!kbId} className="gap-2">
            <Search className="h-4 w-4" /> Run search
          </Button>
        </form>
      </Card>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {response && (
        <Card>
          <CardHeader>
            <CardTitle>Results</CardTitle>
            <CardDescription>
              {response.results.length} results in {response.stats.total_latency_ms}ms
              {response.stats.cache_hit && <Badge className="ml-2">cache hit</Badge>}
            </CardDescription>
          </CardHeader>
          <div className="space-y-4">
            {response.results.map((result) => (
              <div key={result.chunk_id} className="rounded-lg border border-slate-200 p-4">
                <div className="mb-2 flex justify-between gap-4 text-sm text-slate-500">
                  <span>{result.document.name}</span>
                  <span>score {result.score.toFixed(4)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-6">{result.content}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
