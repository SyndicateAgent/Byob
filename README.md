# BYOB

BYOB is a self-hosted vector database management system built for AI Agent retrieval. It helps you turn local files and knowledge sources into searchable vector collections, expose them through HTTP APIs and MCP tools, and quickly test RAG quality from a local management console.

BYOB 是一个面向 AI Agent 检索场景的自部署向量数据库管理系统。它用于把本地文件和知识资料整理成可检索的向量知识库，并通过 HTTP API、MCP 工具和本地控制台交给 AI Agent 使用。

## 目录 / Contents

- [中文说明](#中文说明)
- [English Guide](#english-guide)

## 中文说明

### 项目定位

BYOB 的目标是让个人或团队快速搭建一套给 AI Agent 使用的本地知识库与向量检索服务。它关注的是文档导入、解析、切分、向量化、混合检索、重排、MCP 暴露和 RAG 效果测试。

BYOB 包含一个简单的控制台 QA Agent，用于验证 MCP-backed RAG 的召回与回答效果。它不是生产级 Agent 编排平台，也不提供多租户、计费、用量分析、面向公网的 API Key 管理或复杂对话状态管理。

### 核心能力

- 知识库管理：创建、更新、删除知识库，查看文档和 chunk 状态。
- 文档导入：支持文件上传、批量上传、纯文本导入和 URL 导入。
- 自动去重：同一知识库内按文档名称和 SHA-256 文件 hash 跳过重复文件。
- 文档解析：支持 Markdown、TXT、DOCX、PDF；PDF 默认优先使用 MinerU，支持表格、公式、版面和 OCR 友好解析。
- 图片与资源保存：文档中的图片和解析出的图片资源会保存到 MinIO，并能在控制台 chunk 视图中渲染。
- 向量检索：使用 Qdrant 存储向量，支持普通检索、高级检索、多查询检索、metadata、父级上下文和反馈记录。
- Embedding 与 Rerank：默认通过 Infinity 服务运行 `BAAI/bge-m3` 和 `BAAI/bge-reranker-base`。
- MCP 支持：通过 `api.app.mcp_server` 暴露知识库检索工具，方便 AI Agent 以工具形式调用 BYOB。
- QA Agent 测试台：控制台 `/agent` 页面通过 MCP 调用 BYOB 检索服务，可选接入 OpenAI-compatible LLM 生成 Markdown 答案。
- 富文本渲染：控制台支持 Markdown、表格、公式、图片和部分 HTML 内容的安全渲染。
- 运维入口：提供健康检查、Prometheus metrics、MinIO Web UI 和 Qdrant Dashboard 快捷入口。

### 技术栈

- 后端：FastAPI、Pydantic v2、SQLAlchemy async、Alembic、Celery、Redis。
- 数据与对象存储：PostgreSQL、Qdrant、MinIO。
- 文档处理：MinerU、pypdf、python-docx、自定义 chunker。
- 模型服务：Infinity embedding/rerank HTTP 服务。
- MCP：Python MCP SDK，支持 stdio 和 Streamable HTTP。
- 前端：Next.js App Router、React、TypeScript、Tailwind CSS、React Markdown、KaTeX。

### 服务架构

本仓库的 `docker-compose.yml` 启动基础设施服务：PostgreSQL、Redis、Qdrant、MinIO、Embedding、Rerank。API、Celery Worker、MCP Server 和前端控制台默认在宿主机上运行，方便本地开发和自部署调试。

```text
Browser Console -> Next.js frontend
Next.js frontend -> FastAPI API
FastAPI API -> PostgreSQL metadata
FastAPI API -> Redis queue/cache
FastAPI API -> MinIO document assets
FastAPI API -> Qdrant vectors
FastAPI API -> Infinity embedding/rerank

AI Agent -> MCP stdio or Streamable HTTP
MCP transport -> BYOB MCP Server
BYOB MCP Server -> Retrieval APIs

Console QA Agent -> FastAPI /api/v1/agent/ask
FastAPI Agent endpoint -> MCP HTTP
MCP HTTP -> Retrieval APIs
```

### 默认端口

| 服务 | 地址 |
| --- | --- |
| Frontend console | `http://localhost:3000` |
| FastAPI API | `http://localhost:8000` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Qdrant HTTP | `http://localhost:6333` |
| Qdrant gRPC | `localhost:6334` |
| Qdrant Dashboard | `http://localhost:6333/dashboard` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| Embedding service | `http://localhost:7997` |
| Rerank service | `http://localhost:7998` |
| MCP Streamable HTTP | `http://127.0.0.1:8010/mcp` |

### 部署前准备

请先安装以下工具：

- Docker Desktop 或 Docker Engine + Docker Compose。
- Python 3.12 或更高版本。
- `uv` Python 包管理器。
- Node.js 20 或更高版本。
- Git。

Windows PowerShell 示例：

```powershell
python --version
uv --version
node --version
npm --version
docker --version
docker compose version
```

### 本地部署流程

#### 1. 获取代码并进入项目目录

```powershell
git clone <your-repo-url> Byob
Set-Location Byob
```

如果你已经在本仓库中，直接进入项目根目录即可：

```powershell
Set-Location C:\Project\Byob
```

#### 2. 创建并检查环境变量

```powershell
Copy-Item .env.example .env
```

部署前至少检查这些配置：

- `JWT_SECRET_KEY`：生产环境必须换成足够长的随机密钥。
- `DATABASE_URL`：需要与 PostgreSQL 地址、用户、密码和数据库名一致。
- `CORS_ALLOWED_ORIGINS`：需要包含你的前端访问地址。
- `NEXT_PUBLIC_API_BASE_URL`：前端调用 API 的地址，默认是 `http://localhost:8000`。
- `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`：生产环境必须修改默认值。
- `QDRANT_URL`、`MINIO_ENDPOINT_URL`、`EMBEDDING_ENDPOINT_URL`、`RERANK_ENDPOINT_URL`：如果服务不在默认端口，需要同步修改。
- `PDF_PARSER` 与 `MINERU_*`：控制 PDF 解析方式，默认使用 MinerU。
- `MCP_SERVER_URL`：控制台 QA Agent 调用的 MCP HTTP 地址。
- `AGENT_LLM_ENDPOINT_URL`：可选，配置后 `/agent` 会把 MCP 检索上下文交给 OpenAI-compatible LLM 生成答案。

#### 3. 启动基础设施服务

```powershell
docker compose up -d
docker compose ps
```

首次启动 embedding 和 rerank 服务时会下载 `BAAI/bge-m3` 与 `BAAI/bge-reranker-base` 到 Docker volume，可能需要几分钟。建议等待 `docker compose ps` 中 PostgreSQL、Redis、Qdrant、MinIO、embedding、rerank 都处于 healthy 或 running 状态后再继续。

如需查看日志：

```powershell
docker compose logs -f embedding
docker compose logs -f rerank
docker compose logs -f qdrant
```

#### 4. 安装后端依赖

```powershell
uv sync --extra dev
```

`mineru[core]` 已在项目依赖中。首次安装可能较慢，因为 MinerU 和文档解析相关依赖较大。如果你只想快速验证轻量功能，可以在 `.env` 中把 `PDF_PARSER` 调整为 `pypdf`，但完整 PDF 表格、公式和版面解析建议使用默认 MinerU 配置。

#### 5. 初始化数据库

```powershell
uv run alembic upgrade head
```

如果后续启动 API 或创建管理员时报 “missing table” 一类错误，通常说明当前 `DATABASE_URL` 指向的数据库还没有执行迁移，请重新确认 `.env` 后再运行上面的命令。

#### 6. 创建第一个管理员用户

```powershell
$env:BYOB_ADMIN_EMAIL = "admin@example.com"
$env:BYOB_ADMIN_PASSWORD = "replace-with-a-strong-password"
uv run python -m api.scripts.seed_admin
```

如果不设置 `BYOB_ADMIN_PASSWORD`，脚本会生成一个强密码并只打印一次。已有用户不会被覆盖，除非设置 `BYOB_ADMIN_RESET_PASSWORD=true`。

#### 7. 启动 API 服务

新开一个终端，在项目根目录运行：

```powershell
uv run uvicorn api.app.main:app --reload
```

默认 API 地址：

- `http://localhost:8000`
- 健康检查：`http://localhost:8000/healthz`
- Metrics：`http://localhost:8000/metrics`

#### 8. 启动文档导入 Worker

处理上传文件、解析文档、切分 chunk、生成 embedding 时需要 Celery Worker。新开一个终端，在项目根目录运行：

```powershell
uv run celery -A workers.celery_app.celery_app worker -Q ingestion --loglevel=INFO
```

Windows 下 Worker 默认使用 Celery `solo` pool，用来避免进程池在部分 Windows 环境中出现 `billiard` handle 错误。

#### 9. 启动前端控制台

新开一个终端：

```powershell
Set-Location frontend
npm install
npm run dev
```

打开：

```text
http://localhost:3000
```

使用第 6 步创建的管理员账号登录。控制台侧边栏包含 Knowledge Bases、Documents、Retrieval Console、QA Agent、MCP Guide、MinIO Web UI 和 Qdrant Dashboard 等入口。

#### 10. 启动 MCP 服务

大多数 MCP 客户端使用 stdio transport：

```powershell
uv run python -m api.app.mcp_server
```

示例 MCP 客户端配置：

```json
{
	"mcpServers": {
		"byob": {
			"command": "uv",
			"args": ["run", "python", "-m", "api.app.mcp_server"],
			"cwd": "C:/Project/Byob"
		}
	}
}
```

控制台 `/agent` 页面需要 Streamable HTTP MCP 服务。新开一个终端，在项目根目录运行：

```powershell
uv run python -m api.app.mcp_server --transport streamable-http --host 127.0.0.1 --port 8010
```

更多 MCP 工具参数、示例和排查方式见 [docs/mcp.md](docs/mcp.md)，控制台里也可以打开 `/mcp` 页面查看。

### QA Agent 使用方式

1. 启动基础设施、API、Worker、前端和 Streamable HTTP MCP 服务。
2. 在控制台创建知识库并导入文档。
3. 等待文档状态完成，确认 chunk 已生成。
4. 打开 `/agent` 页面，选择知识库或所有知识库，输入问题。
5. 如果配置了 `AGENT_LLM_ENDPOINT_URL`，Agent 会生成 Markdown 答案并引用来源；如果没有配置，Agent 会返回抽取式 Markdown 答案，方便检查 MCP 检索召回是否正确。

LLM 配置示例：

```env
AGENT_LLM_ENDPOINT_URL=http://localhost:11434/v1
AGENT_LLM_API_KEY=
AGENT_LLM_MODEL=qwen2.5:7b-instruct
AGENT_LLM_TIMEOUT_SECONDS=60
AGENT_MAX_CONTEXT_CHARS=12000
```

### 常用 API 和 MCP 工具

管理端 API 使用 JWT 登录：

- `POST /api/v1/auth/login`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`

知识库和文档 API：

- `POST /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{kb_id}`
- `PATCH /api/v1/knowledge-bases/{kb_id}`
- `DELETE /api/v1/knowledge-bases/{kb_id}`
- `GET /api/v1/knowledge-bases/{kb_id}/stats`
- `POST /api/v1/knowledge-bases/{kb_id}/documents`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/batch`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/text`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/url`
- `GET /api/v1/knowledge-bases/{kb_id}/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/chunks`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/reprocess`

检索 API：

- `POST /api/v1/retrieval/search`
- `POST /api/v1/retrieval/search/advanced`
- `POST /api/v1/retrieval/multi-search`
- `POST /api/v1/retrieval/rerank`
- `POST /api/v1/retrieval/embed`
- `POST /api/v1/retrieval/{request_id}/feedback`

QA Agent API：

- `POST /api/v1/agent/ask`

MCP 工具：

- `list_knowledge_bases`
- `list_documents`
- `search_knowledge_base`
- `advanced_search_knowledge_base`
- `multi_search_knowledge_base`
- `get_document_chunks`

### 生产部署建议

当前 Compose 文件主要用于启动依赖服务。生产或长期自部署时，建议按下面方式落地：

1. 使用 `.env` 管理所有部署参数，并替换 `JWT_SECRET_KEY`、PostgreSQL 密码、MinIO 凭据等默认值。
2. 给 PostgreSQL、Qdrant、MinIO、Redis 配置持久化 volume，并建立备份策略。
3. 将 API、Worker、MCP Server 和前端纳入 systemd、Supervisor、PM2、容器平台或其他进程管理器。
4. 只对可信网络暴露 PostgreSQL、Redis、Qdrant、MinIO 和 MCP HTTP；公网入口建议只暴露前端和 API，并放在反向代理或网关之后。
5. 使用 Nginx、Caddy、Traefik 或云网关提供 HTTPS、压缩、访问日志和鉴权策略。
6. 设置正确的 `CORS_ALLOWED_ORIGINS`、`NEXT_PUBLIC_API_BASE_URL`、`NEXT_PUBLIC_MINIO_CONSOLE_URL` 和 `NEXT_PUBLIC_QDRANT_DASHBOARD_URL`。
7. 生产迁移流程固定为：停止写入或进入维护窗口、备份数据库、更新代码、同步依赖、执行 `uv run alembic upgrade head`、重启 API/Worker/MCP/Frontend。
8. MCP HTTP 服务不要直接暴露公网；如果必须远程访问，应放在 VPN、内网、反向代理鉴权或现有网关后面。
9. 监控 `GET /healthz`、`GET /metrics`、Worker 日志、Qdrant/MinIO/PostgreSQL 存储容量和模型服务健康状态。

### 更新与重新部署

```powershell
git pull
uv sync --extra dev
uv run alembic upgrade head
Set-Location frontend
npm install
npm run build
```

然后依次重启 API、Worker、MCP Server 和前端服务。基础设施镜像更新时可以执行：

```powershell
docker compose pull
docker compose up -d
docker compose ps
```

### 质量检查

```powershell
uv run --extra dev ruff check .
uv run --extra dev pytest -q
Set-Location frontend
npm run lint
npm run typecheck
npm run build
```

### 常见问题

- API 启动时报数据库表不存在：确认 `.env` 中 `DATABASE_URL` 正确，然后运行 `uv run alembic upgrade head`。
- `/agent` 返回 MCP unavailable：确认已启动 `uv run python -m api.app.mcp_server --transport streamable-http --host 127.0.0.1 --port 8010`，并检查 `MCP_SERVER_URL`。
- 前端请求被 CORS 拦截：确认 `CORS_ALLOWED_ORIGINS` 包含前端地址，例如 `http://localhost:3000`。
- Embedding 或 rerank 首次启动很慢：模型正在下载，查看 `docker compose logs -f embedding` 或 `docker compose logs -f rerank`。
- PDF 解析失败：确认 MinerU 已随 `uv sync` 安装，或临时设置 `PDF_PARSER=pypdf`；如果 `MINERU_FALLBACK_TO_PYPDF=true`，MinerU 不可用时会自动退回 pypdf。
- MinIO 或 Qdrant 控制台打不开：检查端口是否被占用，以及 `NEXT_PUBLIC_MINIO_CONSOLE_URL`、`NEXT_PUBLIC_QDRANT_DASHBOARD_URL` 是否指向实际地址。

## English Guide

### Project Overview

BYOB is a self-hosted vector database management system for AI Agent retrieval. It focuses on knowledge base management, document ingestion, parsing, chunking, embedding, hybrid search, reranking, MCP tool exposure, and local RAG evaluation.

BYOB includes a lightweight console QA Agent for testing MCP-backed RAG results. It is not a production Agent orchestration framework, and it does not provide multi-tenancy, billing, usage analytics, public API key management, or complex conversation-state management.

### Features

- Knowledge base management with document and chunk status tracking.
- File upload, batch upload, text import, and URL import.
- Duplicate skipping by document name and SHA-256 file hash within the same knowledge base.
- Markdown, TXT, DOCX, and PDF parsing. PDF parsing uses MinerU by default for layout-aware extraction, tables, formulas, and OCR-friendly output.
- Image and asset storage in MinIO, with rendered chunk previews in the console.
- Qdrant-backed vector search with advanced search, multi-search, metadata, parent context, and feedback APIs.
- Infinity-backed embedding and rerank services using `BAAI/bge-m3` and `BAAI/bge-reranker-base` by default.
- MCP server exposing BYOB retrieval tools over stdio or Streamable HTTP.
- Console QA Agent at `/agent` for quick MCP-backed RAG testing.
- Rich answer rendering for Markdown, tables, formulas, images, and safe HTML snippets.
- Health checks, Prometheus metrics, and quick links to MinIO and Qdrant web consoles.

### Stack

- Backend: FastAPI, Pydantic v2, SQLAlchemy async, Alembic, Celery, Redis.
- Storage: PostgreSQL, Qdrant, MinIO.
- Document processing: MinerU, pypdf, python-docx, custom chunkers.
- Model services: Infinity embedding/rerank HTTP services.
- MCP: Python MCP SDK with stdio and Streamable HTTP transports.
- Frontend: Next.js App Router, React, TypeScript, Tailwind CSS, React Markdown, KaTeX.

### Architecture

The provided `docker-compose.yml` starts infrastructure services only: PostgreSQL, Redis, Qdrant, MinIO, embedding, and rerank. The API, Celery Worker, MCP Server, and frontend console run on the host by default, which keeps local development and self-hosted debugging straightforward.

```text
Browser Console -> Next.js frontend
Next.js frontend -> FastAPI API
FastAPI API -> PostgreSQL metadata
FastAPI API -> Redis queue/cache
FastAPI API -> MinIO document assets
FastAPI API -> Qdrant vectors
FastAPI API -> Infinity embedding/rerank

AI Agent -> MCP stdio or Streamable HTTP
MCP transport -> BYOB MCP Server
BYOB MCP Server -> Retrieval APIs

Console QA Agent -> FastAPI /api/v1/agent/ask
FastAPI Agent endpoint -> MCP HTTP
MCP HTTP -> Retrieval APIs
```

### Default Ports

| Service | URL |
| --- | --- |
| Frontend console | `http://localhost:3000` |
| FastAPI API | `http://localhost:8000` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Qdrant HTTP | `http://localhost:6333` |
| Qdrant gRPC | `localhost:6334` |
| Qdrant Dashboard | `http://localhost:6333/dashboard` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| Embedding service | `http://localhost:7997` |
| Rerank service | `http://localhost:7998` |
| MCP Streamable HTTP | `http://127.0.0.1:8010/mcp` |

### Prerequisites

Install these tools first:

- Docker Desktop or Docker Engine with Docker Compose.
- Python 3.12 or newer.
- `uv` for Python dependency management.
- Node.js 20 or newer.
- Git.

PowerShell check:

```powershell
python --version
uv --version
node --version
npm --version
docker --version
docker compose version
```

### Local Deployment

#### 1. Clone the repository

```powershell
git clone <your-repo-url> Byob
Set-Location Byob
```

If the repository already exists locally:

```powershell
Set-Location C:\Project\Byob
```

#### 2. Create and review `.env`

```powershell
Copy-Item .env.example .env
```

Review at least these values before deployment:

- `JWT_SECRET_KEY`: replace the default value in production.
- `DATABASE_URL`: must match the PostgreSQL host, port, user, password, and database.
- `CORS_ALLOWED_ORIGINS`: must include the frontend origin.
- `NEXT_PUBLIC_API_BASE_URL`: frontend API base URL, defaulting to `http://localhost:8000`.
- `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`: replace defaults in production.
- `QDRANT_URL`, `MINIO_ENDPOINT_URL`, `EMBEDDING_ENDPOINT_URL`, and `RERANK_ENDPOINT_URL`: update when services run on non-default hosts or ports.
- `PDF_PARSER` and `MINERU_*`: control PDF parsing behavior.
- `MCP_SERVER_URL`: Streamable HTTP MCP endpoint used by the console QA Agent.
- `AGENT_LLM_ENDPOINT_URL`: optional OpenAI-compatible chat endpoint for generated QA Agent answers.

#### 3. Start infrastructure services

```powershell
docker compose up -d
docker compose ps
```

The first embedding and rerank startup downloads `BAAI/bge-m3` and `BAAI/bge-reranker-base` into Docker volumes, so it can take several minutes. Wait until PostgreSQL, Redis, Qdrant, MinIO, embedding, and rerank are healthy or running before processing documents.

Useful logs:

```powershell
docker compose logs -f embedding
docker compose logs -f rerank
docker compose logs -f qdrant
```

#### 4. Install backend dependencies

```powershell
uv sync --extra dev
```

`mineru[core]` is part of the project dependencies. The first install can take a while because document parsing dependencies are large. For lightweight local checks you can set `PDF_PARSER=pypdf`, but full PDF layout, table, and formula extraction should use the default MinerU setup.

#### 5. Run database migrations

```powershell
uv run alembic upgrade head
```

If the API or admin bootstrap reports missing tables, confirm `DATABASE_URL` and run the migration command again against the same database.

#### 6. Create the first admin user

```powershell
$env:BYOB_ADMIN_EMAIL = "admin@example.com"
$env:BYOB_ADMIN_PASSWORD = "replace-with-a-strong-password"
uv run python -m api.scripts.seed_admin
```

If `BYOB_ADMIN_PASSWORD` is omitted, the script generates a strong password and prints it once. Existing users are not overwritten unless `BYOB_ADMIN_RESET_PASSWORD=true` is set.

#### 7. Start the API

Open a new terminal at the repository root:

```powershell
uv run uvicorn api.app.main:app --reload
```

Default endpoints:

- API: `http://localhost:8000`
- Health: `http://localhost:8000/healthz`
- Metrics: `http://localhost:8000/metrics`

#### 8. Start the ingestion worker

Document parsing, chunking, embedding, and ingestion tasks require the Celery Worker. Open another terminal at the repository root:

```powershell
uv run celery -A workers.celery_app.celery_app worker -Q ingestion --loglevel=INFO
```

On Windows the worker defaults to Celery's `solo` pool to avoid process-pool handle errors in some environments.

#### 9. Start the frontend console

Open another terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

Log in with the admin created earlier. The sidebar includes Knowledge Bases, Documents, Retrieval Console, QA Agent, MCP Guide, MinIO Web UI, and Qdrant Dashboard.

#### 10. Start MCP

Most MCP clients expect stdio transport:

```powershell
uv run python -m api.app.mcp_server
```

Example MCP client configuration:

```json
{
	"mcpServers": {
		"byob": {
			"command": "uv",
			"args": ["run", "python", "-m", "api.app.mcp_server"],
			"cwd": "C:/Project/Byob"
		}
	}
}
```

The console QA Agent at `/agent` requires Streamable HTTP MCP:

```powershell
uv run python -m api.app.mcp_server --transport streamable-http --host 127.0.0.1 --port 8010
```

See [docs/mcp.md](docs/mcp.md) or the console `/mcp` page for full MCP tool parameters, examples, and troubleshooting.

### QA Agent Usage

1. Start infrastructure, API, Worker, frontend, and the Streamable HTTP MCP server.
2. Create a knowledge base and import documents from the console.
3. Wait until document processing completes and chunks are generated.
4. Open `/agent`, choose a knowledge base or all knowledge bases, and ask a question.
5. If `AGENT_LLM_ENDPOINT_URL` is configured, the Agent generates a Markdown answer with source citations. Without it, the Agent returns an extractive Markdown answer from MCP source chunks so you can still inspect retrieval quality.

LLM example:

```env
AGENT_LLM_ENDPOINT_URL=http://localhost:11434/v1
AGENT_LLM_API_KEY=
AGENT_LLM_MODEL=qwen2.5:7b-instruct
AGENT_LLM_TIMEOUT_SECONDS=60
AGENT_MAX_CONTEXT_CHARS=12000
```

### Main APIs and MCP Tools

Management APIs use JWT login:

- `POST /api/v1/auth/login`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`

Knowledge base and document APIs:

- `POST /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{kb_id}`
- `PATCH /api/v1/knowledge-bases/{kb_id}`
- `DELETE /api/v1/knowledge-bases/{kb_id}`
- `GET /api/v1/knowledge-bases/{kb_id}/stats`
- `POST /api/v1/knowledge-bases/{kb_id}/documents`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/batch`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/text`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/url`
- `GET /api/v1/knowledge-bases/{kb_id}/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/chunks`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/reprocess`

Retrieval APIs:

- `POST /api/v1/retrieval/search`
- `POST /api/v1/retrieval/search/advanced`
- `POST /api/v1/retrieval/multi-search`
- `POST /api/v1/retrieval/rerank`
- `POST /api/v1/retrieval/embed`
- `POST /api/v1/retrieval/{request_id}/feedback`

QA Agent API:

- `POST /api/v1/agent/ask`

MCP tools:

- `list_knowledge_bases`
- `list_documents`
- `search_knowledge_base`
- `advanced_search_knowledge_base`
- `multi_search_knowledge_base`
- `get_document_chunks`

### Production Notes

The current Compose file is intended for dependency services. For production or long-running self-hosted deployments:

1. Manage deployment values in `.env` and replace default secrets, PostgreSQL passwords, and MinIO credentials.
2. Use persistent volumes and backups for PostgreSQL, Qdrant, MinIO, and Redis.
3. Run the API, Worker, MCP Server, and frontend under systemd, Supervisor, PM2, a container platform, or another process manager.
4. Keep PostgreSQL, Redis, Qdrant, MinIO, and MCP HTTP on trusted networks. Public entry points should normally be only the frontend and API behind a reverse proxy or gateway.
5. Use Nginx, Caddy, Traefik, or a cloud gateway for HTTPS, compression, access logs, and access control.
6. Set `CORS_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_MINIO_CONSOLE_URL`, and `NEXT_PUBLIC_QDRANT_DASHBOARD_URL` for your deployment hostnames.
7. Use a repeatable upgrade flow: stop writes or enter maintenance mode, back up the database, update code, sync dependencies, run `uv run alembic upgrade head`, then restart API, Worker, MCP, and frontend services.
8. Do not expose MCP HTTP directly to the public internet. Put it behind VPN, a private network, reverse-proxy authentication, or an existing gateway if remote access is required.
9. Monitor `GET /healthz`, `GET /metrics`, Worker logs, storage capacity, and model-service health.

### Update and Redeploy

```powershell
git pull
uv sync --extra dev
uv run alembic upgrade head
Set-Location frontend
npm install
npm run build
```

Then restart the API, Worker, MCP Server, and frontend services. To update infrastructure images:

```powershell
docker compose pull
docker compose up -d
docker compose ps
```

### Quality Checks

```powershell
uv run --extra dev ruff check .
uv run --extra dev pytest -q
Set-Location frontend
npm run lint
npm run typecheck
npm run build
```

### Troubleshooting

- Missing database tables: confirm `DATABASE_URL`, then run `uv run alembic upgrade head`.
- `/agent` reports MCP unavailable: start `uv run python -m api.app.mcp_server --transport streamable-http --host 127.0.0.1 --port 8010` and check `MCP_SERVER_URL`.
- Browser CORS errors: add the frontend origin, such as `http://localhost:3000`, to `CORS_ALLOWED_ORIGINS`.
- Slow first embedding/rerank startup: models are downloading; inspect `docker compose logs -f embedding` or `docker compose logs -f rerank`.
- PDF parsing failures: ensure MinerU was installed by `uv sync`, or temporarily set `PDF_PARSER=pypdf`. With `MINERU_FALLBACK_TO_PYPDF=true`, BYOB falls back to pypdf when MinerU is unavailable.
- MinIO or Qdrant console cannot open: check port conflicts and verify `NEXT_PUBLIC_MINIO_CONSOLE_URL` and `NEXT_PUBLIC_QDRANT_DASHBOARD_URL`.
