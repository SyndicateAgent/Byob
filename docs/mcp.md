# BYOB MCP 使用说明

BYOB MCP server 让 AI Agent 通过 Model Context Protocol 直接调用本地知识库检索工具。它不会替 Agent 生成最终答案，也不管理会话、Prompt 或 API Key；它只负责把 BYOB 中的知识库、文档和检索结果作为工具暴露给可信环境中的 Agent。

## 前置条件

先确保 BYOB 的基础服务已经启动并可用：

```powershell
docker compose up -d
uv run alembic upgrade head
uv run celery -A workers.celery_app.celery_app worker -Q ingestion --loglevel=INFO
```

至少需要完成这些准备：

- PostgreSQL、Qdrant、Redis、MinIO 正常运行。
- Infinity embedding 服务可访问，默认是 `http://localhost:7997`。
- 如果启用 rerank，Infinity rerank 服务可访问，默认是 `http://localhost:7998`。
- 已创建知识库，并且文档已处理到 `completed` 状态。

## stdio 模式

stdio 是大多数 MCP 客户端的默认集成方式。Agent 客户端会按需启动 BYOB MCP 进程，并通过标准输入/输出通信。

在项目根目录测试启动：

```powershell
uv run python -m api.app.mcp_server
```

典型 MCP 客户端配置：

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

如果客户端不会继承 shell 环境，可以把连接配置显式放进 `env`：

```json
{
  "mcpServers": {
    "byob": {
      "command": "uv",
      "args": ["run", "python", "-m", "api.app.mcp_server"],
      "cwd": "C:/Project/Byob",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://byob:byob@localhost:5432/byob",
        "QDRANT_URL": "http://localhost:6333",
        "EMBEDDING_ENDPOINT_URL": "http://localhost:7997",
        "RERANK_ENDPOINT_URL": "http://localhost:7998"
      }
    }
  }
}
```

## Streamable HTTP 模式

如果 MCP 客户端支持 Streamable HTTP，可以把 BYOB MCP server 作为一个本地 HTTP MCP 服务运行：

```powershell
uv run python -m api.app.mcp_server --transport streamable-http --host 127.0.0.1 --port 8010
```

默认 MCP endpoint 是：

```text
http://127.0.0.1:8010/mcp
```

控制台中的 `/agent` 页面会通过后端配置 `MCP_SERVER_URL` 调用这个 endpoint，用于快速测试 RAG 问答效果。如果设置了 `AGENT_LLM_ENDPOINT_URL`，Agent 会把 MCP 检索上下文交给 OpenAI-compatible Chat Completions 接口生成 Markdown 答案；如果召回 chunk 引用了图片，Agent 会通过 MCP 拉取图片并按 OpenAI-compatible `image_url` 格式传给支持多模态的模型。未设置 LLM 时会返回基于 source chunks 的抽取式答案。

当 `CLIP_PRELOAD_ON_STARTUP=true` 时，MCP Server 启动阶段会先下载并加载 CLIP 模型，避免第一次视觉检索时再等待模型下载。

HTTP 模式适合统一网关或本机多 Agent 共享，但 BYOB MCP 本身不做 API Key 鉴权。生产环境暴露 HTTP MCP 时，应放在内网、VPN、反向代理鉴权或现有网关后面。

## 工具列表

### `list_knowledge_bases`

列出 BYOB 中可用知识库。

参数：

- `include_inactive`: 默认 `false`，是否包含非 active 知识库。

返回字段包括 `id`、`name`、`description`、`status`、`document_count`、`chunk_count` 和 `qdrant_collection`。

### `list_documents`

列出文档，方便 Agent 判断有哪些来源材料。

参数：

- `kb_id`: 可选，限定某个知识库。
- `status`: 默认 `completed`，传 `null` 或空值可不按状态过滤。
- `limit`: 默认 `50`，最大 `200`。

### `search_knowledge_base`

标准混合检索工具，复用 BYOB 的 dense + sparse + CLIP visual + rerank 检索链路。

参数：

- `query`: 必填，用户问题或 Agent 子问题。
- `kb_ids`: 可选，知识库 UUID 列表；不传时检索所有 active 知识库。
- `top_k`: 默认 `5`，范围 `1` 到 `50`。
- `filters`: 可选，当前支持 `chunk_type` 和 `tags`。
- `enable_rerank`: 默认 `true`。
- `enable_visual_search`: 默认 `true`，使用 CLIP 文本向量召回已索引图片。
- `include_metadata`: 默认 `true`。
- `include_parent_context`: 默认 `false`。
- `score_threshold`: 可选，过滤低分结果。

示例参数：

```json
{
  "query": "BYOB 如何存储上传文件和切块？",
  "top_k": 5,
  "filters": {
    "chunk_type": "text",
    "tags": ["架构"]
  },
  "enable_rerank": true,
  "enable_visual_search": true
}
```

返回结果中的 `results[].content` 是原文 chunk，`document` 包含来源文档，`assets` 包含该 chunk 中显式引用或由 CLIP 视觉召回命中的图片/文件 asset manifest，例如 `id`、`url`、`content_type`、`file_size` 和 `source_path`。`stats` 包含 embedding、Qdrant recall、sparse search、visual search、rerank、内容回表等耗时。

默认情况下，检索只返回 `review_status = published` 的文档。`document` 中会包含 `governance_source_type`、`authority_level`、`review_status` 和 `version`，Agent 应在冲突时优先采用更高权威等级的来源，也就是数字更小的 `authority_level`。

### `advanced_search_knowledge_base`

高级检索工具，在标准检索前增加轻量 query rewrite、HyDE 和问题拆解。

参数包含 `search_knowledge_base` 的主要参数，并额外支持：

- `query_rewrite`: 默认 `true`。
- `hyde`: 默认 `false`。
- `decompose`: 默认 `false`。
- `max_sub_queries`: 默认 `3`，范围 `1` 到 `8`。

适合复杂问题、包含多个子条件的问题，或需要 Agent 先扩展检索表达的问题。

### `multi_search_knowledge_base`

批量检索工具，适合 Agent 已经自行拆出多个子问题时一次调用。

参数：

- `queries`: 必填，最多 20 个问题。
- `kb_ids`: 可选。
- `top_k`: 默认 `5`。
- `filters`: 可选。
- `enable_rerank`: 默认 `true`。
- `enable_visual_search`: 默认 `true`。
- `include_metadata`: 默认 `true`。

### `get_document_chunks`

读取指定文档的有序 chunks，适合 Agent 在命中特定文档后继续查看更多上下文。

参数：

- `document_id`: 必填，文档 UUID。
- `offset`: 默认 `0`。
- `limit`: 默认 `50`，最大 `200`。

### `list_document_assets`

列出指定文档解析出的图片或其他二进制 assets。适合 Agent 在命中文档后查看可附带的素材。

参数：

- `document_id`: 必填，文档 UUID。

### `get_document_asset`

读取指定 asset 的二进制内容，返回 base64；图片会额外返回 `data_uri`，可交给支持多模态输入的模型分析。

参数：

- `document_id`: 必填，文档 UUID。
- `asset_id`: 必填，asset UUID。
- `max_bytes`: 默认 `2000000`，最大 `10000000`，用于限制返回体积。

## Agent 使用建议

推荐 Agent 流程：

1. 调 `list_knowledge_bases` 找到可用知识库。
2. 对用户问题调用 `search_knowledge_base` 或 `advanced_search_knowledge_base`。
3. 如果 `results[].assets` 中有相关图片，调用 `get_document_asset` 获取图片内容，让多模态模型直接查看。
4. 如果命中结果来自同一文档且上下文不足，调用 `get_document_chunks` 扩展上下文。
5. 基于 `results[].content` 和相关 assets 生成答案，并引用 `document.name`、`chunk_id` 或页码 metadata。回答中可以使用 asset 的 `url` 以 Markdown 图片或链接形式附带素材。

示例 Agent 指令：

```text
回答用户问题前，优先调用 BYOB MCP 的 search_knowledge_base 工具检索本地知识库。
只根据检索到的 source chunks 回答；如果检索结果不足，说明缺少依据。
如果 results[].assets 中有相关图片，调用 get_document_asset 查看图片内容。
回答时保留来源文档名称，必要时列出 chunk_id，并用 asset.url 附带相关图片或文件。
```

## 常见问题

### `No active knowledge bases are available`

还没有 active 知识库，或数据库连接到了错误的 BYOB 实例。先在控制台创建知识库并导入文档。

### `One or more knowledge bases were not found`

传入的 `kb_ids` 不存在，或知识库不是 active 状态。先调用 `list_knowledge_bases` 获取正确 UUID。

### Embedding 或 rerank 连接失败

确认 Docker Compose 中 Infinity 服务健康：

```powershell
docker compose ps
```

如果服务端口经过代理或改动了端口，更新 `.env` 中的 `EMBEDDING_ENDPOINT_URL` 和 `RERANK_ENDPOINT_URL`。

### stdio 模式没有响应

确认 MCP 客户端的 `cwd` 指向 BYOB 项目根目录，并且使用的是安装过依赖的同一个 Python/uv 环境。

### HTTP MCP 暴露给外部后如何保护

BYOB 不在 MCP 层实现 API Key。请使用反向代理鉴权、VPN、内网 ACL、网关或现有身份体系保护 HTTP MCP endpoint。