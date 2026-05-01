# BYOB Markdown Retrieval Sample

This Markdown document is designed to exercise rendering, chunking, overlap handling, math support, tables, code blocks, and retrieval.

## Executive Summary

BYOB is a self-hosted vector database management system for AI Agents. It helps users upload documents, parse source files, generate chunks, embed those chunks, and search them through Qdrant-backed hybrid retrieval.

中文段落：这个样例用于测试中文分词、段落边界、chunk overlap 以及前端预览。系统应该保留标题、列表、公式和表格，并且在召回时可以命中文档中的关键事实。

## Important Facts

- Product: BYOB Vector Database Console
- Goal: Manage self-hosted RAG knowledge bases for AI Agent retrieval
- Storage: PostgreSQL for metadata and chunks, MinIO for source and parsed assets, Qdrant for vectors
- Worker: Celery ingestion pipeline
- Parser: MinerU-first PDF parser with fallback support

## Formula

Inline formula: $score = \alpha \cdot dense + (1 - \alpha) \cdot sparse$.

Block formula:

$$
\operatorname{cosine}(q, d) = \frac{q \cdot d}{\lVert q \rVert \lVert d \rVert}
$$

## Table

| Stage | Expected progress | Notes |
| --- | ---: | --- |
| Queued | 10% | Document record was created |
| Parsing | 30% | Parser reads source content |
| Chunking | 56% | Parsed text becomes retrieval chunks |
| Embedding | 70% | Embedding endpoint is called |
| Indexing | 92% | Qdrant points are upserted |
| Completed | 100% | Document is ready for retrieval |

## Mermaid-like Code Block

```text
Upload -> Parse -> Chunk -> Embed -> Index -> Retrieve
```

## Inline Image Data URI

![Small inline sample image](data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNDAiIGhlaWdodD0iOTAiIHZpZXdCb3g9IjAgMCAyNDAgOTAiPjxyZWN0IHdpZHRoPSIyNDAiIGhlaWdodD0iOTAiIHJ4PSIxMiIgZmlsbD0iI2Y4ZmFmYyIgc3Ryb2tlPSIjMjU2M2ViIi8+PHRleHQgeD0iMjAiIHk9IjUwIiBmb250LXNpemU9IjE4IiBmb250LWZhbWlseT0iQXJpYWwiIGZpbGw9IiMwZjE3MmEiPkJZT0Igc2FtcGxlIGltYWdlPC90ZXh0Pjwvc3ZnPg==)

## Retrieval Questions To Try

- What storage systems does BYOB use?
- Which parser is preferred for PDF files?
- What progress value corresponds to embedding?
- BYOB 的目标是什么？
