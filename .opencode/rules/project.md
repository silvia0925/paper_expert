# Paper Expert — Project Rules

> 每次对话自动注入。极简，不含技术细节。详情用 skill 按需加载。

## 核心规则

1. **Library 是中枢**: `paper_expert/core/library.py` 编排一切。CLI 和 MCP 都通过它调用，别绕过。
2. **PaperQA2 隔离**: 只有 `paper_expert/adapters/paperqa.py` 可以 `import paperqa`。违反则破坏解耦。
3. **SQLite 是 source of truth**: 向量索引可重建，SQLite 不可丢。写操作必须先写 SQLite。
4. **PDF 按标题命名 + 按分类归档**: `pdfs/<category>/论文标题.pdf`。不允许用 ID 命名，不允许平铺在根目录。
5. **MCP tools 不放业务逻辑**: `mcp_server.py` 只做参数转换和格式化，业务逻辑必须在 Library 里。
6. **领域无硬编码**: 所有词表、关键词、分类 prompt 由用户通过 `DomainConfig` 定义。不预设任何学科。

## 编码红线

- 不用 print，用 `logging.getLogger(__name__)`
- 不用 Unicode 特殊字符（Windows GBK 会崩）
- 不绕过付费墙获取论文
- 网络失败必须 graceful degrade，不允许未捕获的网络异常
- MCP tools 返回 str（JSON 或 Markdown），不返回 Python 对象

## 需要深入？加载 Skill

| 场景 | Skill |
|------|-------|
| 改架构 / 跨模块 | `paper_expert-architecture` |
| 加 API 源 / 改搜索 | `paper_expert-adapters` |
| 改数据库 / schema | `paper_expert-database` |
| 改分类 / 标签 | `paper_expert-classification` |
| 改 QA / 自动补检 | `paper_expert-qa` |
| 改综述 / 方向 / 专家 | `paper_expert-review` |
| 加 CLI 命令 | `paper_expert-cli` |
| 改 MCP tools | `paper_expert-mcp` |
| 改配置 | `paper_expert-config` |
| 改领域配置 | `paper_expert-domain` |
| 遇到报错 | `paper_expert-known-issues` |