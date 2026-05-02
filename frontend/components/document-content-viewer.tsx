"use client";

import * as React from "react";
import DOMPurify from "dompurify";
import { Eye, FileCode2, ListTree } from "lucide-react";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Badge } from "@/components/ui/badge";
import { apiUrl, getToken } from "@/lib/api";
import { mergeChunkContent } from "@/lib/chunk-overlap";
import { cn, formatNumber } from "@/lib/utils";
import type { ChunkItem } from "@/lib/types";

type PreviewMode = "rendered" | "text" | "chunks";
type ContentKind = "markdown" | "html" | "text";

interface DocumentContentViewerProps {
  content: string;
  chunks: ChunkItem[];
  fileType: string | null;
}

function detectContentKind(fileType: string | null, content: string): ContentKind {
  const normalizedType = (fileType ?? "").toLowerCase().replace(/^\./, "");
  if (["md", "markdown"].includes(normalizedType)) return "markdown";
  if (["html", "htm"].includes(normalizedType)) return "html";

  const sample = content.slice(0, 6000);
  if (
    /^#{1,6}\s+\S/m.test(sample) ||
    /```/.test(sample) ||
    /^\s*[-*+]\s+\S/m.test(sample) ||
    /\|.+\|\s*\r?\n\|[-:|\s]+\|/m.test(sample) ||
    /!\[[^\]]*]\([^)]+\)/m.test(sample) ||
    /(^|[^\\])\$\$[\s\S]+?\$\$/m.test(sample) ||
    /\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\]/m.test(sample) ||
    /(^|[^\\])\$[^$\n]*(\\[a-zA-Z]+|[=^_])[^$\n]*\$/m.test(sample)
  ) {
    return "markdown";
  }
  if (/^\s*<!doctype\s+html/i.test(sample) || /<\s*(html|body|main|article|section|h[1-6]|p|table|ul|ol|pre|blockquote)\b/i.test(sample)) {
    return "html";
  }
  return "text";
}

function contentKindLabel(kind: ContentKind) {
  if (kind === "markdown") return "Markdown";
  if (kind === "html") return "HTML";
  return "Text";
}

function MarkdownImage({ alt, src }: React.ComponentPropsWithoutRef<"img">) {
  const imageAlt = typeof alt === "string" ? alt : "";
  const imageSource = typeof src === "string" ? src : "";
  const controlledAssetUrl = React.useMemo(() => controlledAssetApiUrl(imageSource), [imageSource]);
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null);
  const [loadFailed, setLoadFailed] = React.useState(false);

  React.useEffect(() => {
    if (!controlledAssetUrl) {
      setObjectUrl(null);
      setLoadFailed(false);
      return undefined;
    }

    const controller = new AbortController();
    let activeObjectUrl: string | null = null;
    setObjectUrl(null);
    setLoadFailed(false);

    const headers = new Headers();
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    fetch(controlledAssetUrl, { headers, signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Image request failed: ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        activeObjectUrl = URL.createObjectURL(blob);
        setObjectUrl(activeObjectUrl);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoadFailed(true);
      });

    return () => {
      controller.abort();
      if (activeObjectUrl) URL.revokeObjectURL(activeObjectUrl);
    };
  }, [controlledAssetUrl]);

  const resolvedSrc = controlledAssetUrl ? objectUrl : imageSource;

  return (
    <span className="document-image-frame">
      {resolvedSrc
        ? React.createElement("img", {
            alt: imageAlt,
            decoding: "async",
            loading: "lazy",
            referrerPolicy: "no-referrer",
            src: resolvedSrc,
          })
        : (
          <span className="document-image-placeholder">
            {loadFailed ? "Image failed to load" : "Loading image"}
          </span>
        )}
      {imageAlt ? <span className="document-image-caption">{imageAlt}</span> : null}
    </span>
  );
}

function controlledAssetApiUrl(src: string): string | null {
  if (!src) return null;
  if (src.startsWith("/api/v1/documents/") && src.includes("/assets/")) return apiUrl(src);
  try {
    const parsed = new URL(src);
    if (parsed.pathname.startsWith("/api/v1/documents/") && parsed.pathname.includes("/assets/")) {
      return src;
    }
  } catch {
    return null;
  }
  return null;
}

function appendAccessToken(url: string): string {
  const token = getToken();
  if (!token) return url;
  const parsed = new URL(url);
  parsed.searchParams.set("access_token", token);
  return parsed.toString();
}

function rewriteHtmlControlledAssets(html: string): string {
  if (typeof document === "undefined") return html;

  const template = document.createElement("template");
  template.innerHTML = html;
  for (const link of template.content.querySelectorAll("a")) {
    const href = link.getAttribute("href") ?? "";
    const controlledUrl = controlledAssetApiUrl(href);
    if (!controlledUrl) continue;
    link.setAttribute("href", appendAccessToken(controlledUrl));
  }
  for (const image of template.content.querySelectorAll("img")) {
    const src = image.getAttribute("src") ?? "";
    const controlledUrl = controlledAssetApiUrl(src);
    if (!controlledUrl) continue;
    image.setAttribute("src", appendAccessToken(controlledUrl));
    image.setAttribute("loading", "lazy");
    image.setAttribute("decoding", "async");
    image.setAttribute("referrerpolicy", "no-referrer");
  }
  return template.innerHTML;
}

export function RenderedContent({
  className,
  content,
  kind,
}: {
  className?: string;
  content: string;
  kind: ContentKind;
}) {
  const sanitizedHtml = React.useMemo(() => {
    if (kind !== "html") return "";
    const sanitized = DOMPurify.sanitize(content, { USE_PROFILES: { html: true, mathMl: true } });
    return rewriteHtmlControlledAssets(sanitized);
  }, [content, kind]);
  const sanitizedMarkdown = React.useMemo(() => {
    if (kind !== "markdown") return content;
    return DOMPurify.sanitize(content, { USE_PROFILES: { html: true, mathMl: true } });
  }, [content, kind]);

  if (kind === "html") {
    return (
      <div
        className={cn("document-rendered document-rendered-html", className)}
        dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
      />
    );
  }

  if (kind === "markdown") {
    return (
      <div className={cn("document-rendered", className)}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeRaw, rehypeKatex]}
          components={{
            a: ({ href, children }) => {
              const isInternalAnchor = href?.startsWith("#");
              const controlledAssetUrl = href ? controlledAssetApiUrl(href) : null;
              const resolvedHref = controlledAssetUrl ? appendAccessToken(controlledAssetUrl) : href;
              return (
                <a href={resolvedHref} rel={isInternalAnchor ? undefined : "noreferrer"} target={isInternalAnchor ? undefined : "_blank"}>
                  {children}
                </a>
              );
            },
            img: MarkdownImage,
          }}
        >
          {sanitizedMarkdown}
        </ReactMarkdown>
      </div>
    );
  }

  return <pre className="document-plain-text">{content}</pre>;
}

function ChunkContentPreview({
  content,
  fileType,
  expanded = false,
}: {
  content: string;
  fileType: string | null;
  expanded?: boolean;
}) {
  const trimmedContent = content.trim();
  const kind = React.useMemo(() => detectContentKind(fileType, trimmedContent), [fileType, trimmedContent]);

  if (!trimmedContent) return null;
  if (kind === "text") {
    return (
      <p
        className={cn(
          "whitespace-pre-wrap break-words text-slate-700",
          expanded ? "text-sm leading-6" : "line-clamp-6 text-xs leading-5",
        )}
      >
        {trimmedContent}
      </p>
    );
  }

  return (
    <div className={cn("overflow-auto rounded-md border border-slate-100 bg-white p-2", expanded ? "max-h-none" : "max-h-72")}>
      <RenderedContent className="document-rendered-compact" content={trimmedContent} kind={kind} />
    </div>
  );
}

function chunkSnippet(content: string) {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return "No text content";
  return normalized.length > 150 ? `${normalized.slice(0, 150)}...` : normalized;
}

export function DocumentContentViewer({ content, chunks, fileType }: DocumentContentViewerProps) {
  const mergedChunkContent = React.useMemo(() => mergeChunkContent(chunks), [chunks]);
  const displayContent = content || mergedChunkContent.content;
  const contentKind = React.useMemo(() => detectContentKind(fileType, displayContent), [displayContent, fileType]);
  const [mode, setMode] = React.useState<PreviewMode>(contentKind === "text" ? "text" : "rendered");
  const [selectedChunkId, setSelectedChunkId] = React.useState<string | null>(null);

  React.useEffect(() => {
    setMode(contentKind === "text" ? "text" : "rendered");
  }, [contentKind]);

  React.useEffect(() => {
    setSelectedChunkId((current) => {
      if (current && mergedChunkContent.chunks.some((item) => item.chunk.id === current)) return current;
      return mergedChunkContent.chunks[0]?.chunk.id ?? null;
    });
  }, [mergedChunkContent.chunks]);

  const selectedChunk = React.useMemo(
    () => mergedChunkContent.chunks.find((item) => item.chunk.id === selectedChunkId) ?? mergedChunkContent.chunks[0] ?? null,
    [mergedChunkContent.chunks, selectedChunkId],
  );

  const modes: Array<{ id: PreviewMode; label: string; icon: React.ElementType }> = [
    { id: "rendered", label: contentKindLabel(contentKind), icon: Eye },
    { id: "text", label: "Text", icon: FileCode2 },
    { id: "chunks", label: "Chunks", icon: ListTree },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="shrink-0 flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="inline-flex w-full rounded-lg bg-slate-100 p-1 sm:w-auto">
          {modes.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setMode(item.id)}
                className={cn(
                  "inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium transition-all duration-200 sm:flex-none",
                  mode === item.id
                    ? "bg-white text-blue-700 shadow-sm"
                    : "text-slate-600 hover:bg-white/70 hover:text-slate-950",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2 px-1">
          <Badge variant="muted">{contentKindLabel(contentKind)}</Badge>
          <Badge variant="info">{formatNumber(chunks.length)} chunks</Badge>
          {mergedChunkContent.totalOverlapCharacters > 0 && (
            <Badge variant="warning">
              {formatNumber(mergedChunkContent.totalOverlapCharacters)} overlap chars folded
            </Badge>
          )}
        </div>
      </div>

      {mode === "rendered" && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="shrink-0 border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-700">
            Rendered content
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <RenderedContent content={displayContent} kind={contentKind} />
          </div>
        </div>
      )}

      {mode === "text" && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="shrink-0 border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-700">
            Plain text
          </div>
          <pre className="document-plain-text min-h-0 flex-1 overflow-auto p-4">{displayContent}</pre>
        </div>
      )}

      {mode === "chunks" && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="shrink-0 flex flex-col gap-2 border-b border-slate-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-slate-700">Chunk inspector</p>
              <p className="text-xs text-slate-500">Select a chunk to inspect the exact stored text and overlap handling.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="info">{formatNumber(mergedChunkContent.chunks.length)} chunks</Badge>
              {mergedChunkContent.overlappedChunkCount > 0 && (
                <Badge variant="warning">{formatNumber(mergedChunkContent.overlappedChunkCount)} folded</Badge>
              )}
            </div>
          </div>
          <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,14rem)_minmax(0,1fr)] overflow-hidden lg:grid-cols-[22rem_minmax(0,1fr)] lg:grid-rows-1">
            <aside className="min-h-0 overflow-y-auto border-b border-slate-100 bg-slate-50/70 p-3 lg:border-b-0 lg:border-r">
              <div className="space-y-2">
                {mergedChunkContent.chunks.map((item) => {
                  const active = selectedChunk?.chunk.id === item.chunk.id;
                  const displayText = item.uniqueContent || item.content;
                  return (
                    <button
                      key={item.chunk.id}
                      type="button"
                      onClick={() => setSelectedChunkId(item.chunk.id)}
                      className={cn(
                        "w-full rounded-lg border p-3 text-left transition-all duration-200",
                        active
                          ? "border-blue-200 bg-white shadow-sm ring-1 ring-blue-100"
                          : "border-slate-200 bg-white/70 hover:border-slate-300 hover:bg-white",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant={active ? "info" : "muted"}>#{item.chunk.chunk_index + 1}</Badge>
                          {item.chunk.page_num !== null && <Badge variant="muted">p{item.chunk.page_num}</Badge>}
                        </div>
                        <span className="text-xs text-slate-500">{formatNumber(displayText.length)} chars</span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600">
                        {chunkSnippet(displayText)}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <Badge variant="muted">{item.chunk.chunk_type}</Badge>
                        {item.overlapCharacters > 0 && (
                          <Badge variant="warning">{formatNumber(item.overlapCharacters)} overlap</Badge>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </aside>
            <section className="min-h-0 min-w-0 overflow-y-auto p-4">
              {selectedChunk ? (
                <div className="space-y-4">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-950">Chunk #{selectedChunk.chunk.chunk_index + 1}</p>
                        <p className="mt-1 text-xs text-slate-500">ID {selectedChunk.chunk.id}</p>
                      </div>
                      <div className="flex flex-wrap gap-2 sm:justify-end">
                        <Badge variant="muted">{selectedChunk.chunk.chunk_type}</Badge>
                        {selectedChunk.chunk.page_num !== null && <Badge variant="muted">page {selectedChunk.chunk.page_num}</Badge>}
                        <Badge variant="info">{formatNumber((selectedChunk.uniqueContent || selectedChunk.content).length)} chars</Badge>
                        {selectedChunk.overlapCharacters > 0 && (
                          <Badge variant="warning">{formatNumber(selectedChunk.overlapCharacters)} overlap folded</Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  {selectedChunk.overlapCharacters > 0 && (
                    <div className="rounded-lg border border-amber-100 bg-amber-50 p-3 text-sm text-amber-900">
                      <div className="mb-2 font-medium">Folded overlap</div>
                      <ChunkContentPreview content={selectedChunk.overlapContent} fileType={fileType} expanded />
                    </div>
                  )}

                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
                      <p className="text-sm font-medium text-slate-900">Stored chunk content</p>
                      {selectedChunk.chunk.content_hash && <Badge variant="muted">hash {selectedChunk.chunk.content_hash.slice(0, 10)}</Badge>}
                    </div>
                    <ChunkContentPreview content={selectedChunk.uniqueContent || selectedChunk.content} fileType={fileType} expanded />
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                  No chunks available.
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}