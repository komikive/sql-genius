"""Human-readable comments for the application database schema."""

from __future__ import annotations

from sqlalchemy import MetaData

SchemaComments = dict[str, dict[str, str | dict[str, str]]]


SCHEMA_COMMENTS: SchemaComments = {
    "alembic_version": {
        "table": "Alembic 数据库迁移版本表，用于记录当前 schema 已应用到哪个迁移版本。",
        "columns": {
            "version_num": "当前已应用的 Alembic revision ID。",
        },
    },
    "admin_sessions": {
        "table": "管理端可见的对话会话摘要，用于历史列表和会话删除。",
        "columns": {
            "thread_id": "会话线程 ID，作为管理端会话主键。",
            "first_user_message": "该会话的首条用户消息摘要。",
            "last_user_message": "该会话最近一条用户消息摘要。",
            "turn_count": "该会话累计对话轮次数。",
            "created_at": "会话首次创建时间。",
            "last_activity_at": "会话最近活跃时间。",
        },
    },
    "datasources": {
        "table": "系统注册的数据源连接配置，是技能、记忆、问答案例和会话的归属根节点。",
        "columns": {
            "id": "数据源稳定标识，供前后端和关联表引用。",
            "display_name": "数据源在管理界面展示的名称。",
            "dialect": "数据源数据库方言，例如 postgresql 或 mysql。",
            "connection_url": "数据源连接 URL，用于结构采集和 SQL 执行。",
            "is_default": "是否作为默认数据源展示或选择。",
            "created_at": "数据源注册时间。",
            "updated_at": "数据源配置最近更新时间。",
        },
    },
    "datasource_memory_documents": {
        "table": "每个数据源一份由 Agent 自动维护的 Markdown 主记忆文档。",
        "columns": {
            "datasource_id": "所属数据源 ID，同时作为主键。",
            "title": "主记忆文档标题。",
            "markdown_content": "Agent 维护的主记忆 Markdown 正文。",
            "source_overview": "记忆内容来源或维护过程摘要。",
            "structured_outline": "主记忆的结构化目录，便于检索和 UI 展示。",
            "document_metadata": "主记忆文档的扩展元数据。",
            "created_at": "主记忆文档创建时间。",
            "updated_at": "主记忆文档最近更新时间。",
        },
    },
    "datasource_profiles": {
        "table": "数据源画像与 onboarding 分析状态，描述数据源业务含义和分析结果。",
        "columns": {
            "datasource_id": "所属数据源 ID，同时作为主键。",
            "summary": "数据源整体摘要。",
            "profile_json": "数据源画像的结构化 JSON。",
            "analysis_status": "画像分析状态，例如 pending、running、ready、analysis_failed。",
            "analysis_error": "最近一次画像分析失败原因。",
            "schema_digest": "结构快照摘要哈希，用于判断是否需要重新分析。",
            "last_analyzed_at": "最近一次完成分析的时间。",
            "created_at": "画像记录创建时间。",
            "updated_at": "画像记录最近更新时间。",
        },
    },
    "datasource_qa_examples": {
        "table": "数据源级问答案例库，保存可语义检索的成功问题、SQL 和说明。",
        "columns": {
            "id": "问答案例 ID。",
            "datasource_id": "所属数据源 ID。",
            "skill_pack_id": "关联技能包 ID，可为空。",
            "question": "用户问题或业务问题表述。",
            "sql": "该问题对应的参考 SQL。",
            "note": "SQL 口径、适用场景或注意事项说明。",
            "scenario_tags": "问答案例场景标签。",
            "source": "案例来源，例如 runtime-learning、skill-pack。",
            "source_metadata": "案例来源扩展元数据。",
            "question_embedding": "问题语义向量，用于相似案例召回。",
            "embedding_status": "向量化状态。",
            "embedding_error": "向量化失败原因。",
            "embedding_updated_at": "向量最近更新时间。",
            "created_at": "案例创建时间。",
            "updated_at": "案例最近更新时间。",
        },
    },
    "datasource_schema_snapshots": {
        "table": "数据源最近一次结构采集快照，用于 schema 展示、工具调用和 onboarding。",
        "columns": {
            "datasource_id": "所属数据源 ID，同时作为主键。",
            "payload": "结构采集结果 JSON，包含表、字段、类型和约束等信息。",
            "captured_at": "结构快照采集时间。",
        },
    },
    "checkpoint_blobs": {
        "table": "LangGraph PostgreSQL checkpointer 的大对象/通道载荷表，用于持久化超过主 checkpoint 载荷的二进制状态片段。",
        "columns": {
            "thread_id": "LangGraph 线程 ID。",
            "checkpoint_ns": "checkpoint 命名空间。",
            "channel": "状态通道名称。",
            "version": "通道载荷版本。",
            "type": "载荷编码类型。",
            "blob": "序列化后的二进制状态片段。",
        },
    },
    "checkpoint_migrations": {
        "table": "LangGraph PostgreSQL checkpointer 内部迁移版本表，用于记录 checkpoint 存储结构版本。",
        "columns": {
            "v": "已应用的 LangGraph checkpoint 存储迁移版本号。",
        },
    },
    "checkpoint_writes": {
        "table": "LangGraph PostgreSQL checkpointer 的中间写入表，用于保存任务执行过程中的 pending writes。",
        "columns": {
            "thread_id": "LangGraph 线程 ID。",
            "checkpoint_ns": "checkpoint 命名空间。",
            "checkpoint_id": "所属 checkpoint ID。",
            "task_id": "产生该写入的任务 ID。",
            "idx": "同一任务内的写入序号。",
            "channel": "写入目标状态通道。",
            "type": "写入载荷编码类型。",
            "blob": "序列化后的写入载荷。",
            "task_path": "LangGraph 任务路径。",
        },
    },
    "checkpoints": {
        "table": "LangGraph PostgreSQL checkpointer 的主 checkpoint 表，用于持久化可恢复的图执行状态。",
        "columns": {
            "thread_id": "LangGraph 线程 ID。",
            "checkpoint_ns": "checkpoint 命名空间。",
            "checkpoint_id": "checkpoint 唯一 ID。",
            "parent_checkpoint_id": "父 checkpoint ID，用于恢复状态链路。",
            "type": "checkpoint 载荷编码类型。",
            "checkpoint": "序列化后的 checkpoint 状态。",
            "metadata": "checkpoint 元数据。",
        },
    },
    "learning_signals": {
        "table": "新领域学习信号缓冲表，用于累计尚未形成技能的查询模式。",
        "columns": {
            "id": "学习信号自增 ID。",
            "datasource_id": "所属数据源 ID。",
            "thread_id": "产生信号的会话线程 ID。",
            "user_question": "触发信号的用户问题。",
            "generated_sql": "该轮生成的 SQL，可为空。",
            "sql_explanation": "该轮 SQL 解释，可为空。",
            "domain_summary": "疑似新领域或新模式摘要。",
            "pattern_hash": "用于去重的模式哈希。",
            "created_at": "学习信号创建时间。",
        },
    },
    "onboarding_runs": {
        "table": "数据源 onboarding 后台运行记录，持久化分析进度、事件和结果预览。",
        "columns": {
            "id": "onboarding 运行 ID。",
            "datasource_id": "所属数据源 ID。",
            "status": "运行状态，例如 queued、running、succeeded、failed。",
            "phase": "当前运行阶段。",
            "status_message": "当前状态说明。",
            "error": "运行失败错误信息。",
            "events": "运行过程事件列表。",
            "result_payload": "运行结果结构化载荷。",
            "started_at": "运行开始时间。",
            "completed_at": "运行完成时间。",
            "created_at": "运行记录创建时间。",
            "updated_at": "运行记录最近更新时间。",
        },
    },
    "skill_documents": {
        "table": "技能文档表，当前每个技能以一份 canonical Markdown 主文档作为运行时知识源。",
        "columns": {
            "id": "技能文档自增 ID。",
            "skill_pack_id": "所属技能包 ID。",
            "document_type": "文档类型，canonical 表示技能主文档。",
            "title": "文档标题。",
            "content": "Markdown 文档正文。",
            "source": "文档来源，例如 onboarding-agent、admin-skill-studio。",
            "weight": "检索权重，canonical 文档通常最高。",
            "document_metadata": "文档扩展元数据。",
            "embedding": "文档语义向量。",
            "embedding_status": "文档向量化状态。",
            "embedding_error": "文档向量化失败原因。",
            "embedding_updated_at": "文档向量最近更新时间。",
            "created_at": "文档创建时间。",
            "updated_at": "文档最近更新时间。",
        },
    },
    "skill_packs": {
        "table": "技能包索引表，保存技能的检索锚点、状态和治理元数据；正文在 canonical 技能文档中。",
        "columns": {
            "id": "技能包 ID。",
            "datasource_id": "所属数据源 ID，可为空表示系统级技能。",
            "name": "技能名称。",
            "slug": "技能在数据源内的稳定短标识。",
            "summary": "技能摘要，用于列表展示和语义召回。",
            "business_overview": "历史兼容字段：业务概述，内容会同步进入 canonical 技能文档。",
            "schema_notes": "历史兼容字段：结构备注，内容会同步进入 canonical 技能文档。",
            "status": "技能状态，例如 draft、ready、superseded、rejected。",
            "origin": "技能来源，例如 onboarding、runtime-learning、system。",
            "activation_mode": "技能激活模式，例如 auto、manual。",
            "confidence": "技能可信度评分。",
            "keywords": "技能检索关键词。",
            "metrics": "历史兼容字段：指标定义列表，内容会同步进入 canonical 技能文档。",
            "entities": "历史兼容字段：关键实体列表，内容会同步进入 canonical 技能文档。",
            "table_focus": "技能重点关注的表名列表。",
            "business_rules": "历史兼容字段：业务规则列表，内容会同步进入 canonical 技能文档。",
            "example_sql_pairs": "历史兼容字段：旧版技能内 SQL 示例，现已迁移到独立 QA 案例层。",
            "example_questions": "历史兼容字段：旧版示例问题，现已由独立 QA 案例层替代。",
            "pack_metadata": "技能扩展元数据，例如待补充问题和生成来源。",
            "summary_embedding": "技能摘要语义向量，用于技能召回。",
            "embedding_status": "技能摘要向量化状态。",
            "embedding_error": "技能摘要向量化失败原因。",
            "embedding_updated_at": "技能摘要向量最近更新时间。",
            "created_at": "技能创建时间。",
            "updated_at": "技能最近更新时间。",
        },
    },
    "sql_execution_history": {
        "table": "SQL 执行审计历史，记录工作台执行请求的状态、耗时和错误。",
        "columns": {
            "id": "执行记录自增 ID。",
            "thread_id": "发起执行的会话线程 ID。",
            "datasource_id": "执行 SQL 的数据源 ID。",
            "sql_text": "被执行的 SQL 文本。",
            "status": "执行状态，例如 success、error。",
            "rowcount": "返回行数或影响行数。",
            "error_message": "执行失败错误信息。",
            "duration_ms": "执行耗时，单位毫秒。",
            "executed_at": "执行发生时间。",
        },
    },
    "thread_context_summaries": {
        "table": "数据源绑定会话的滚动摘要，用于长对话上下文压缩。",
        "columns": {
            "thread_id": "会话线程 ID。",
            "datasource_id": "所属数据源 ID。",
            "rolling_summary": "滚动上下文摘要正文。",
            "summary_status": "摘要状态，例如 fresh、stale。",
            "summary_metadata": "摘要扩展元数据。",
            "char_count": "摘要字符数。",
            "recent_turn_count": "近期未压缩轮次数。",
            "summarized_turn_count": "已纳入摘要的轮次数。",
            "compression_count": "上下文压缩执行次数。",
            "last_user_message": "最近一条用户消息摘要。",
            "last_assistant_message": "最近一条助手消息摘要。",
            "last_compacted_at": "最近一次上下文压缩时间。",
            "created_at": "摘要记录创建时间。",
            "updated_at": "摘要记录最近更新时间。",
        },
    },
    "thread_conversation_turns": {
        "table": "数据源绑定会话的原始对话轮次，用于历史回放、学习和摘要压缩。",
        "columns": {
            "id": "对话轮次自增 ID。",
            "thread_id": "会话线程 ID。",
            "datasource_id": "所属数据源 ID。",
            "role": "消息角色，例如 user、assistant。",
            "content": "消息正文。",
            "turn_metadata": "轮次扩展元数据，例如 trace、SQL、工具调用和学习结果。",
            "feedback_rating": "用户反馈评分，例如 positive、negative。",
            "feedback_comment": "用户反馈备注。",
            "feedback_at": "用户反馈时间。",
            "created_at": "对话轮次创建时间。",
        },
    },
}


def apply_schema_comments(metadata: MetaData) -> None:
    """Attach schema comments to SQLAlchemy metadata for future autogeneration."""

    for table_name, table_comments in SCHEMA_COMMENTS.items():
        table = metadata.tables.get(table_name)
        if table is None:
            continue
        table.comment = str(table_comments.get("table") or "")
        columns = table_comments.get("columns")
        if not isinstance(columns, dict):
            continue
        for column_name, comment in columns.items():
            column = table.columns.get(column_name)
            if column is not None:
                column.comment = str(comment)
