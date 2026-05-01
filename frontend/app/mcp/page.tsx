import { readFile } from "node:fs/promises";
import { join } from "node:path";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

async function loadMcpGuide() {
  const markdownPath = join(process.cwd(), "..", "docs", "mcp.md");
  const content = await readFile(markdownPath, "utf-8");
  return content.replace(/^# BYOB MCP 使用说明\s*/, "").trim();
}

export default async function McpGuidePage() {
  const markdown = await loadMcpGuide();

  return (
    <div className="space-y-6">
      <PageHeader
        title="MCP Guide"
        description="Configure AI Agents to retrieve local BYOB knowledge base context through Model Context Protocol tools."
      />
      <Card className="animate-fade-up overflow-hidden p-0">
        <div className="border-b border-slate-100 px-6 py-4">
          <p className="text-sm font-medium text-slate-700">Rendered from docs/mcp.md</p>
        </div>
        <div className="max-h-[calc(100vh-220px)] overflow-auto p-6">
          <div className="document-rendered">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </div>
        </div>
      </Card>
    </div>
  );
}