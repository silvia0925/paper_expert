# paper_expert-domain — Domain Configuration

## 触发场景

- 用户设置或修改研究领域
- 添加 L0 关键词组
- 添加 L1 词表条目
- 调试分类结果异常（分类不准通常是 domain 配置问题）

## 核心概念

### 无预设原则

Paper Expert 不预设任何学科。所有领域配置完全由用户定义。

### DomainConfig 结构

```python
@dataclass
class DomainConfig:
    domain_name: str = ""               # 研究领域名称
    l0_keywords: dict[str, list[str]]   # L0 关键词组 -> 关键词列表
    l1_vocabulary: dict[str, list[str]] # 规范词 -> 别名列表
    l1_prompt_template: str = ""        # L1 LLM 分类 prompt 模板
```

### 存储位置

- 运行时存在 `PaperExpertConfig.domain` 字段
- 持久化到 `config.toml` 的 `[domain]` 段
- 数据库词表通过 `vocabulary.py:init_vocabulary(db, domain_config=...)` 同步

## 关键文件

| 文件 | 作用 |
|------|------|
| `paper_expert/core/domain.py` | DomainConfig 定义 + 初始化/持久化逻辑 |
| `paper_expert/core/config.py` | `_apply_dict` 中通过 `load_domain_from_toml` 加载领域 |
| `paper_expert/core/vocabulary.py` | `init_vocabulary(db, domain_config=...)` 从 DomainConfig 同步词表 |

## 双入口

### CLI

```bash
paper_expert domain init "领域名" -k '{"组名": ["关键词1", "关键词2"]}'
paper_expert domain show
paper_expert domain add-keyword 组名 关键词
paper_expert domain add-vocab 规范词 "别名1, 别名2"
```

### MCP

- `setup_domain(domain_name, keywords_json)` — 初始化/修改领域
- `get_domain_config()` — 查看当前配置
- `add_domain_keyword(group, keyword)` — 添加 L0 关键词
- `add_domain_vocab(canonical, aliases)` — 添加 L1 词表

## 与 classifier 的交互

1. `classify_l0(title, abstract, domain_config)` 使用 `domain_config.l0_keywords` 做关键词匹配
2. `classify_l1_llm(title, abstract, domain_config, ...)` 使用 `build_l1_prompt(domain_config, ...)` 生成分类 prompt
3. `normalize_l1_tags(raw_tags, db)` 从数据库词表（由 vocabulary.py 从 DomainConfig 同步）做归一化

## 修改领域配置时注意

- 修改 `config.domain` 后必须调用 `config.save()` 持久化
- 如果修改了 `l1_vocabulary`，需要调用 `init_vocabulary(db, domain_config=config.domain)` 同步到数据库
- 已分类的论文不会自动重新分类，需要手动重新执行 `batch_classify`