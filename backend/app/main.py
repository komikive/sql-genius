"""FastAPI application factory: lifespan, routers, typed error envelopes (SAFE-03)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text

from app.api.error_handlers import register_exception_handlers
from app.api.routers import (
    admin_datasources,
    admin_history,
    admin_learning,
    admin_skill_packs,
    chat,
    execution,
    health,
)
from app.core.config import get_settings
from app.core.db import async_engine
from app.core.observability import shutdown_langfuse
from app.core.psycopg_dsn import raw_psycopg_dsn
from app.core.thread_guard import ThreadRunGuard
from app.workflow.graph import build_workflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：编译 LangGraph 工作流并挂到 app.state.workflow。

    - 正常环境：Postgres checkpointer（与业务库同集群，表 checkpoint_*）
    - pytest：MemorySaver + sql_agent_skip_db_lifespan，避免依赖 checkpoint 表
    - chat / execution 路由通过 request.app.state.workflow 取图
    """
    settings = get_settings()
    # ponytail: process-local single-flight; use Redis/Postgres locks for multi-worker deployment.
    app.state.thread_run_guard = ThreadRunGuard()
    try:
        if settings.sql_agent_skip_db_lifespan:
            app.state.workflow = build_workflow(MemorySaver(), settings)
            yield
            return

        async with AsyncPostgresSaver.from_conn_string(
            raw_psycopg_dsn(settings.sql_agent_database_url)
        ) as checkpointer:
            await checkpointer.setup()
            # 单图主链路：prepare → agent → complete；支持 interrupt/resume
            app.state.workflow = build_workflow(checkpointer, settings)
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            yield
    finally:
        shutdown_langfuse()
        await async_engine.dispose()


def create_app() -> FastAPI:
    """注册路由：chat（SSE）、execution（手工执行 SQL）、admin 资产治理。"""
    app = FastAPI(
        title="SQL Genius API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(health.router, prefix="", tags=["health"])
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(execution.router, prefix="/api/v1", tags=["execution"])
    app.include_router(admin_datasources.router, prefix="/api/v1", tags=["admin"])
    app.include_router(admin_history.router, prefix="/api/v1", tags=["admin"])
    app.include_router(admin_learning.router, prefix="/api/v1", tags=["admin"])
    app.include_router(admin_skill_packs.router, prefix="/api/v1", tags=["admin"])
    return app


app = create_app()
