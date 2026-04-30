"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { apiRequest, setApiKey } from "@/lib/api";
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
  const [apiKeyInput, setApiKeyInput] = useState("");
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
    if (apiKeyInput) setApiKey(apiKeyInput);
    try {
      const result = await apiRequest<SearchResponse>("/api/v1/retrieval/search/advanced", {
        method: "POST",
        auth: "api-key",
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
      <div>
        <h1 className="text-2xl font-semibold">Retrieval Console</h1>
        <p className="text-slate-500">Test hybrid dense+sparse search with optional query rewrite.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Search</CardTitle>
          <CardDescription>Use an API key created in the API Keys page.</CardDescription>
        </CardHeader>
        <form className="space-y-3" onSubmit={runSearch}>
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
          <Input
            value={apiKeyInput}
            onChange={(event) => setApiKeyInput(event.target.value)}
            placeholder="Optional API key override"
          />
          <Textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask a question" required />
          <Button type="submit" disabled={!kbId}>
            Run Search
          </Button>
        </form>
      </Card>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {response && (
        <Card>
          <CardHeader>
            <CardTitle>Results</CardTitle>
            <CardDescription>
              {response.results.length} results in {response.stats.total_latency_ms}ms, cache hit:{" "}
              {response.stats.cache_hit ? "yes" : "no"}
            </CardDescription>
          </CardHeader>
          <div className="space-y-4">
            {response.results.map((result) => (
              <div key={result.chunk_id} className="rounded-lg border border-slate-200 p-4">
                <div className="mb-2 flex justify-between text-sm text-slate-500">
                  <span>{result.document.name}</span>
                  <span>score {result.score.toFixed(4)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm">{result.content}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
