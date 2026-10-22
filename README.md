# SQL Genius

基于 LangGraph 的 Text-to-SQL Agent：把自然语言问题变成可执行的 SQL，并在运行中持续积累业务知识与问答经验。

它不只做"一次翻译"。接一个新数据源时，它会先读 Schema、做数据画像，再**自动生成候选技能包**；每次问答结束后，会**复盘这一轮该不该沉淀点什么**——业务口径、表关系、容易踩的坑，都会被写成可检索的技能文档、数据源记忆和 QA 样例，供后续问题召回。

## 为什么值得看

大多数 Text-to-SQL Demo 到"生成一段 SQL 并执行"就结束了。真实场景里卡住人的是另外三件事：**业务口径不知道**、**提问本身不清楚**、**错了不知道为什么**。

这个项目围绕这三点做了工程处理：

| 问题 | 处理方式 |
|---|---|
| 业务口径不知道 | 数据源接入时生成技能包，运行时按问题检索技能文档、QA 样例、历史与记忆 |
| 提问不清楚 | 工作流可中断，向用户反问后从检查点恢复，而不是整段重跑 |
| 错了不知道为什么 | 每轮回合后复盘，把结论沉淀成可追溯的记忆条目；执行全程可观测 |
| LLM 乱写 SQL | 执行前强制只读校验，只放行单条 `SELECT` / `WITH` |

## 核心能力

**单图 + 工具循环。** 工作流只有三个节点：`prepare_runtime → run_agent → complete`。事实查询、Schema 探查、知识检索、记忆读写全部收在工具循环里，由模型按当前问题决定调什么，而不是钉死在固定节点上。图状态持久化，支持中断与恢复。

**八类工具。** `execute_query`、`introspect_schema`、`recall_memory`、`save_memory`、`search_history`、`search_qa_examples`、`search_skill_documents`、`search_skills`。

**数据源接入即学习。** `introspect_schema` 读取表结构，结合数据画像生成候选技能包；管理员可以在 Admin 里审阅、改写、启用。技能可以限定在单个数据源，也可以跨数据源共享。

**回合后学习。** 每轮结束触发一次 review，判断这一轮是否产生了值得保留的知识：业务口径、字段含义、常见误区、可用范例。确认后才写入，避免噪声污染检索库。

**上下文分层。** 线程级滚动摘要负责"这轮聊到哪了"，数据源级记忆负责"这个库的口径是什么"，两者分开存储、分别召回，并有字符预算约束，不会把整库知识常驻在 prompt 里。

**只读边界。** `app/sql/safety.py` 在执行前校验：只允许单条 `SELECT` / `WITH`，拦截写入、DDL 与系统操作。查询还有行数上限和语句超时。

**可观测。** 可选接入 Langfuse，记录请求、模型、工具与耗时。默认**不采集** Prompt、SQL 和结果正文——排障需要链路，不需要业务内容。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、LangGraph、LangChain、SQLAlchemy 2.0、Alembic |
| 数据库 | PostgreSQL 18 + pgvector |
| 前端 | React、Vite、TypeScript、Tailwind v4、shadcn/ui |
| 工具链 | `uv`、Docker Compose |

## 快速开始

```bash
git clone <this-repo> && cd sql-genius
cp .env.example .env
```

在 `.env` 里至少填这几项：

```dotenv
SQL_AGENT_CHAT_BASE_URL=      # OpenAI 兼容地址
SQL_AGENT_CHAT_API_KEY=
SQL_AGENT_CHAT_MODEL=
SQL_AGENT_EMBEDDING_BASE_URL=
SQL_AGENT_EMBEDDING_API_KEY=
SQL_AGENT_EMBEDDING_MODEL=
```

启动整套服务：

```bash
./scripts/demo.sh up
```

它会拉起 PostgreSQL（5432）、后端（8000）和前端（3000），并检查演示用的示例数据源是否需要初始化。跳过这一步：

```bash
SQL_AGENT_DEMO_SKIP_LABS=1 ./scripts/demo.sh up
```

打开 `http://127.0.0.1:3000`。健康检查在 `http://127.0.0.1:8000/health`。

**宿主机开发**（不用 Compose 跑前端）：

```bash
cd backend && uv sync --dev && uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
cd web && npm install && npm run dev -- --host 127.0.0.1 --port 5173
```

## 使用流程

1. **接入数据源**：在 `Datasource Wizard` 填连接串，系统读取 Schema、生成画像。
2. **审阅技能包**：进 `Admin / Skills` 看自动生成的技能文档，按需修改或停用。
3. **开始提问**：在 `Workbench` 用自然语言提问。问题模糊时会被反问，补充后继续。
4. **看它学了什么**：`Admin / Memory` 与 `Admin / QA` 里能看到这一轮沉淀了哪些知识。
5. **追执行记录**：`Admin / History` 查看每次执行的 SQL、耗时与结果。

## 配置

`.env.example` 里有完整清单，常用几项：

| 变量 | 作用 |
|---|---|
| `SQL_AGENT_QUERY_MAX_ROWS` | 单次查询返回行数硬上限，默认 500 |
| `SQL_AGENT_QUERY_TIMEOUT_MS` | 语句超时，默认 30000 |
| `SQL_AGENT_OBSERVABILITY_ENABLED` | 是否启用 Langfuse 追踪，默认关闭 |
| `SQL_AGENT_OBSERVABILITY_CAPTURE_CONTENT` | 是否采集 Prompt / SQL / 结果正文，默认关闭 |
| `SQL_AGENT_RUNTIME_MEMORY_CHAR_BUDGET` | 单轮注入的记忆字符预算 |
| `SQL_AGENT_DATASOURCE_MEMORY_CHAR_BUDGET` | 单数据源记忆召回总量预算 |
| `SQL_AGENT_EMBEDDING_DIMENSION` | 向量维度，需与 pgvector 列定义一致，默认 1024 |

## 目录

```
backend/
  app/workflow/       LangGraph 图与状态定义
  app/services/       Agent 主循环、工具、接入、记忆、学习复盘
  app/rag/            向量化与检索
  app/sql/            执行与只读安全校验
  app/api/routers/    chat / execution / admin_* / health
  app/db/models/      数据模型（Alembic 迁移在 backend/alembic）
web/
  src/pages/          Workbench、Overview、Admin 各页、数据源向导
scripts/demo.sh       本地演示栈的启停与检查
docs/                 架构说明、Skill Studio 设计与示例数据源说明
```

## 开发

```bash
# 后端测试
cd backend && uv run pytest

# 前端检查与构建
cd web && npm run lint && npm run build

# 检查演示栈是否可达
./scripts/demo.sh check

# Docker 侧改动后重建
docker compose up -d --build
```

## 文档

- [`docs/agent-architecture-reference.md`](docs/agent-architecture-reference.md) — Agent 架构与工具设计参考
- [`docs/current-system-explainer.md`](docs/current-system-explainer.md) — 系统现状讲解
- [`docs/skill-studio-rollout.md`](docs/skill-studio-rollout.md) — Skill Studio 与学习闭环
- [`docs/lab-databases-overview.md`](docs/lab-databases-overview.md) — 示例数据源说明

## 已知边界

- 单机单进程部署。没有做多租户隔离和水平扩展，生产使用需要自己补。
- 技能与记忆的生效依赖审核流程，全自动写入容易引入噪声，所以默认保留人工确认。
- SQL 校验是保守的白名单策略，会挡掉一部分合法的复杂查询。
- 向量检索用 pgvector 精确搜索，数据量大之后需要换 ANN 索引。

## 许可

MIT，见 [LICENSE](LICENSE)。
