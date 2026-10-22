# Agent Architecture Reference

> 本文档是对 **deepagents**（LangChain）与 **hermes-agent**（Nous Research）两个项目的深度技术研究总结，
> 作为 SQL Genius 架构演进方向的长期参考。

---

## 一、DeepAgents 架构解析

> 来源：[langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) v0.5.1

### 1.1 核心设计

- **入口**：`create_deep_agent()` → 编译后的 `CompiledStateGraph`（LangGraph）。
- **不是**手写多节点工作流，而是 **Agent + Middleware** 洋葱模型。
- 默认模型为 `ChatAnthropic`（Claude Sonnet），可换任意支持 tool calling 的模型。
- **核心理念**：Agent 不被图结构约束，而是通过工具描述引导模型自主决策。

### 1.2 中间件栈（Middleware Onion）

按固定顺序组合，每层负责一项能力：

| 中间件 | 职责 |
|--------|------|
| `TodoListMiddleware` | 规划：`write_todos` 工具 |
| `SkillsMiddleware` | 从路径加载 SKILL.md 文档 |
| `MemoryMiddleware` | 加载 AGENTS.md 并教模型如何更新 |
| `FilesystemMiddleware` | `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` + 大结果卸载 |
| `SubAgentMiddleware` | `task` 工具 — 子代理独立上下文 |
| `AsyncSubAgentMiddleware` | 远程/后台子代理 |
| `SummarizationMiddleware` | 自动摘要 + 历史落盘 |
| `PatchToolCallsMiddleware` | 悬空 tool_calls 修复 |

### 1.3 上下文管理策略

三层卸载机制防止上下文爆炸：

1. **大工具结果**：超过 ~20k token 的工具输出 → 写入文件 → 消息替换为路径 + 预览。
2. **超长用户消息**：超过 ~50k token → 写文件 + 消息标记 `lc_evicted_to`。
3. **自动摘要**：上下文达模型 85% → 旧消息存入 `conversation_history/` → 替换为结构化摘要。

### 1.4 子代理隔离

- 每个子代理是独立的 `create_agent` 图实例。
- 调用时**只传一条 HumanMessage**（任务描述），父状态完全剔除。
- 返回**最后一条消息**作为 ToolMessage，中间步骤对主代理不可见。
- 默认有 `general-purpose` 子代理与主代理能力对齐。

### 1.5 可迁移要点

- **不用子代理跑每条 SQL**：`task` 适合 schema 探查、批量实验；高频请求留主图。
- **工具描述即路由**：通过极长的 tool description 引导模型选择，而非硬编码路由。
- **继承大结果卸载**：查询大结果集 → 落盘/结构化存储 → 模型只读路径+摘要。
- **middleware 模式**：每层只管一件事，组合灵活。

---

## 二、Hermes Agent 架构解析

> 来源：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) v0.8.0

### 2.1 核心设计

- **单进程标准 Chat Completions 客户端 + 工具循环**，不是固定 DAG。
- 运行时：`AIAgent` — 会话管理、模型调用、工具分发、预算与中断、会话落盘。
- 状态持久化：SQLite + WAL + FTS5。
- 多端入口共享同一套 Agent 逻辑：CLI、Telegram、Discord、Slack 等。

### 2.2 分层记忆系统

| 层级 | 机制 | 存储 | 检索方式 |
|------|------|------|----------|
| 工作记忆 | 内存中 messages | 内存 + SQLite | 顺序 replay |
| 超长对话 | ContextCompressor | 摘要注入对话 | 阈值触发 + LLM 摘要 |
| 策展记忆 | MEMORY.md + USER.md | 文本文件 | 会话初注入 system prompt |
| 情景记忆 | session_search | SQLite FTS5 | 全文检索 + LLM 摘要 |
| 用户建模 | Honcho 插件 | 插件自有 | prefetch/sync API |

**关键设计**：
- MEMORY.md 在会话开始时拍快照注入 system prompt，会话中写入立即落盘但不刷新缓存前缀（保持 prompt caching 稳定）。
- 跨会话检索用 FTS5 而非向量库（更可控、更快）。
- 对写入做注入/外泄模式扫描。

### 2.3 Skills 系统

- **物理形态**：`~/.hermes/skills/` 目录 + `SKILL.md`（YAML frontmatter + 正文），兼容 agentskills.io 标准。
- **渐进式披露**：
  1. `skills_list` — 只暴露 name + description（第一层）
  2. `skill_view` — 加载全文或子文件（第二层、第三层）
- **学习与更新**：`skill_manage` 工具 — create/edit/patch/delete + 安全扫描。
- **条件激活**：`requires_toolsets`、`fallback_for_toolsets` 等声明式约束。

### 2.4 自学习闭环

三条线 + 周期性 nudge：

1. **会话内**：模型通过 memory/skill_manage/todo 工具即时写入。
2. **会话后**：`_spawn_background_review` — 独立线程再跑一个 quiet AIAgent，用专用 prompt 决定是否写入记忆/技能，**不污染主对话**。
3. **跨会话**：session_search 用 FTS 找回历史并由辅助模型摘要。
4. **周期 nudge**：`_memory_nudge_interval`、`_skill_nudge_interval` 提醒模型做维护。

### 2.5 编排模式

- **无独立规划图**：规划靠模型自然语言 + todo 工具 + 压缩摘要中的 Goal/Next Steps。
- **子任务隔离**：`delegate_task` — 独立 AIAgent、独立上下文与终端，父级只收摘要。
- **并行安全**：`_PARALLEL_SAFE_TOOLS` 白名单 + 路径作用域检查。
- **迭代预算**：`IterationBudget` + 接近上限时在 tool 结果里注入 budget warning。

### 2.6 与固定工作流的差异

| 维度 | Hermes 取向 | 固定工作流 |
|------|-------------|-----------|
| 控制流 | **模型 + 工具循环**驱动 | 预定义节点与边 |
| 记忆 | **多存储 + 多检索策略** | 单一 state 或单一向量库 |
| 技能 | **文件化 + 渐进披露** | 硬编码 prompt 或静态 RAG |
| 规划 | **隐式**（对话 + todo + 摘要） | **显式**节点 plan → act |
| 扩展 | **工具/MCP/子代理** | 改图结构或加节点 |

---

## 三、SQL Genius 演进方向

### 3.1 当前架构问题

1. **固定工作流**（`prepare_runtime → run_skill_agent → complete`）束缚了 Agent 的自主性。
2. **SQL-only**：只能生成 SELECT 查询，无法回答业务分析问题或自主探查数据库结构。
3. **Schema 上下文不足**：未将 DatasourceSchemaSnapshot 注入 SQL 生成（已修复）。
4. **工具面太窄**：Agent 只有 4 个工具（list/read/search skill packs + generate SQL）。

### 3.2 目标架构：自主数据库 Agent

借鉴 deepagents 的 harness 和 hermes 的编排/学习：

```
用户消息
  │
  ▼
┌──────────────────────────────────────┐
│  Autonomous Database Agent           │
│  (LLM + Tool Loop, not fixed graph)  │
│                                      │
│  工具面：                              │
│  ├── introspect_schema    查看表/列/索引│
│  ├── query_database       执行 SELECT  │
│  ├── explain_query        获取执行计划   │
│  ├── search_skills        搜索技能包    │
│  ├── recall_memory        检索历史记忆   │
│  ├── search_history       检索历史对话   │
│  ├── write_memory         写入经验      │
│  ├── clarify_user         请求澄清      │
│  └── delegate_task        委派子任务     │
│                                      │
│  上下文管理：                           │
│  ├── Schema snapshot 自动注入          │
│  ├── 大结果集卸载                      │
│  ├── 自动摘要                         │
│  └── 渐进式技能披露                    │
│                                      │
│  学习闭环：                            │
│  ├── 会话内即时写入 memory/skill       │
│  ├── 后台回顾 (background review)     │
│  ├── 跨会话 FTS 检索                  │
│  └── 周期性维护 nudge                 │
└──────────────────────────────────────┘
```

### 3.3 Phase 1 实施状态（已完成）

已实现的核心改造：

| 文件 | 变更 |
|------|------|
| `backend/app/services/agent_tools.py` | 新建 — 7 个自主工具 |
| `backend/app/services/autonomous_agent.py` | 新建 — Agent + Tool Loop 运行时 |
| `backend/app/workflow/graph.py` | 重写 — 使用 autonomous agent 替换 skill_runtime |

已实现的工具：

| 工具 | 功能 |
|------|------|
| `introspect_schema` | 查看表/列/类型，无参列所有表 |
| `execute_query` | 执行 SELECT 查询获取真实数据（限 50 行） |
| `search_skills` | 搜索技能包获取领域知识 |
| `search_skill_documents` | 搜索技能文档获取详细 schema/规则 |
| `recall_memory` | 检索数据源记忆 |
| `search_history` | 搜索历史对话 |
| `save_memory` | 保存发现为 draft 记忆 |

验证结果：
- 同一问题（"哪个供应商…"）：旧架构超时/生成错误列 → 新架构 15s 完成，**自主执行查询**并返回数据分析
- 探索性问题（"看看有哪些表"）：旧架构无法处理 → 新架构自主 introspect + 构建 UNION ALL COUNT 查询

### 3.4 Phase 2 待实施（学习闭环）

- 后台 review agent（参考 hermes `_spawn_background_review`）
- 渐进式技能披露（参考 hermes `skills_list` → `skill_view`）
- 跨会话 FTS 检索
- 周期性 memory/skill nudge

### 3.5 Phase 3 待实施（子代理与上下文管理）

- 子代理委派（参考 deepagents `SubAgentMiddleware`、hermes `delegate_task`）
- 大结果卸载（参考 deepagents `FilesystemMiddleware` eviction）
- 自动摘要（参考 deepagents `SummarizationMiddleware`、hermes `ContextCompressor`）

### 3.6 安全约束

- **SELECT-only** 保留为默认策略，`execute_query` 工具内部有 `SqlSafetyService.validate`。
- **迭代预算**：`MAX_AGENT_STEPS = 15`，超出则优雅退出并返回中间结果。
- **大结果截断**：工具返回超 8000 字符自动截断。
- **Memory 写入**：保存为 draft 状态，需管理员审核。

---

## 四、参考文件索引

### DeepAgents
| 主题 | 路径 |
|------|------|
| 入口与中间件顺序 | `libs/deepagents/deepagents/graph.py` |
| 子代理 | `libs/deepagents/deepagents/middleware/subagents.py` |
| 文件工具与大结果卸载 | `libs/deepagents/deepagents/middleware/filesystem.py` |
| 摘要 | `libs/deepagents/deepagents/middleware/summarization.py` |
| 记忆 | `libs/deepagents/deepagents/middleware/memory.py` |

### Hermes Agent
| 主题 | 路径 |
|------|------|
| 主循环 | `run_agent.py` → `AIAgent` |
| 记忆工具 | `tools/memory_tool.py` |
| 技能工具 | `tools/skills_tool.py` + `tools/skill_manager_tool.py` |
| 上下文压缩 | `agent/context_compressor.py` |
| 会话搜索 | `tools/session_search_tool.py` |
| 委派 | `tools/delegate_tool.py` |
| 记忆管理 | `agent/memory_manager.py` |
| 状态持久化 | `hermes_state.py` → `SessionDB` |
