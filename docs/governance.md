# BYOB 知识库治理设计

BYOB 现在把文档导入、检索和 Agent 回答建立在明确的治理字段上，避免官方文件、内部 SOP、律师经验、群聊记录和视频转写被同权重混合使用。

## 必填治理字段

新文档导入时必须标注：

- `governance_source_type`: 来源类型，例如 `official_law`、`official_guidance`、`internal_sop`、`expert_summary`、`chat_record`、`video_transcript`、`other`。
- `authority_level`: 权威等级，`1` 最高，`5` 最低。
- `review_status`: 审核状态，支持 `draft`、`reviewed`、`published`、`deprecated`。

建议等级：

| 等级 | 含义 | 示例 |
| --- | --- | --- |
| L1 | 官方最高权威 | 法律法规、正式官方文件 |
| L2 | 权威解释或外部规则 | 法院规则、官方解释 |
| L3 | 内部正式流程 | 已发布 SOP、标准流程 |
| L4 | 已审核经验 | 律师经验总结、审核后的案例说明 |
| L5 | 原始材料 | 群聊记录、视频转写、未审核笔记 |

## 检索规则

默认检索只使用 `review_status = published` 的文档。这样 draft、reviewed 和 deprecated 文档不会进入正式 Agent 回答。

当多个来源同时命中时，BYOB 会优先排序更高权威来源：

```text
L1 > L2 > L3 > L4 > L5
```

MCP 和 HTTP 检索结果会返回文档治理字段，Agent prompt 会要求模型在冲突时优先相信较低 `authority_level` 数字的来源。

## 版本历史

每个文档都有 `current_version`，并在以下场景写入版本快照：

- 初次导入。
- 治理字段更新，例如从 `draft` 发布为 `published`。
- Governance 面板中修改可检索源内容，并触发重新索引。

版本快照保留当时的文件信息、治理字段、metadata、变更说明和操作人信息。

## 内容修正与重新索引

Governance 面板可以加载当前解析后的全文内容；如果解析快照不存在，则回退为 chunk 合并内容。保存修改后，BYOB 会把编辑后的内容作为新的文本源：

1. 删除旧 chunk、旧 MinIO 解析资源、旧上传源对象和 Qdrant 向量点。
2. 更新文档 hash、文件大小、source metadata 和版本号。
3. 写入 `document.content_updated` 审计记录。
4. 将文档重新置为 `pending` 并排队解析、切分、embedding 和索引。

这保证 Agent 后续召回只使用重新索引后的内容，不会混用旧向量、旧图片资源和新文本。

文档 reprocess 会保留原始上传源，但会先删除旧 MinIO 解析快照、旧解析资源、旧 chunk 和旧向量，再重新生成。删除文档会删除该文档的原始上传对象、解析快照、解析资源、chunk 和向量。删除知识库会删除整个 `knowledge_bases/{kb_id}/` MinIO 前缀和对应 Qdrant collection。

## 审计日志

文档生命周期会写入审计日志，包括：

- `document.created`
- `document.governance_updated`
- `document.content_updated`
- `document.reprocessed`
- `document.deleted`

审计日志记录操作人、时间、变更摘要、变更前后快照。控制台 Documents 页面可以打开每个文档的 Governance 面板查看版本、审计历史、当前处理阶段、索引进度、chunk 数和失败信息。

## 推荐交付流程

正式知识库建议采用：

```text
导入资料 -> 标注来源和权威等级 -> 解析入库 -> 人工审核 -> 发布 -> Agent 可检索
```

推荐约束：

- 正式问答 Agent 默认只查 `published` 文档。
- 群聊记录和视频转写应先作为 `draft` 或 `reviewed` 保存，不直接发布。
- 低权威来源不能覆盖高权威来源，只能作为经验补充。
- SOP 更新时先修改治理状态或版本说明，再确认检索结果是否使用新版本。