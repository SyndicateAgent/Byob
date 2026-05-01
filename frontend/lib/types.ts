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
