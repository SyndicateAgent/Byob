"use client";

import { FormEvent, useEffect, useState } from "react";
import { Database, Gauge, Search, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { PipelineLoader } from "@/components/ui/loading";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar, StepRail, type StepItem } from "@/components/ui/progress";
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

function retrievalSteps(progress: number, complete: boolean): StepItem[] {
  return [
    { label: "Rewrite", state: complete || progress >= 22 ? "done" : "active" },
    { label: "Embed", state: complete || progress >= 46 ? "done" : progress >= 22 ? "active" : "idle" },
    { label: "Recall", state: complete || progress >= 72 ? "done" : progress >= 46 ? "active" : "idle" },
    { label: "Rerank", state: complete ? "done" : progress >= 72 ? "active" : "idle" },
  ];
}

export default function RetrievalPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState("");
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchProgress, setSearchProgress] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases")
      .then((result) => {
        setKbs(result.data);
        if (result.data.length > 0) setKbId(result.data[0].id);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  useEffect(() => {
    if (!isSearching) return;
    const startedAt = Date.now();
    setElapsedMs(0);
    const timer = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
      setSearchProgress((current) => Math.min(94, current + (current < 50 ? 9 : 5)));
    }, 260);
    return () => window.clearInterval(timer);
  }, [isSearching]);

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    setIsSearching(true);
    setSearchProgress(8);
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
      setSearchProgress(100);
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      window.setTimeout(() => {
        setIsSearching(false);
        setSearchProgress(0);
      }, 500);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Retrieval Console"
        description="Test direct hybrid dense+sparse recall with visible query, embedding, vector search, and rerank stages."
      />
      <Card className="animate-fade-up overflow-hidden p-0">
        <div className="border-b border-slate-200 bg-white p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <CardHeader className="mb-0">
              <CardTitle>Search</CardTitle>
              <CardDescription>Retrieval endpoints are direct local APIs for your AI Agent runtime.</CardDescription>
            </CardHeader>
            <div className="grid gap-3 text-xs text-slate-500 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="mb-1 flex items-center gap-1 text-slate-700"><Sparkles className="h-3.5 w-3.5" /> Enhanced</div>
                <p>query rewrite enabled</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="mb-1 flex items-center gap-1 text-slate-700"><Database className="h-3.5 w-3.5" /> Hybrid</div>
                <p>dense + sparse recall</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="mb-1 flex items-center gap-1 text-slate-700"><Gauge className="h-3.5 w-3.5" /> Top K</div>
                <p>5 results</p>
              </div>
            </div>
          </div>
        </div>
        <div className="p-6">
          <form className="space-y-4" onSubmit={runSearch}>
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
            <Button type="submit" disabled={!kbId || isSearching} className="gap-2">
              <Search className="h-4 w-4" /> {isSearching ? "Searching..." : "Run search"}
            </Button>
          </form>
        </div>
      </Card>

      {isSearching && (
        <Card className="animate-soft-pop border-cyan-100 bg-white">
          <PipelineLoader
            label="Recall in progress"
            detail={`Elapsed ${elapsedMs.toLocaleString()}ms`}
          />
          <div className="mt-4 space-y-4">
            <ProgressBar
              value={searchProgress}
              label="Retrieval pipeline"
              detail="Query enhancement, embedding, Qdrant recall, rerank, hydration"
              tone="cyan"
              indeterminate
            />
            <StepRail steps={retrievalSteps(searchProgress, false)} />
          </div>
        </Card>
      )}

      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {response && (
        <Card className="animate-fade-up">
          <CardHeader>
            <CardTitle>Results</CardTitle>
            <CardDescription>
              {response.results.length} results in {response.stats.total_latency_ms}ms
              {response.stats.cache_hit && <Badge className="ml-2">cache hit</Badge>}
            </CardDescription>
          </CardHeader>
          <div className="space-y-4">
            {response.results.map((result, index) => (
              <div
                key={result.chunk_id}
                className="animate-fade-up rounded-lg border border-slate-200 bg-white p-4 transition-all duration-300 hover:border-blue-200 hover:shadow-sm"
                style={{ animationDelay: `${index * 55}ms` }}
              >
                <div className="mb-2 flex justify-between gap-4 text-sm text-slate-500">
                  <span>{result.document.name}</span>
                  <div className="flex items-center gap-2">
                    {result.rerank_score !== null && <Badge variant="info">rerank {result.rerank_score.toFixed(4)}</Badge>}
                    <span>score {result.score.toFixed(4)}</span>
                  </div>
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
