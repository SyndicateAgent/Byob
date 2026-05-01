export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  chunk_count: number;
  qdrant_collection: string;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  kb_id: string;
  name: string;
  status: string;
  source_type: string;
  file_type: string | null;
  file_size: number | null;
  minio_path: string | null;
  file_hash: string | null;
  source_url: string | null;
  chunk_count: number;
  error_message: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DocumentBatchUploadItem {
  filename: string;
  status: "created" | "skipped";
  reason: "duplicate_name" | "duplicate_file_hash" | "empty_file" | null;
  detail: string | null;
  document: DocumentItem | null;
}

export interface DocumentBatchUploadResponse {
  request_id: string;
  created_count: number;
  skipped_count: number;
  items: DocumentBatchUploadItem[];
}

export interface ChunkItem {
  id: string;
  document_id: string;
  kb_id: string;
  chunk_index: number;
  content: string;
  content_hash: string | null;
  chunk_type: string;
  parent_chunk_id: string | null;
  page_num: number | null;
  bbox: Record<string, unknown> | null;
  qdrant_point_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface DocumentContent {
  request_id: string;
  document_id: string;
  content: string;
  content_type: string;
  source: string;
}

export interface RetrievalResult {
  chunk_id: string;
  content: string;
  score: number;
  rerank_score: number | null;
  kb_id: string;
  chunk_type: string;
  document: {
    id: string;
    name: string;
    metadata: Record<string, unknown>;
  };
}

export interface AgentSource {
  source_id: string;
  chunk_id: string;
  kb_id: string;
  document: {
    id: string;
    name: string;
    metadata: Record<string, unknown>;
  };
  content: string;
  score: number;
  rerank_score: number | null;
  chunk_type: string;
  page_num: number | null;
  metadata: Record<string, unknown>;
}

export interface AgentAskResponse {
  request_id: string;
  answer: string;
  answer_format: "markdown";
  model: string | null;
  mcp_tool: string;
  sources: AgentSource[];
  stats: {
    total_latency_ms: number;
    retrieval_latency_ms: number;
    generation_latency_ms: number;
    mcp_session_id: string | null;
  };
  warnings: string[];
}

export interface UserItem {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  role: string;
}
