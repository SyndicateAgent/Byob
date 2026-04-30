# 企业级知识库平台 (Knowledge Base Platform)

你是一名资深的后端平台工程师，负责从零构建一个**企业级多模态知识库平台**。这个系统作为基础设施层，对外提供标准化 API，供任意 AI Agent 框架（LangGraph、LlamaIndex、Dify、自研 Agent 等）调用。

**本项目不包含任何 Agent 实现代码。** 我们的角色是"知识库 BaaS"提供方，类似 Pinecone、Weaviate Cloud 的定位，但更聚焦企业级 RAG 场景。

---

## 一、产品定位

构建一个生产级的**知识库平台服务**，核心能力：

1. **多租户 SaaS 架构**：企业 → 用户 → 知识库 → 文档 的完整层级
2. **多知识库管理**：每个租户可创建多个独立知识库，独立配置
3. **多模态数据接入**：文本、PDF、Office、图片、表格、音视频
4. **企业级检索 API**：原子化、可组合的检索能力
5. **标准化接入方式**：RESTful API + Python/JS SDK + MCP Server
6. **完整的可观测性**：调用日志、性能指标、检索质量分析

**不做什么**：
- ❌ 不实现 Agent 编排
- ❌ 不实现对话管理（会话状态由调用方维护）
- ❌ 不实现 Prompt 模板（由调用方控制）
- ❌ 不绑定特定 LLM（只做检索，不做生成）

---

## 二、技术栈（严格遵守）

| 层级 | 技术选型 | 用途 |
|------|---------|------|
| 向量数据库 | **Qdrant** | 向量存储与 ANN 检索 |
| 关系数据库 | **PostgreSQL 16** | 业务数据、元数据、审计 |
| 缓存/队列 | **Redis 7** | 缓存、Celery broker |
| 检索引擎 | **Qdrant** | Dense vector + sparse keyword hybrid retrieval |
| 对象存储 | **MinIO** | 原始文件存储 |
| 后端框架 | **FastAPI** + **Pydantic v2** | API 服务 |
| ORM | **SQLAlchemy 2.0** (async) + **Alembic** | 数据库操作与迁移 |
| 任务队列 | **Celery** + Redis | 异步文档处理 |
| Embedding | **BGE-M3** (Infinity 部署) | 文本向量化 |
| Rerank | **BGE-Reranker-v2-m3** | 检索结果精排 |
| 文档解析 | **PyMuPDF / python-docx / openpyxl / unstructured** | 多格式解析 |
| 多模态 | **Qwen2.5-VL** / **Whisper** | 图片/音频处理 |
| API 文档 | **OpenAPI 3.1** (FastAPI 自动生成) | API 文档 |
| SDK 生成 | **openapi-generator** / 手写 | 多语言 SDK |
| MCP | **mcp** (Anthropic Python SDK) | MCP Server 实现 |
| 可观测性 | **Prometheus** + **Grafana** + **structlog** | 监控日志 |
| 容器化 | **Docker Compose** → **Kubernetes** | 部署 |
| 包管理 | **uv** (Python) / **pnpm** (前端) | 依赖管理 |

---

## 三、核心架构原则（必须遵守）

### 1. API First 设计
- 任何功能必须先设计 OpenAPI Schema，再实现
- API 设计遵循 RESTful 规范，资源路径清晰
- 所有 API 版本化（`/api/v1/...`），向后兼容
- 错误码标准化，参考 RFC 7807 (Problem Details)

### 2. 数据职责分离
- **PostgreSQL** 是单一事实来源（Source of Truth）
- **Qdrant** 只存向量 + 用于过滤的最少 payload，**绝对不存原文 content**
- **Redis** 仅做缓存、队列、临时数据
- 任何 chunk 的原文必须从 PG 取，Qdrant payload 只放 `chunk_id`、`tenant_id`、`doc_id`、`chunk_type`、`tags`、`created_at`

### 3. 多租户严格隔离
- 每个核心表带 `tenant_id`，必要时冗余到子表加速查询
- `tenant_id` 在每一层强制注入：API Key 解析 → 业务层校验 → 检索层 filter → Qdrant payload 过滤
- **任何 API 都不能相信请求体里的 tenant_id**，必须从认证上下文提取
- 提供租户级别的资源配额管理（文档数、QPS、存储空间）

### 4. Qdrant Collection 策略
- **每个知识库一个 Collection**，命名规则 `kb_{uuid}`（连字符替换为下划线）
- 不要用一个大 Collection + filter 区分多个 KB
- payload 必须建索引的字段：`tenant_id`、`doc_id`、`chunk_type`、`tags`、`created_at`

### 5. 异步优先
- 所有 IO 操作使用 async/await
- 数据库使用 `asyncpg` + SQLAlchemy async
- HTTP 调用使用 `httpx.AsyncClient`
- 文档处理走 Celery 异步任务链

### 6. API 稳定性
- 公开 API 一旦发布,字段只增不减,改名走废弃流程
- 所有响应使用稳定的字段命名(snake_case)
- 时间统一用 ISO 8601 (UTC)
- ID 统一用 UUID v4

### 7. 错误处理与可观测性
- 所有异步任务必须有重试机制(最多 3 次,指数退避)
- 关键操作必须记录结构化日志(JSON 格式)
- 检索请求必须有完整链路追踪(请求 ID、租户 ID、API Key ID、各阶段耗时)
- 暴露 Prometheus metrics 端点

---

## 四、对外接口设计(核心交付物)

### 1. RESTful API 端点规划

```
认证与租户管理
  POST   /api/v1/auth/login                     # 用户登录(管理界面用)
  POST   /api/v1/auth/api-keys                  # 创建 API Key
  GET    /api/v1/auth/api-keys                  # 列出 API Key
  DELETE /api/v1/auth/api-keys/{id}             # 撤销 API Key

知识库管理
  POST   /api/v1/knowledge-bases                # 创建知识库
  GET    /api/v1/knowledge-bases                # 列出知识库
  GET    /api/v1/knowledge-bases/{id}           # 获取知识库详情
  PATCH  /api/v1/knowledge-bases/{id}           # 更新知识库配置
  DELETE /api/v1/knowledge-bases/{id}           # 删除知识库
  GET    /api/v1/knowledge-bases/{id}/stats     # 知识库统计信息

文档管理
  POST   /api/v1/knowledge-bases/{kb_id}/documents          # 上传文档
  POST   /api/v1/knowledge-bases/{kb_id}/documents/text     # 直接上传文本
  POST   /api/v1/knowledge-bases/{kb_id}/documents/url      # 从 URL 抓取
  GET    /api/v1/knowledge-bases/{kb_id}/documents          # 列出文档
  GET    /api/v1/documents/{id}                             # 文档详情
  GET    /api/v1/documents/{id}/chunks                      # 文档分块列表
  DELETE /api/v1/documents/{id}                             # 删除文档
  POST   /api/v1/documents/{id}/reprocess                   # 重新处理

检索接口(核心)
  POST   /api/v1/retrieval/search               # 标准混合检索
  POST   /api/v1/retrieval/search/advanced      # 带 query 改写的高级检索
  POST   /api/v1/retrieval/multi-search         # 多 query 批量检索
  POST   /api/v1/retrieval/rerank               # 独立 rerank 接口(给已有候选集排序)
  POST   /api/v1/retrieval/embed                # 独立 embedding 接口

直接数据访问
  GET    /api/v1/chunks/{id}                    # 获取单个 chunk(含原文)
  POST   /api/v1/chunks/batch                   # 批量获取 chunks

反馈与优化
  POST   /api/v1/retrieval/{request_id}/feedback  # 检索结果反馈

监控
  GET    /api/v1/usage                          # 当前租户用量统计
  GET    /healthz                               # 健康检查
  GET    /metrics                               # Prometheus 指标
```

### 2. 核心检索接口设计

**标准检索 (`POST /api/v1/retrieval/search`)**

```json
// Request
{
  "kb_ids": ["uuid1", "uuid2"],         // 必填,要检索的知识库列表
  "query": "用户问题",                    // 必填
  "top_k": 5,                            // 可选,默认 5
  "filters": {                           // 可选,元数据过滤
    "chunk_type": "text",
    "tags": ["产品手册"],
    "metadata": {"version": "v2.0"}      // 自定义元数据过滤
  },
  "options": {
    "enable_rerank": true,               // 默认 true
    "include_parent_context": false,     // 是否返回父块上下文
    "include_metadata": true,
    "score_threshold": 0.5               // 最低分数阈值
  }
}

// Response
{
  "request_id": "req_xxx",               // 用于反馈和追踪
  "results": [
    {
      "chunk_id": "uuid",
      "content": "...",
      "score": 0.87,
      "rerank_score": 0.92,
      "document": {
        "id": "uuid",
        "name": "产品手册.pdf",
        "metadata": {...}
      },
      "kb_id": "uuid",
      "chunk_type": "text",
      "page_num": 12,
      "bbox": {"x0": 100, "y0": 200, "x1": 500, "y1": 300},
      "metadata": {...},
      "parent_chunk": {                  // 如果 include_parent_context=true
        "id": "uuid",
        "content": "..."
      }
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
    "after_rerank": 5
  }
}
```

**高级检索 (`POST /api/v1/retrieval/search/advanced`)**

支持 query 改写、HyDE、子查询分解等增强能力,但**不做生成**,只返回检索结果:

```json
{
  "kb_ids": ["..."],
  "query": "...",
  "enhancements": {
    "query_rewrite": true,               // 改写为更适合检索的形式
    "hyde": false,                       // 假设性文档生成
    "decompose": true,                   // 复杂问题分解为子查询
    "max_sub_queries": 3
  },
  "top_k": 5
}

// Response 多了:
{
  ...
  "enhancement_info": {
    "rewritten_query": "...",
    "sub_queries": ["...", "..."],
    "hyde_doc": null
  },
  ...
}
```

### 3. SDK 设计原则

提供 Python 和 TypeScript 两个官方 SDK,设计要简洁:

```python
# Python SDK 示例
from kb_platform import KnowledgeBaseClient

client = KnowledgeBaseClient(
    api_key="kb_xxx",
    base_url="https://kb.example.com"
)

# 检索
results = await client.search(
    kb_ids=["kb_uuid"],
    query="用户问题",
    top_k=5,
    filters={"tags": ["产品"]}
)

# 异步上传文档
job = await client.upload_document(
    kb_id="kb_uuid",
    file_path="./manual.pdf"
)
await job.wait_for_completion()
```

### 4. MCP Server 接入

提供官方 MCP Server,让 Claude Desktop、各种 MCP 兼容客户端零成本接入:

```python
# 暴露的 MCP Tools
- search_knowledge_base(kb_id, query, top_k)    # 基础检索
- list_knowledge_bases()                         # 列出可用知识库
- get_document(document_id)                      # 获取文档信息
- get_chunk(chunk_id)                            # 获取分块原文
```

---

## 五、项目目录结构

```
kb-platform/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── pyproject.toml
├── PROJECT.md                  # 本文件
├── README.md
├── docs/                       # 设计文档
│   ├── architecture.md
│   ├── api-reference.md
│   └── phases/                 # 各 Phase 总结
│
├── api/                        # FastAPI 主服务
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── deps.py
│   │   ├── middleware/
│   │   │   ├── auth.py         # API Key / JWT 鉴权
│   │   │   ├── tenant.py       # 租户上下文注入
│   │   │   ├── ratelimit.py    # 限流
│   │   │   └── logging.py      # 请求日志
│   │   ├── models/             # SQLAlchemy ORM
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── api/v1/
│   │   │   ├── auth.py
│   │   │   ├── knowledge_bases.py
│   │   │   ├── documents.py
│   │   │   ├── retrieval.py
│   │   │   ├── chunks.py
│   │   │   └── usage.py
│   │   ├── services/           # 业务逻辑
│   │   │   ├── kb_service.py
│   │   │   ├── document_service.py
│   │   │   ├── retrieval_service.py
│   │   │   ├── ingestion_service.py
│   │   │   └── auth_service.py
│   │   ├── core/
│   │   │   ├── qdrant_client.py
│   │   │   ├── redis_client.py
│   │   │   ├── minio_client.py
│   │   │   ├── embedder.py
│   │   │   ├── reranker.py
│   │   │   └── query_enhancer.py   # query 改写、HyDE、分解
│   │   └── utils/
│   ├── alembic/
│   └── tests/
│
├── workers/                    # Celery worker
│   ├── celery_app.py
│   ├── tasks/
│   │   ├── document_tasks.py
│   │   ├── embedding_tasks.py
│   │   └── maintenance.py
│   ├── parsers/                # 文档解析
│   │   ├── base.py
│   │   ├── pdf_parser.py
│   │   ├── office_parser.py
│   │   ├── markdown_parser.py
│   │   ├── image_parser.py
│   │   └── audio_parser.py
│   └── chunkers/               # 分块策略
│       ├── base.py
│       ├── semantic_chunker.py
│       ├── markdown_chunker.py
│       └── parent_child_chunker.py
│
├── mcp_server/                 # MCP Server 实现
│   ├── server.py
│   ├── tools.py
│   └── pyproject.toml
│
├── sdks/                       # 官方 SDK
│   ├── python/
│   │   ├── kb_platform/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── typescript/
│       ├── src/
│       └── package.json
│
├── frontend/                   # 管理后台 (Next.js)
│   └── ...
│
├── infra/
│   ├── prometheus/
│   ├── grafana/
│   └── nginx/
│
└── examples/                   # 接入示例
    ├── langgraph_integration.py
    ├── llamaindex_integration.py
    ├── dify_integration.md
    └── raw_api_examples/
```

---

## 六、PostgreSQL Schema

```sql
-- 租户
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',           -- free/pro/enterprise
    quota JSONB DEFAULT '{}',                  -- 配额配置
    config JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 用户(管理后台用户)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'viewer',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- API Key(对外 API 鉴权)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) UNIQUE NOT NULL,    -- 存 hash,不存原文
    key_prefix VARCHAR(20),                   -- 显示用,如 "kb_live_xxxx"
    scopes JSONB DEFAULT '[]',                -- 权限范围(可访问哪些 KB)
    rate_limit INT DEFAULT 100,               -- QPS 限制
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);

-- 知识库
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    embedding_model VARCHAR(100) DEFAULT 'bge-m3',
    embedding_dim INT DEFAULT 1024,
    chunk_size INT DEFAULT 512,
    chunk_overlap INT DEFAULT 50,
    retrieval_config JSONB DEFAULT '{}',
    qdrant_collection VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    document_count INT DEFAULT 0,
    chunk_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

-- 文档
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    name VARCHAR(500) NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    minio_path VARCHAR(500),
    file_hash VARCHAR(64),
    source_type VARCHAR(50) DEFAULT 'upload', -- upload/text/url/api
    source_url TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    chunk_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_documents_kb_status ON documents(kb_id, status);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);

-- 分块
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    kb_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64),
    chunk_type VARCHAR(20) DEFAULT 'text',
    parent_chunk_id UUID REFERENCES chunks(id),
    page_num INT,
    bbox JSONB,
    qdrant_point_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_kb ON chunks(kb_id);
CREATE INDEX idx_chunks_qdrant_point ON chunks(qdrant_point_id);

-- 检索日志(用于优化和审计)
CREATE TABLE retrieval_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    api_key_id UUID,
    kb_ids UUID[],
    query TEXT,
    rewritten_query TEXT,
    sub_queries TEXT[],
    retrieved_chunk_ids UUID[],
    rerank_scores FLOAT[],
    total_latency_ms INT,
    stage_latencies JSONB,                    -- 各阶段耗时
    feedback VARCHAR(20),                     -- good/bad/null
    feedback_detail TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_retrieval_logs_request ON retrieval_logs(request_id);
CREATE INDEX idx_retrieval_logs_tenant_time ON retrieval_logs(tenant_id, created_at DESC);

-- 用量统计(按天聚合)
CREATE TABLE usage_daily (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    date DATE NOT NULL,
    api_calls INT DEFAULT 0,
    retrieval_calls INT DEFAULT 0,
    documents_uploaded INT DEFAULT 0,
    chunks_created INT DEFAULT 0,
    embedding_tokens BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    UNIQUE(tenant_id, date)
);
```

---

## 七、关键实现规范

### 1. API Key 鉴权
- API Key 格式:`kb_live_<32位随机字符>` 或 `kb_test_<32位随机字符>`
- 数据库只存 SHA256 hash,不存原文
- 创建时返回明文一次,之后不可见
- 支持 scopes 限制(比如某个 Key 只能访问指定 KB)
- 每次调用更新 `last_used_at`(异步,不阻塞请求)

### 2. 检索流程标准化
标准检索必须包含:
1. API Key 校验 + 租户上下文注入
2. 限流检查(基于 Redis 滑动窗口)
3. 输入参数校验
4. 缓存检查(Redis,TTL 5 分钟,key 包含 tenant_id)
5. 在 Qdrant 中并行执行 dense vector 检索 + sparse keyword 检索
6. RRF 融合(k=60)
7. 从 PG 批量获取 chunk content
8. Rerank 精排(BGE-Reranker)
9. 父块上下文补全(如配置)
10. 写入 retrieval_logs(异步)
11. 写入缓存
12. 返回带 request_id 的结果

### 3. Qdrant 操作规范
- 创建 Collection 时 `on_disk=True` 节省内存
- 批量写入用 `upsert(points=[...], wait=False)`
- 查询必须带 `tenant_id` filter
- 必建索引字段:`tenant_id`、`doc_id`、`chunk_type`、`tags`、`created_at`
- 每个 Collection 同时维护 dense vector 和 sparse vector,关键词检索不再依赖外部全文检索服务

### 4. 分块策略
- 默认语义分块(按段落+标题层级)
- 表格独立成块,转 Markdown
- 代码块独立成块,保留语言信息
- 父子块:子块 256 token 检索,父块 1024 token 用于上下文补全
- 必须保留位置信息(page_num、bbox)用于溯源

### 5. API 响应规范
- 所有响应包含 `request_id`(从 header `X-Request-ID` 或自动生成)
- 列表接口统一分页格式:
```json
  {
    "data": [...],
    "pagination": {
      "cursor": "next_cursor",
      "has_more": true,
      "total": 1234   // 可选,大表可省略
    }
  }
```
- 错误响应统一(参考 RFC 7807):
```json
  {
    "error": {
      "code": "RESOURCE_NOT_FOUND",
      "message": "Knowledge base not found",
      "detail": {"kb_id": "..."},
      "request_id": "req_xxx",
      "type": "https://docs.kb-platform.com/errors/RESOURCE_NOT_FOUND"
    }
  }
```

### 6. 限流策略
- 默认每个 API Key 100 QPS,可在 API Key 配置中调整
- 用 Redis 滑动窗口实现
- 超限返回 429,带 `Retry-After` header
- 用量统计每天聚合写入 `usage_daily` 表

### 7. 代码风格
- 所有函数必须有完整 type hints
- 用 `ruff` + `black` 格式化
- 用 `mypy --strict` 检查
- 所有 public 函数必须有 Google 风格 docstring
- 测试覆盖率 >70%
- 用 `structlog` 输出结构化日志,**不允许使用 print**

---

## 八、开发阶段(按顺序执行)

### Phase 1: 基础设施 (Week 1)
- [x] 项目骨架(uv 项目、目录结构、配置管理)
- [x] Docker Compose 编排所有基础服务
- [x] PostgreSQL Schema + Alembic 迁移
- [x] Qdrant、Redis、MinIO 客户端封装
- [x] 基础健康检查 + Prometheus metrics 端点
- [x] 结构化日志(structlog)集成

### Phase 2: 鉴权与多租户 (Week 2)
- [x] 用户/租户/API Key 数据模型
- [x] JWT 用户登录(管理后台用)
- [x] API Key 鉴权中间件
- [x] 租户上下文注入中间件
- [x] 限流中间件(Redis 滑动窗口)
- [x] 用量统计基础

### Phase 3: 数据接入 Pipeline (Week 3-4)
- [x] 知识库 CRUD API
- [x] 文档上传 API(文件、文本、URL)
- [x] 文档解析器(PDF、DOCX、MD、TXT)
- [x] 智能分块器(语义分块 + 父子块)
- [x] Embedding 服务(Infinity 部署 BGE-M3)
- [x] Celery 任务链:解析 → 分块 → 向量化 → 入库
- [x] 失败重试 + 状态追踪 + 进度查询

### Phase 4: 检索引擎 (Week 5)
- [ ] Qdrant dense vector 检索(多 Collection 并行)
- [ ] Qdrant sparse keyword 检索
- [ ] RRF 融合
- [ ] Rerank 服务
- [ ] 缓存层
- [ ] 标准检索 API(`/retrieval/search`)
- [ ] 完整的 retrieval_logs 写入

### Phase 5: 高级检索能力 (Week 6)
- [ ] Query 改写
- [ ] HyDE
- [ ] 子查询分解
- [ ] 高级检索 API(`/retrieval/search/advanced`)
- [ ] 独立 rerank API
- [ ] 独立 embedding API
- [ ] 多 query 批量检索 API
- [ ] 反馈接口

### Phase 6: 管理后台 (Week 7)
- [ ] Next.js + shadcn/ui 项目搭建
- [ ] 知识库管理界面
- [ ] 文档管理界面(上传、列表、删除、重新处理)
- [ ] API Key 管理界面
- [ ] 用量统计面板
- [ ] 检索测试控制台(类似 Pinecone 的 console)

### Phase 7: SDK 与 MCP (Week 8)
- [ ] Python SDK(异步优先,完整类型注解)
- [ ] TypeScript SDK
- [ ] MCP Server 实现
- [ ] SDK 单元测试 + 集成测试
- [ ] 接入示例(LangGraph、LlamaIndex、Dify)

### Phase 8: 多模态扩展 (Week 9+)
- [ ] 图片处理(Qwen-VL caption)
- [ ] 表格深度处理
- [ ] 音视频处理(Whisper)
- [ ] 性能优化(批量 Embedding、向量索引调优)
- [ ] Grafana 监控面板完善

---

## 九、协作规范(Agent 必读)

1. **每完成一个子任务**先汇报进度并请求确认,再继续
2. **不要一次写大段代码**,按文件、按模块逐步实现
3. **遇到设计决策**(字段加不加、流程怎么走),先列选项和权衡,让我决定
4. **写代码前先写接口定义**:Pydantic schema、函数签名、API 路径定下来,确认后再实现
5. **每个 Phase 结束**写 `docs/phases/phase_X_summary.md`:做了什么、踩了什么坑、下一步计划
6. **任何技术栈替换、Schema 修改、架构调整必须先经过我同意**
7. **优先质量**,代码要清晰、可维护、可测试
8. **测试驱动**:核心模块(检索、分块、向量化)必须有单元测试
9. **不用过时 API**:LangChain 老版本 Chain API、Pydantic v1、SQLAlchemy 1.x 都不要用
10. **不确定就问**,不要猜

---

## 十、禁止事项

- ❌ 不要把 chunk 原文塞进 Qdrant payload
- ❌ 不要在没有 tenant_id 过滤的情况下查询
- ❌ 不要用同步 IO
- ❌ 不要硬编码密钥
- ❌ 不要 try/except: pass
- ❌ 不要绕过 Alembic 改 schema
- ❌ 不要用 print 调试,用 structlog
- ❌ 不要写超过 300 行的单文件
- ❌ 不要在平台代码里耦合任何 Agent 框架(LangGraph/LlamaIndex 等)
- ❌ 不要在响应中返回敏感字段(密码 hash、API Key 原文等)
- ❌ 不要让 API 行为依赖请求体里的 tenant_id

---

## 十一、参考文档

- Qdrant: https://qdrant.tech/documentation/
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0: https://docs.sqlalchemy.org/en/20/
- BGE-M3: https://huggingface.co/BAAI/bge-m3
- MCP: https://modelcontextprotocol.io/
- RFC 7807 (Problem Details): https://datatracker.ietf.org/doc/html/rfc7807

---

请确认理解以上所有内容。开始工作前:
1. 用一段话复述你的理解,**重点说明这是个平台/BaaS,不做 Agent**
2. 列出 Phase 1 的具体任务
3. 告诉我你打算第一步做什么
4. 指出文档中需要澄清的地方