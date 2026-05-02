"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Bot, BookOpen, FileText, Send, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Label, Select } from "@/components/ui/select";
import { RenderedContent } from "@/components/document-content-viewer";
import { apiRequest } from "@/lib/api";
import type { AgentAskResponse, KnowledgeBase } from "@/lib/types";

const ALL_KNOWLEDGE_BASES = "__all__";

function reviewStatusVariant(status: string) {
  if (status === "published") return "success" as const;
  if (status === "reviewed") return "info" as const;
  if (status === "deprecated") return "muted" as const;
  return "warning" as const;
}

export default function AgentPage() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState(ALL_KNOWLEDGE_BASES);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState("5");
  const [useLlm, setUseLlm] = useState(true);
  const [response, setResponse] = useState<AgentAskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);

  useEffect(() => {
    apiRequest<{ data: KnowledgeBase[] }>("/api/v1/knowledge-bases")
      .then((result) => setKbs(result.data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  const selectedKbName = useMemo(() => {
    if (kbId === ALL_KNOWLEDGE_BASES) return "All active knowledge bases";
    return kbs.find((kb) => kb.id === kbId)?.name ?? "Selected knowledge base";
  }, [kbId, kbs]);

  async function askAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    setIsAsking(true);
    try {
      const result = await apiRequest<AgentAskResponse>("/api/v1/agent/ask", {
        method: "POST",
        body: JSON.stringify({
          question,
          kb_ids: kbId === ALL_KNOWLEDGE_BASES ? null : [kbId],
          top_k: Number(topK),
          use_llm: useLlm,
          options: {
            query_rewrite: true,
            hyde: false,
            decompose: false,
            max_sub_queries: 3,
            enable_rerank: true,
            include_parent_context: true,
          },
        }),
      });
      setResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent request failed");
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="QA Agent"
        description="Ask questions through a simple MCP-backed RAG Agent and inspect rendered answers with source chunks."
      />

      <Card className="animate-fade-up overflow-hidden p-0">
        <div className="border-b border-slate-200 bg-white p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <CardHeader className="mb-0">
              <CardTitle>Ask</CardTitle>
              <CardDescription>{selectedKbName}</CardDescription>
            </CardHeader>
            <div className="grid gap-3 text-xs text-slate-500 sm:grid-cols-3">
              <StatusTile icon={Bot} label="Agent" value="MCP client" />
              <StatusTile icon={BookOpen} label="Tool" value="advanced search" />
              <StatusTile icon={Sparkles} label="Render" value="markdown, math, tables" />
            </div>
          </div>
        </div>

        <form className="space-y-4 p-6" onSubmit={askAgent}>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_10rem]">
            <div className="space-y-1">
              <Label htmlFor="agent-kb">Knowledge base</Label>
              <Select id="agent-kb" value={kbId} onChange={(event) => setKbId(event.target.value)}>
                <option value={ALL_KNOWLEDGE_BASES}>All active knowledge bases</option>
                {kbs.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="agent-top-k">Top K</Label>
              <Select id="agent-top-k" value={topK} onChange={(event) => setTopK(event.target.value)}>
                {[3, 5, 8, 10, 15, 20].map((value) => (
                  <option key={value} value={String(value)}>
                    {value}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="agent-question">Question</Label>
            <Textarea
              id="agent-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a question about your imported documents"
              required
              className="min-h-32"
            />
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(event) => setUseLlm(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Use configured LLM when available
            </label>
            <Button type="submit" disabled={!question.trim() || isAsking} className="gap-2">
              <Send className="h-4 w-4" /> {isAsking ? "Asking..." : "Ask Agent"}
            </Button>
          </div>
        </form>
      </Card>

      {isAsking && (
        <Card className="border-blue-100 bg-white p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-900">Agent is calling BYOB MCP</p>
              <p className="text-xs text-slate-500">Retrieval, context assembly, and answer generation are running.</p>
            </div>
          </div>
        </Card>
      )}

      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {response && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <Card className="animate-fade-up min-w-0 overflow-hidden p-0">
            <div className="flex flex-col gap-3 border-b border-slate-200 bg-white p-6 sm:flex-row sm:items-start sm:justify-between">
              <CardHeader className="mb-0">
                <CardTitle>Answer</CardTitle>
                <CardDescription>
                  {response.stats.total_latency_ms}ms total · {response.stats.retrieval_latency_ms}ms retrieval · {response.stats.generation_latency_ms}ms generation
                </CardDescription>
              </CardHeader>
              <div className="flex flex-wrap gap-2 sm:justify-end">
                <Badge variant="info">{response.mcp_tool}</Badge>
                <Badge variant={response.model ? "success" : "muted"}>{response.model ?? "extractive"}</Badge>
              </div>
            </div>
            <div className="max-h-[calc(100vh-260px)] min-w-0 overflow-auto p-6">
              {response.warnings.length > 0 && (
                <div className="mb-4 space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  {response.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              )}
              <RenderedContent content={response.answer} kind="markdown" />
            </div>
          </Card>

          <Card className="animate-fade-up min-w-0 overflow-hidden p-0">
            <div className="border-b border-slate-200 bg-white p-5">
              <CardHeader className="mb-0">
                <CardTitle>Sources</CardTitle>
                <CardDescription>{response.sources.length} MCP chunks</CardDescription>
              </CardHeader>
            </div>
            <div className="max-h-[calc(100vh-260px)] space-y-3 overflow-auto p-4">
              {response.sources.map((source) => (
                <div key={source.chunk_id} className="min-w-0 rounded-lg border border-slate-200 bg-white p-3">
                  <div className="mb-2 flex min-w-0 items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant="muted">{source.source_id}</Badge>
                        <Badge variant={reviewStatusVariant(source.document.review_status)}>{source.document.review_status}</Badge>
                        <Badge variant="muted">L{source.document.authority_level}</Badge>
                        <span className="truncate text-sm font-medium text-slate-900" title={source.document.name}>
                          {source.document.name}
                        </span>
                      </div>
                      <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                        <FileText className="h-3.5 w-3.5" />
                        {source.page_num !== null ? `page ${source.page_num}` : source.chunk_type}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-slate-500">{source.score.toFixed(4)}</span>
                  </div>
                  <RenderedContent className="document-rendered-compact" content={source.content} kind="markdown" />
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function StatusTile({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-slate-700">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <p>{value}</p>
    </div>
  );
}
