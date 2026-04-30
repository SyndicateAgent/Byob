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
  chunk_count: number;
  error_message: string | null;
  created_at: string;
}

export interface ApiKeyItem {
  id: string;
  name: string;
  key_prefix: string | null;
  rate_limit: number;
  revoked: boolean;
  created_at: string;
}

export interface UsageDaily {
  date: string;
  api_calls: number;
  retrieval_calls: number;
  documents_uploaded: number;
  chunks_created: number;
  embedding_tokens: number;
  storage_bytes: number;
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
