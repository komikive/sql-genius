"""
Autonomous database agent tools.

Inspired by deepagents' FilesystemMiddleware tool pattern and
hermes-agent's registry + dispatch model. Each tool is a standalone
async function that the LLM can invoke through LangChain tool calling.
"""

from __future__ import annotations

import json
from typing import Any

import anyio
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.skill_pack import SkillPack
from app.db.models.skill_document import SkillDocument
from app.db.models.thread_conversation_turn import ThreadConversationTurn
from app.rag.embed_service import build_embedding_client
from app.services.datasource_memory import apply_memory_candidate_to_document
from app.services.datasource_resolve import resolve_datasource_url
from app.services.qa_examples import search_datasource_qa_examples
from app.services.skill_documents import render_canonical_skill_document
from app.sql.execution import run_bounded_select
from app.sql.safety import SqlSafetyService


def build_agent_tools(
    session: AsyncSession,
    settings: Settings,
    datasource_id: str,
    thread_id: str | None = None,
) -> list[Any]:
    """构造自主 Agent 的 8 个 LangChain 工具（闭包捕获 session / datasource_id）。

    约定：一律返回 JSON 字符串；错误写入 error 字段，不抛异常，便于模型自我修正。
    返回顺序影响模型 tool schema 排列：QA/历史检索靠前，execute_query 居中。
    """

    # --- 结构与执行 ---
    @tool
    async def introspect_schema(
        table_name: str | None = None,
    ) -> str:
        """Query the database schema. Without table_name: list all tables.
        With table_name: show columns, types, and constraints for that table.
        Use this to understand what tables and columns exist before writing SQL."""
        snapshot = await session.get(DatasourceSchemaSnapshot, datasource_id)
        if not snapshot or not snapshot.payload:
            return json.dumps({"error": "no_schema_snapshot", "hint": "数据源还未完成结构采集"})

        tables = snapshot.payload.get("tables") or []
        if not isinstance(tables, list):
            schemas_dict = snapshot.payload.get("schemas", {})
            flat: list[dict] = []
            if isinstance(schemas_dict, dict):
                for tbl_list in schemas_dict.values():
                    if isinstance(tbl_list, list):
                        flat.extend(tbl_list)
            tables = flat

        if table_name:
            needle = table_name.lower().strip()
            match = next(
                (t for t in tables if (t.get("name") or "").lower() == needle),
                None,
            )
            if not match:
                available = [t.get("name") for t in tables[:30]]
                return json.dumps(
                    {"error": "table_not_found", "available_tables": available},
                    ensure_ascii=False,
                )
            return json.dumps(match, ensure_ascii=False, default=str)

        summary = []
        for t in tables[:50]:
            name = t.get("name") or "?"
            cols = t.get("columns", [])
            col_names = [c.get("name", "?") for c in cols[:12]] if isinstance(cols, list) else []
            summary.append({"table": name, "columns": col_names, "column_count": len(cols)})
        return json.dumps(summary, ensure_ascii=False)

    @tool
    async def execute_query(sql: str) -> str:
        # SqlSafetyService + NullPool 一次性连接；结果截断防撑爆上下文
        """Execute a read-only SELECT query against the datasource and return results.
        Only SELECT queries are allowed. Results are limited to 50 rows.
        Use this to verify SQL correctness or fetch data the user needs."""
        ok, reason = SqlSafetyService.validate(sql)
        if not ok:
            return json.dumps(
                {"error": "sql_rejected", "reason": reason, "hint": "只允许 SELECT 查询"},
                ensure_ascii=False,
            )
        try:
            url = await resolve_datasource_url(session, settings, datasource_id)
        except Exception as exc:
            return json.dumps({"error": "datasource_unreachable", "detail": str(exc)[:200]})

        def _run():
            return run_bounded_select(
                url,
                sql,
                max_rows=min(50, settings.sql_agent_query_max_rows),
                timeout_ms=settings.sql_agent_query_timeout_ms,
            )

        try:
            query_result = await anyio.to_thread.run_sync(_run)
        except Exception as exc:
            return json.dumps(
                {"error": "execution_failed", "detail": str(exc)[:300]},
                ensure_ascii=False,
            )
        rows = query_result.rows
        visible_rows = rows[:20]
        return json.dumps(
            {
                "rows": visible_rows,
                "total_returned": len(rows),
                "truncated": query_result.truncated or len(rows) > len(visible_rows),
            },
            ensure_ascii=False,
            default=str,
        )

    # --- 领域知识检索（答辩重点：QA 与历史优先于盲目写 SQL）---
    @tool
    async def search_skills(query: str | None = None) -> str:
        """Search available skill packs for the current datasource.
        Skill packs are light-weight indexes for canonical skill documents.
        Use this to pick the most relevant skill before reading its main document."""
        from sqlalchemy import or_, select as sa_select

        cooked_query = (query or "").strip()
        client = build_embedding_client(settings)
        if client is not None and cooked_query:
            try:
                vector = await client.aembed_query(cooked_query)
                distance_expr = SkillPack.summary_embedding.cosine_distance(vector)
                result = await session.execute(
                    sa_select(SkillPack, distance_expr.label("distance"))
                    .where(SkillPack.datasource_id == datasource_id)
                    .where(SkillPack.status.notin_(["superseded", "rejected"]))
                    .where(
                        or_(
                            SkillPack.origin != "runtime-learning",
                            SkillPack.status != "draft",
                        )
                    )
                    .where(SkillPack.embedding_status == "ready")
                    .where(SkillPack.summary_embedding.is_not(None))
                    .order_by(distance_expr, SkillPack.confidence.desc(), SkillPack.name.asc(), SkillPack.id.asc())
                    .limit(3)
                )
                rows = result.all()
                packs = [row[0] for row in rows]
            except Exception:
                packs = []
        else:
            packs = []

        if not packs:
            stmt = (
                sa_select(SkillPack)
                .where(SkillPack.datasource_id == datasource_id)
                .where(SkillPack.status.notin_(["superseded", "rejected"]))
                .where(
                    or_(
                        SkillPack.origin != "runtime-learning",
                        SkillPack.status != "draft",
                    )
                )
                .limit(3)
            )
            result = await session.execute(stmt)
            packs = list(result.scalars().all())
        if not packs:
            return json.dumps({"items": [], "hint": "该数据源暂无可用技能包"})

        docs_by_pack: dict[str, SkillDocument] = {}
        pack_ids = [p.id for p in packs]
        if pack_ids:
            docs_result = await session.execute(
                sa_select(SkillDocument)
                .where(SkillDocument.skill_pack_id.in_(pack_ids))
                .where(SkillDocument.document_type.in_(["canonical", "overview"]))
                .order_by(SkillDocument.weight.desc(), SkillDocument.id.asc())
            )
            for document in docs_result.scalars().all():
                docs_by_pack.setdefault(document.skill_pack_id, document)

        items = []
        for p in packs:
            canonical_document = docs_by_pack.get(p.id)
            items.append({
                "id": p.id,
                "name": p.name,
                "summary": p.summary,
                "table_focus": p.table_focus or [],
                "keywords": p.keywords or [],
                "canonical_document_id": (
                    int(canonical_document.id) if canonical_document is not None else None
                ),
                "canonical_document_excerpt": (
                    (canonical_document.content or "")[:1200]
                    if canonical_document is not None
                    else render_canonical_skill_document(p)[:1200]
                ),
            })
        return json.dumps({"items": items}, ensure_ascii=False)

    @tool
    async def search_qa_examples(query: str, limit: int = 5) -> str:
        # 独立 QA 层（datasource_qa_examples），向量检索 + 结构化 question/sql/note
        """Search structured QA examples (question + SQL + note) for this datasource.
        Call this early before writing SQL whenever the user asks for metrics, reports,
        rankings, trends, or any business query — reuse proven question/SQL patterns."""

        items = await search_datasource_qa_examples(
            session,
            datasource_id=datasource_id,
            query=query,
            settings=settings,
            limit=limit,
        )
        if not items:
            return json.dumps({"items": [], "hint": "暂无相关示例问答对"}, ensure_ascii=False)
        return json.dumps({"items": items}, ensure_ascii=False)

    @tool
    async def search_skill_documents(
        skill_pack_id: str,
        query: str,
        limit: int = 5,
    ) -> str:
        """Read the canonical Markdown document for a skill pack (业务方法、口径、易错点).

        The canonical document contains stable business methods, table/join notes,
        metric definitions, and pitfalls. QA examples are searched separately."""
        from sqlalchemy import select as sa_select

        pack = next(
            (
                p
                for p in (
                    await session.execute(
                        sa_select(SkillPack).where(SkillPack.id == skill_pack_id).limit(1)
                    )
                )
                .scalars()
                .all()
            ),
            None,
        )
        if not pack:
            return json.dumps({"error": "skill_pack_not_found"})

        docs_result = await session.execute(
            sa_select(SkillDocument)
            .where(SkillDocument.skill_pack_id == skill_pack_id)
            .order_by(SkillDocument.weight.desc(), SkillDocument.id.asc())
        )
        docs = sorted(
            list(docs_result.scalars().all()),
            key=lambda item: (
                item.document_type not in {"canonical", "overview"},
                -float(item.weight or 0.0),
                int(item.id),
            ),
        )[: max(1, min(int(limit or 5), 5))]
        if docs:
            chunks = [
                {
                    "id": str(d.id),
                    "title": d.title or "",
                    "document_type": d.document_type,
                    "content": (d.content or "")[:1800],
                }
                for d in docs
            ]
        else:
            chunks = [
                {
                    "id": "synthetic-canonical",
                    "title": f"{pack.name} 技能主文档",
                    "document_type": "canonical",
                    "content": render_canonical_skill_document(pack)[:1800],
                }
            ]
        return json.dumps({"skill_pack": pack.name, "documents": chunks}, ensure_ascii=False)

    @tool
    async def recall_memory(query: str) -> str:
        # 运行时二次召回；prepare 阶段已注入一批，工具用于追问细化
        """Search the datasource's canonical memory document by relevant sections."""
        from app.services.datasource_memory import recall_datasource_memory

        chunks = await recall_datasource_memory(
            session, datasource_id=datasource_id, query=query, settings=settings,
        )
        if not chunks:
            return json.dumps({"items": [], "hint": "暂无相关记忆"})

        items = [
            {
                "id": chunk.id,
                "title": chunk.title,
                "section": chunk.section,
                "content": chunk.content[:500],
                "keywords": chunk.keywords,
            }
            for chunk in chunks[:5]
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    @tool
    async def search_history(query: str, limit: int = 10) -> str:
        # 扫描 thread_conversation_turns 元数据中的 generated_sql（会话级成功案例）
        """Search past successful conversation turns for this datasource (includes generated_sql).
        Call this right after search_qa_examples on data/SQL questions to find prior wins,
        align with past SQL, and avoid reinventing queries the system already solved."""
        from sqlalchemy import select as sa_select

        cooked_query = (query or "").strip()
        stmt = (
            sa_select(ThreadConversationTurn)
            .where(ThreadConversationTurn.datasource_id == datasource_id)
            .order_by(ThreadConversationTurn.id.desc())
            .limit(100)
        )
        result = await session.execute(stmt)
        turns = list(result.scalars().all())
        if not turns:
            return json.dumps({"items": [], "hint": "暂无相关历史对话" if cooked_query else "暂无历史对话"})

        def _history_score(turn: ThreadConversationTurn) -> tuple[int, int]:
            metadata = turn.turn_metadata if isinstance(turn.turn_metadata, dict) else {}
            haystack = "\n".join(
                [
                    str(turn.content or ""),
                    str(metadata.get("generated_sql") or ""),
                    str(metadata.get("sql_explanation") or ""),
                ]
            ).lower()
            if not cooked_query:
                return (1, int(turn.id))
            query_lower = cooked_query.lower()
            score = 0
            if query_lower in haystack:
                score += 4
            for token in query_lower.split():
                if token and token in haystack:
                    score += 1
            return (score, int(turn.id))

        ranked = sorted(turns, key=_history_score, reverse=True)
        if cooked_query:
            ranked = [turn for turn in ranked if _history_score(turn)[0] > 0]
        ranked = ranked[: max(1, min(int(limit or 10), 20))]
        if not ranked:
            return json.dumps({"items": [], "hint": "暂无相关历史对话"})

        items = []
        for t in ranked:
            metadata = t.turn_metadata if isinstance(t.turn_metadata, dict) else {}
            items.append(
                {
                    "role": t.role,
                    "content": t.content[:400],
                    "thread_id": t.thread_id,
                    "created_at": str(t.created_at) if t.created_at else None,
                    "generated_sql": str(metadata.get("generated_sql") or "")[:500] or None,
                    "sql_explanation": str(metadata.get("sql_explanation") or "")[:300] or None,
                    "recalled_memory_titles": [
                        str(item) for item in (metadata.get("recalled_memory_titles") or []) if isinstance(item, str)
                    ][:6],
                }
            )
        return json.dumps({"items": items}, ensure_ascii=False)

    # --- Agent 主动写入主记忆（极少使用；多数沉淀走 post-turn learning）---
    @tool
    async def save_memory(title: str, content: str, memory_type: str = "fact") -> str:
        """Write one concise stable fact into the datasource memory document.
        Use sparingly: only for long-lived, global knowledge worth reusing across conversations."""

        applied = await apply_memory_candidate_to_document(
            session,
            datasource_id=datasource_id,
            title=title,
            content=content,
            memory_type=memory_type,
            confidence=1.0,
            settings=settings,
            source="agent-tool",
            thread_id=thread_id,
        )
        if not bool(applied.get("applied")):
            return json.dumps(
                {
                    "status": "skipped",
                    "reason": applied.get("reason") or "memory_not_written",
                    "title": title[:200],
                    "content_preview": content[:200],
                    "memory_type": memory_type[:32],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "written",
                "title": applied.get("title"),
                "section": applied.get("section"),
                "action": applied.get("action"),
                "change_summary": applied.get("change_summary"),
                "updated_at": applied.get("updated_at"),
            },
            ensure_ascii=False,
        )

    # 列表顺序 = 绑定到 LLM 时的工具展示顺序
    return [
        introspect_schema,
        search_qa_examples,
        search_history,
        recall_memory,
        search_skills,
        search_skill_documents,
        execute_query,
        save_memory,
    ]
