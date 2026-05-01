# BYOB 自部署向量数据库管理系统

BYOB 的目标是让用户快速搭建一个供 AI Agent 使用的自部署向量数据库管理系统。它负责知识库、文档、切块、向量索引和检索 API，不实现 Agent 编排、不保存对话状态、不管理 Prompt 模板，也不绑定特定 LLM。

本项目不是多租户 SaaS，不提供租户管理、API Key 管理或用量统计。部署者应把系统放在自己的可信网络、反向代理或现有身份体系之后使用。

---

## 产品定位

核心能力：

1. 知识库管理：创建、更新、删除多个知识库，每个知识库对应一个独立 Qdrant collection。
2. 文档管理：上传文件、直接写入文本、从 URL 抓取内容，并异步解析和切块。
3. 向量索引：使用 BGE-M3 生成 dense embedding，同时构建 sparse keyword vector。
4. 检索 API：为 AI Agent 提供混合检索、高级检索、批量检索、独立 embedding、独立 rerank、chunk 获取和反馈能力。
5. 管理控制台：用于本地管理员管理知识库、文档、用户账号和检索测试。
6. 自部署基础设施：PostgreSQL、Redis、Qdrant、MinIO、Infinity embedding/rerank、Celery worker。

明确不做：

- 不做租户、套餐、配额、计费或用量统计。
- 不做 API Key 生命周期管理；检索 API 作为自部署本地 API 暴露。
- 不做 Agent 编排、会话管理或 Prompt 管理。
- 不做生成式回答，系统只负责检索和返回原文片段。

---

## 技术栈

| 层级 | 技术选型 | 用途 |
| --- | --- | --- |
| 后端框架 | FastAPI + Pydantic v2 | API 服务与 OpenAPI |
| ORM / 迁移 | SQLAlchemy 2.0 async + Alembic | PostgreSQL 元数据 |
| 关系数据库 | PostgreSQL 16 | 用户、知识库、文档、chunk、检索日志 |
| 向量数据库 | Qdrant | Dense + sparse 检索 |
| 对象存储 | MinIO | 上传文件原文 |
| 缓存 / 队列 | Redis 7 | 检索缓存、Celery broker |
| 异步任务 | Celery | 文档解析、切块、向量写入 |
| Embedding | BGE-M3 via Infinity | 文本向量化 |
| Rerank | BGE-Reranker via Infinity | 检索结果精排 |
| 前端 | Next.js + TypeScript + Tailwind | 管理控制台 |

---

## 核心架构原则

### 数据职责分离

- PostgreSQL 是业务元数据和 chunk 原文的单一事实来源。
- Qdrant 只保存向量和最小检索 payload，不保存原文 content。
- MinIO 保存上传文件原始对象。
- Redis 只保存缓存、队列和临时数据。

### 单实例工作区

- 系统按一个自部署实例运行，不存在租户隔离层。
- 管理控制台使用 JWT 登录，仅用于本地用户管理和后台操作。
- 检索 API 不要求项目内 API Key，便于 LangGraph、LlamaIndex、Dify、自研 Agent 等在同一可信环境中直接调用。
- 生产部署时应通过反向代理、内网访问控制、VPN、网关或外部鉴权体系保护服务边界。

### Qdrant collection 策略

- 每个知识库一个 collection，命名规则为 `kb_{uuid}`，UUID 中的连字符替换为下划线。
- 不使用一个大 collection 承载多个知识库。
- Qdrant payload 只包含：`chunk_id`、`doc_id`、`chunk_type`、`tags`、`created_at`。

### 异步处理

- API 层只创建文档记录和入队任务。
- Celery worker 负责解析、切块、embedding、写入 chunks 表和 Qdrant。
- 文档处理失败要写入 `documents.error_message`，便于控制台展示。

---

## API 规划

认证与用户：

```text
POST   /api/v1/auth/login        # 管理控制台登录
GET    /api/v1/users             # 管理本地控制台用户
POST   /api/v1/users
PATCH  /api/v1/users/{user_id}
DELETE /api/v1/users/{user_id}
```

知识库：

```text
POST   /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases
GET    /api/v1/knowledge-bases/{kb_id}
PATCH  /api/v1/knowledge-bases/{kb_id}
DELETE /api/v1/knowledge-bases/{kb_id}
GET    /api/v1/knowledge-bases/{kb_id}/stats
```

文档与 chunk：

```text
POST   /api/v1/knowledge-bases/{kb_id}/documents
POST   /api/v1/knowledge-bases/{kb_id}/documents/text
POST   /api/v1/knowledge-bases/{kb_id}/documents/url
GET    /api/v1/knowledge-bases/{kb_id}/documents
GET    /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/chunks
DELETE /api/v1/documents/{document_id}
POST   /api/v1/documents/{document_id}/reprocess
```

检索：

```text
POST   /api/v1/retrieval/search
POST   /api/v1/retrieval/search/advanced
POST   /api/v1/retrieval/multi-search
POST   /api/v1/retrieval/rerank
POST   /api/v1/retrieval/embed
POST   /api/v1/retrieval/{request_id}/feedback
```

运维：

```text
GET    /healthz
GET    /metrics
```

---

## 核心数据模型

```text
users
  id, email, password_hash, role, created_at

knowledge_bases
  id, name, description, embedding_model, embedding_dim,
  chunk_size, chunk_overlap, retrieval_config, qdrant_collection,
  status, document_count, chunk_count, created_at, updated_at

documents
  id, kb_id, name, file_type, file_size, minio_path, file_hash,
  source_type, source_url, status, error_message, metadata,
  chunk_count, created_at, updated_at

chunks
  id, document_id, kb_id, chunk_index, content, content_hash,
  chunk_type, parent_chunk_id, page_num, bbox, qdrant_point_id,
  metadata, created_at

retrieval_logs
  id, request_id, kb_ids, query, rewritten_query, sub_queries,
  retrieved_chunk_ids, rerank_scores, total_latency_ms,
  stage_latencies, feedback, feedback_detail, created_at
```

Removed from the target schema:

```text
tenants
api_keys
usage_daily
```

---

## 检索接口示例

```json
{
  "kb_ids": ["knowledge-base-uuid"],
  "query": "用户问题",
  "top_k": 5,
  "filters": {
    "chunk_type": "text",
    "tags": ["产品手册"]
  },
  "options": {
    "enable_rerank": true,
    "include_parent_context": false,
    "include_metadata": true,
    "score_threshold": 0.5
  }
}
```

响应：

```json
{
  "request_id": "req_xxx",
  "results": [
    {
      "chunk_id": "uuid",
      "content": "...",
      "score": 0.87,
      "rerank_score": 0.92,
      "document": {
        "id": "uuid",
        "name": "manual.pdf",
        "metadata": {}
      },
      "kb_id": "uuid",
      "chunk_type": "text",
      "page_num": 12,
      "bbox": null,
      "metadata": {},
      "parent_chunk": null
    }
  ],
  "stats": {
    "total_latency_ms": 234,
    "stages": {
      "embedding_ms": 12,
      "vector_search_ms": 45,
      "sparse_search_ms": 34,
      "rerank_ms": 120,
      "fetch_content_ms": 23
    },
    "total_candidates": 100,
    "after_fusion": 30,
    "after_rerank": 5,
    "cache_hit": false
  }
}
```

---

## 本地开发

```powershell
Copy-Item .env.example .env
docker compose up -d
uv sync --extra dev
uv run alembic upgrade head
uv run python -m api.scripts.seed_admin
uv run uvicorn api.app.main:app --reload
```

文档处理 worker：

```powershell
uv run celery -A workers.celery_app.celery_app worker -Q ingestion --loglevel=INFO
```

前端控制台：

```powershell
cd frontend
npm install
npm run dev
```

质量检查：

```powershell
uv run ruff check .
uv run pytest
cd frontend
npm run lint
npx tsc --noEmit
```

---

## 开发守则

- 新功能必须服务于“自部署向量数据库 + AI Agent 检索”这个目标。
- 不重新引入租户、API Key 管理、套餐、计费或用量统计。
- Qdrant payload 不允许保存 chunk 原文。
- 控制台用于管理本地实例，不做 SaaS 管理后台。
- API 行为不依赖请求体中的组织、租户或账号归属字段。
