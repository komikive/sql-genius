"""Tests for signal-driven runtime learning review."""

from __future__ import annotations

import anyio
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.db.models.skill_pack import SkillPack
from app.services import learning_review
from app.services.learning_review import (
    LearningReviewOutput,
    SkillEnrichmentProposal,
    SkillExampleSqlPairCandidate,
    qa_candidate_is_sedimentable,
    run_post_turn_learning_review,
    should_trigger_learning,
)


def test_signal_filter_skips_no_sql() -> None:
    assert not should_trigger_learning(
        generated_sql=None,
        sql_execution_success=False,
        user_feedback_positive=None,
        save_to_skill=False,
    )


def test_signal_filter_skips_failed_execution() -> None:
    assert not should_trigger_learning(
        generated_sql="SELECT * FROM bad_table",
        sql_execution_success=False,
        user_feedback_positive=None,
        save_to_skill=False,
    )


def test_signal_filter_skips_trivial_sql() -> None:
    assert not should_trigger_learning(
        generated_sql="SELECT * FROM users WHERE id = 1",
        sql_execution_success=True,
        user_feedback_positive=None,
        save_to_skill=False,
    )


def test_signal_filter_passes_aggregate_sql_without_join() -> None:
    assert should_trigger_learning(
        generated_sql="SELECT COUNT(*) AS order_count FROM orders",
        sql_execution_success=True,
        user_feedback_positive=None,
        save_to_skill=False,
    )


def test_signal_filter_passes_complex_sql() -> None:
    assert should_trigger_learning(
        generated_sql="SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name",
        sql_execution_success=True,
        user_feedback_positive=None,
        save_to_skill=False,
    )


def test_signal_filter_passes_positive_feedback() -> None:
    assert should_trigger_learning(
        generated_sql="SELECT * FROM users",
        sql_execution_success=True,
        user_feedback_positive=True,
        save_to_skill=False,
    )


def test_signal_filter_blocks_negative_feedback() -> None:
    assert not should_trigger_learning(
        generated_sql="SELECT * FROM users JOIN orders ON users.id = orders.user_id GROUP BY users.name",
        sql_execution_success=True,
        user_feedback_positive=False,
        save_to_skill=False,
    )


def test_signal_filter_passes_save_to_skill() -> None:
    assert should_trigger_learning(
        generated_sql=None,
        sql_execution_success=False,
        user_feedback_positive=None,
        save_to_skill=True,
    )


def test_learning_output_defaults_empty() -> None:
    output = LearningReviewOutput()
    assert output.memory_candidates == []
    assert output.skill_enrichments == []
    assert output.new_domain_signal is False
    assert output.new_domain_summary == ""


def test_learning_result_defaults_empty() -> None:
    from app.services.learning_review import LearningReviewResult

    result = LearningReviewResult()
    assert result.memory_count == 0
    assert result.memory_updates == []
    assert result.qa_example_count == 0
    assert result.enrichment_count == 0
    assert result.signal_buffered is False


def test_qa_sedimentable_requires_execution_success() -> None:
    assert not qa_candidate_is_sedimentable(
        question="按 payer 统计收入",
        sql="SELECT payer_id, SUM(amount) FROM claims GROUP BY payer_id",
        sql_execution_success=False,
    )


def test_qa_sedimentable_requires_nontrivial_sql() -> None:
    assert not qa_candidate_is_sedimentable(
        question="查看用户",
        sql="SELECT * FROM users",
        sql_execution_success=True,
    )


def test_qa_sedimentable_requires_informative_question() -> None:
    assert not qa_candidate_is_sedimentable(
        question="看一下",
        sql="SELECT payer_id, SUM(amount) FROM claims GROUP BY payer_id",
        sql_execution_success=True,
    )


def test_qa_sedimentable_accepts_high_value_case() -> None:
    assert qa_candidate_is_sedimentable(
        question="近 30 天按 payer 统计收入和拒付金额",
        sql="SELECT payer_id, SUM(paid_amount), SUM(denied_amount) FROM claims GROUP BY payer_id",
        sql_execution_success=True,
    )


async def _prepare_learning_review_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    SkillPack.__table__,
                    DatasourceQaExample.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_qa_examples WHERE datasource_id = 'test-learning-qa-ds'")
        )
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-learning-qa-ds'"))


async def _run_datasource_level_qa_fallback() -> tuple[int, str | None]:
    await _prepare_learning_review_tables()
    settings = get_settings()

    async def _empty_learning_output(**_kwargs):
        return LearningReviewOutput()

    original_extract = learning_review.extract_learning_output
    learning_review.extract_learning_output = _empty_learning_output
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                Datasource(
                    id="test-learning-qa-ds",
                    display_name="Learning QA DS",
                    dialect="postgresql",
                    connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                    is_default=False,
                )
            )
            await session.flush()
            result = await run_post_turn_learning_review(
                session,
                datasource_id="test-learning-qa-ds",
                thread_id="thread-learning-qa",
                user_question="最近 30 天各区域净销售额排名",
                assistant_text="已生成并执行 SQL。",
                generated_sql=(
                    "SELECT r.region_name, SUM(o.net_amount) AS total_net_sales "
                    "FROM orders o JOIN stores s ON o.store_id = s.id "
                    "JOIN regions r ON s.region_id = r.id "
                    "GROUP BY r.region_name ORDER BY total_net_sales DESC"
                ),
                sql_explanation="按区域汇总净销售额。",
                activated_skill_pack_names=[],
                sql_execution_success=True,
                settings=settings,
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                sa.select(DatasourceQaExample).where(
                    DatasourceQaExample.datasource_id == "test-learning-qa-ds"
                )
            )
            qa_rows = list(rows.scalars().all())
        return result.qa_example_count, qa_rows[0].skill_pack_id if qa_rows else "missing"
    finally:
        learning_review.extract_learning_output = original_extract
        await _prepare_learning_review_tables()


def test_runtime_learning_sediments_datasource_level_qa_without_activated_skill() -> None:
    qa_count, skill_pack_id = anyio.run(_run_datasource_level_qa_fallback)

    assert qa_count == 1
    assert skill_pack_id is None


async def _run_enrichment_miss_triggers_turn_fallback() -> int:
    await _prepare_learning_review_tables()
    settings = get_settings()

    async def _enrichment_with_unknown_pack(**_kwargs):
        return LearningReviewOutput(
            skill_enrichments=[
                SkillEnrichmentProposal(
                    target_skill_name="不存在的技能包",
                    enrichment_type="example_sql_pair",
                    example_sql_pair=SkillExampleSqlPairCandidate(
                        question="占位问题",
                        sql="SELECT region_name, SUM(net_amount) FROM orders GROUP BY region_name",
                    ),
                )
            ]
        )

    original_extract = learning_review.extract_learning_output
    learning_review.extract_learning_output = _enrichment_with_unknown_pack
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                Datasource(
                    id="test-learning-qa-ds",
                    display_name="Learning QA DS",
                    dialect="postgresql",
                    connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                    is_default=False,
                )
            )
            await session.flush()
            result = await run_post_turn_learning_review(
                session,
                datasource_id="test-learning-qa-ds",
                thread_id="thread-learning-qa-miss",
                user_question="按大区统计净销售额排名",
                assistant_text="已生成并执行 SQL。",
                generated_sql=(
                    "SELECT r.region_name, SUM(o.net_amount) AS total_net_sales "
                    "FROM orders o JOIN stores s ON o.store_id = s.id "
                    "JOIN regions r ON s.region_id = r.id "
                    "GROUP BY r.region_name ORDER BY total_net_sales DESC"
                ),
                sql_explanation="按区域汇总净销售额。",
                activated_skill_pack_names=[],
                sql_execution_success=True,
                settings=settings,
            )
            await session.commit()
        return result.qa_example_count
    finally:
        learning_review.extract_learning_output = original_extract
        await _prepare_learning_review_tables()


def test_runtime_learning_fallback_when_enrichments_do_not_persist() -> None:
    qa_count = anyio.run(_run_enrichment_miss_triggers_turn_fallback)
    assert qa_count == 1
