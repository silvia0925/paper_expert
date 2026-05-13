# Paper Expert — Agent Knowledge Base

> 渐进式披露：本文件只提供定位和索引。具体技术细节按需加载对应 skill。

## 项目一句话

基于 PaperQA2 的通用论文管理与研究助手。提供 CLI + MCP Server 双入口。**所有领域配置由用户自定义，无任何预设学科。**

## 关键差异（vs Scholar Agent）

- **无硬编码领域**: 词表、关键词、分类 prompt 全部由用户通过 `DomainConfig` 定义
- **领域初始化向导**: CLI 和 MCP 提供 domain 管理命令
- **空词表启动**: 词汇量随论文积累和用户定义共同增长
- **领域无关分类器**: L0 和 L1 分类完全使用用户配置，不预设任何学科

## 4 条核心规则

1. **Library 是中枢** — `paper_expert/core/library.py` 编排所有组件。CLI 和 MCP 都通过它调用。
2. **PaperQA2 隔离** — 只有 `paper_expert/adapters/paperqa.py` 可以 `import paperqa`
3. **SQLite 是 source of truth** — 向量索引可重建，SQLite 不可丢
4. **领域无硬编码** — 所有 domain 配置通过 `DomainConfig` 管理，由用户自定义

## 双入口架构

```
OpenCode / Claude Desktop          终端
        |                            |
   MCP Server (stdio)            CLI (Typer)
   paper_expert/mcp_server.py   paper_expert/cli/
        |                            |
        +-------- Library -----------+
                     |
        +---+---+----+----+---------+
        |   |   |    |    |         |
       DB  PQA Search PDF  LLM  DomainConfig
```

- **MCP**: `paper_expert/mcp_server.py` — 14 个 async tools（含 4 个 domain 管理），OpenCode 通过 `opencode.json` 配置调用
- **CLI**: `paper_expert/cli/` — 11 个命令组（含 domain 管理），终端直接使用
- 两个入口调用同一套 `core/` 代码，共享同一个知识库

## 目录速查

| 要改什么 | 去哪里 | 加载 skill |
|---------|--------|-----------|
| 跨模块修改 / 数据流 | `paper_expert/core/library.py` | `paper_expert-architecture` |
| 外部 API 适配器 | `paper_expert/adapters/` | `paper_expert-adapters` |
| SQLite / 数据模型 | `paper_expert/core/database.py`, `paper_expert/models/` | `paper_expert-database` |
| 分类 / 标签 / 词表 | `paper_expert/core/classifier.py`, `vocabulary.py` | `paper_expert-classification` |
| 领域配置 | `paper_expert/core/domain.py`, `config.py` | `paper_expert-domain` |
| QA 问答 / 自动补检 | `paper_expert/core/qa_engine.py`, `auto_fetch.py` | `paper_expert-qa` |
| 综述 / 方向建议 / 专家 | `paper_expert/core/review_engine.py`, `direction_advisor.py`, `domain_expert.py` | `paper_expert-review` |
| 直接 LLM 调用 | `paper_expert/core/llm.py` | `paper_expert-review` |
| CLI 命令 | `paper_expert/cli/` | `paper_expert-cli` |
| MCP Server | `paper_expert/mcp_server.py` | `paper_expert-mcp` |
| 配置 / 目录结构 | `paper_expert/core/config.py` | `paper_expert-config` |
| 运行时报错 / 平台问题 | — | `paper_expert-known-issues` |

## Skill 索引

按需加载，不要一次全部读取。

| Skill | 触发场景 | 内容 |
|-------|---------|------|
| `paper_expert-architecture` | 跨模块修改、理解数据流、调试组件交互 | 组件图、双入口架构、add_paper/search/ask/review 完整流程 |
| `paper_expert-adapters` | 新增 API 源、修改搜索逻辑、调试 API 问题 | adapter 模式、5 个现有 adapter 详情、去重逻辑、PaperQA2 query 接口 |
| `paper_expert-database` | 修改 schema、新增查询、数据 migration | SQL schema v3 (7 表)、全部 CRUD、migration 策略 |
| `paper_expert-classification` | 分类系统、LLM 标签、受控词表 | 三层体系（领域无关）、L0 用户定义关键词、L1 用户定义 prompt |
| `paper_expert-domain` | 设置/修改研究领域、L0 关键词、L1 词表 | DomainConfig 结构、双入口管理、与 classifier/vocabulary 交互 |
| `paper_expert-qa` | QA 问答、自动补检、置信度、摘要 | QAEngine/AutoFetcher 架构、scope 过滤、置信度阈值 |
| `paper_expert-review` | 综述生成、方向建议、领域专家化 | 6 阶段综述管道、方法x问题矩阵、趋势分析、llm.py 工具 |
| `paper_expert-cli` | 新增 CLI 命令、修改命令选项 | Typer 模式、async 桥接、11 个命令组（含 domain） |
| `paper_expert-mcp` | 修改 MCP tools、新增 MCP 功能 | FastMCP 模式、tool 注册、OpenCode 配置、双入口共存、14 个 tools |
| `paper_expert-config` | 修改配置项、调试配置加载 | 完整 TOML 参考、PaperExpertConfig 结构、DomainConfig 持久化 |
| `paper_expert-known-issues` | 运行时报错、平台兼容性 | 已知问题及 workaround、依赖 pin 表 |

## 编码约定（最小集）

- Python >=3.10, type hints, Pydantic v2
- async/await + httpx (网络 I/O)
- `logging.getLogger(__name__)`, 不用 print
- ruff: line-length=100
- 网络失败 graceful degrade, 不崩溃
- Windows: 不用 Unicode 特殊字符
- MCP tools 返回 JSON 字符串或 Markdown 文本，不返回 Python 对象
- 领域配置无预设：所有词表/关键词从 DomainConfig 读取