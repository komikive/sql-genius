"""add canonical memory documents and structured skill example pairs

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-13

"""

from __future__ import annotations

import json
import re
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _truncate(value: str, limit: int = 320) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)] + "..."


def _normalize_example_sql_pairs(
    raw_pairs: Any,
    *,
    fallback_questions: list[str] | None = None,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _push(question: str, sql: str = "", note: str = "", scenario_tags: Any = None) -> None:
        cooked_question = str(question or "").strip()
        cooked_sql = str(sql or "").strip()
        cooked_note = str(note or "").strip()
        tags = [
            str(item).strip()
            for item in (scenario_tags or [])
            if str(item).strip()
        ]
        if not cooked_question:
            return
        key = (cooked_question.lower(), cooked_sql.lower())
        if key in seen:
            return
        seen.add(key)
        pairs.append(
            {
                "question": cooked_question,
                "sql": cooked_sql,
                "note": cooked_note,
                "scenario_tags": tags[:8],
            }
        )

    if isinstance(raw_pairs, list):
        for item in raw_pairs:
            if isinstance(item, str):
                _push(item)
            elif isinstance(item, dict):
                _push(
                    question=str(item.get("question") or item.get("title") or ""),
                    sql=str(item.get("sql") or ""),
                    note=str(item.get("note") or item.get("description") or ""),
                    scenario_tags=item.get("scenario_tags") or item.get("tags") or [],
                )

    for question in fallback_questions or []:
        _push(question)

    return pairs[:24]


def _build_outline(markdown_content: str) -> list[dict[str, Any]]:
    outline: list[dict[str, Any]] = []
    for line in (markdown_content or "").splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            outline.append({"level": len(match.group(1)), "title": match.group(2).strip()})
    return outline[:24]


def _build_initial_memory_markdown(
    *,
    datasource_name: str,
    profile_summary: str | None,
    legacy_entries: list[dict[str, Any]],
) -> str:
    sections = [f"# {datasource_name} 主记忆"]
    sections.append(
        "## 维护说明\n"
        "- 这是一份面向 Agent 与管理员的主记忆文档。\n"
        "- 只保留跨会话稳定、全局有效的业务知识与查询注意事项。\n"
        "- 运行时学习不再直接写入这里，后续内容以人工编辑为准。"
    )
    if (profile_summary or "").strip():
        sections.append(f"## 数据源概览\n{profile_summary.strip()}")
    if legacy_entries:
        lines = []
        for entry in legacy_entries[:12]:
            title = str(entry.get("title") or "").strip()
            content = _truncate(str(entry.get("content") or ""), 280)
            if title and content:
                lines.append(f"- **{title}**：{content}")
            elif title:
                lines.append(f"- **{title}**")
        if lines:
            sections.append("## 已沉淀知识\n" + "\n".join(lines))
    else:
        sections.append("## 已沉淀知识\n- 暂无，请按业务主题整理稳定口径、核心表关系和 SQL 使用注意事项。")
    sections.append("## 查询注意事项\n- 在此维护必须遵守的过滤条件、统计口径、时间字段和关联规则。")
    return "\n\n".join(section.strip() for section in sections if section.strip()).strip()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "datasource_memory_documents" not in existing_tables:
        op.create_table(
            "datasource_memory_documents",
            sa.Column(
                "datasource_id",
                sa.String(length=128),
                sa.ForeignKey("datasources.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("title", sa.String(length=255), nullable=False, server_default="主记忆文档"),
            sa.Column("markdown_content", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_overview", sa.Text(), nullable=True),
            sa.Column("structured_outline", sa.JSON(), nullable=True),
            sa.Column("document_metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        existing_tables.add("datasource_memory_documents")

    if "skill_packs" in existing_tables:
        existing_columns = {
            column["name"] for column in inspector.get_columns("skill_packs")
        }
        if "example_sql_pairs" not in existing_columns:
            op.add_column(
                "skill_packs",
                sa.Column(
                    "example_sql_pairs",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
            )

        skill_rows = bind.execute(
            sa.text(
                """
                SELECT id, example_questions, example_sql_pairs
                FROM skill_packs
                ORDER BY id
                """
            )
        ).mappings()
        for row in skill_rows:
            pairs = _normalize_example_sql_pairs(
                row.get("example_sql_pairs"),
                fallback_questions=list(row.get("example_questions") or []),
            )
            questions = [
                str(item.get("question") or "").strip()
                for item in pairs
                if str(item.get("question") or "").strip()
            ][:24]
            bind.execute(
                sa.text(
                    """
                    UPDATE skill_packs
                    SET example_sql_pairs = CAST(:example_sql_pairs AS jsonb),
                        example_questions = CAST(:example_questions AS jsonb)
                    WHERE id = :skill_pack_id
                    """
                ),
                {
                    "skill_pack_id": row["id"],
                    "example_sql_pairs": json.dumps(pairs, ensure_ascii=True),
                    "example_questions": json.dumps(questions, ensure_ascii=True),
                },
            )

    if {"datasource_memory_documents", "datasources"}.issubset(existing_tables):
        datasource_rows = bind.execute(
            sa.text(
                """
                SELECT d.id, d.display_name, dp.summary
                FROM datasources d
                LEFT JOIN datasource_profiles dp ON dp.datasource_id = d.id
                ORDER BY d.id
                """
            )
        ).mappings()
        for row in datasource_rows:
            exists = bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM datasource_memory_documents
                    WHERE datasource_id = :datasource_id
                    """
                ),
                {"datasource_id": row["id"]},
            ).scalar()
            if exists:
                continue

            legacy_entries = list(
                bind.execute(
                    sa.text(
                        """
                        SELECT title, content
                        FROM datasource_memory_entries
                        WHERE datasource_id = :datasource_id
                          AND status IN ('active', 'review', 'draft')
                        ORDER BY confidence DESC, updated_at DESC, id ASC
                        LIMIT 12
                        """
                    ),
                    {"datasource_id": row["id"]},
                ).mappings()
            )
            markdown = _build_initial_memory_markdown(
                datasource_name=str(row["display_name"] or row["id"]),
                profile_summary=str(row["summary"] or "").strip() or None,
                legacy_entries=legacy_entries,
            )
            source_overview_parts = ["主记忆文档由管理员直接维护。"]
            if str(row["summary"] or "").strip():
                source_overview_parts.append("初始内容已参考数据源画像摘要。")
            if legacy_entries:
                source_overview_parts.append(
                    f"已参考 {len(legacy_entries)} 条历史记忆条目作为初始回填素材。"
                )
            source_overview_parts.append("运行时学习结果不会再自动写入主记忆。")
            bind.execute(
                sa.text(
                    """
                    INSERT INTO datasource_memory_documents (
                      datasource_id,
                      title,
                      markdown_content,
                      source_overview,
                      structured_outline,
                      document_metadata,
                      created_at,
                      updated_at
                    )
                    VALUES (
                      :datasource_id,
                      :title,
                      :markdown_content,
                      :source_overview,
                      CAST(:structured_outline AS jsonb),
                      CAST(:document_metadata AS jsonb),
                      now(),
                      now()
                    )
                    """
                ),
                {
                    "datasource_id": row["id"],
                    "title": f"{str(row['display_name'] or row['id'])} 主记忆",
                    "markdown_content": markdown,
                    "source_overview": " ".join(source_overview_parts),
                    "structured_outline": json.dumps(
                        _build_outline(markdown),
                        ensure_ascii=True,
                    ),
                    "document_metadata": json.dumps(
                        {
                            "initialized_from_profile_summary": bool(
                                str(row["summary"] or "").strip()
                            ),
                            "initialized_legacy_entry_count": len(legacy_entries),
                            "usage_count": 0,
                        },
                        ensure_ascii=True,
                    ),
                },
            )

    if "learning_review_items" in existing_tables:
        bind.execute(
            sa.text(
                """
                UPDATE learning_review_items
                SET status = 'rejected',
                    review_note = COALESCE(review_note, 'memory review retired after canonical memory migration'),
                    reviewed_at = COALESCE(reviewed_at, now())
                WHERE review_kind = 'memory'
                  AND status = 'pending'
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "skill_packs" in existing_tables:
        existing_columns = {
            column["name"] for column in inspector.get_columns("skill_packs")
        }
        if "example_sql_pairs" in existing_columns:
            op.drop_column("skill_packs", "example_sql_pairs")

    if "datasource_memory_documents" in existing_tables:
        op.drop_table("datasource_memory_documents")
