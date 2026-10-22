"""ORM models (import side effects register metadata with Alembic)."""

from app.db.models.admin_session import AdminSession
from app.db.models.datasource import Datasource
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.learning_signal import LearningSignal
from app.db.models.onboarding_run import OnboardingRun
from app.db.models.sql_execution_history import SqlExecutionHistory
from app.db.models.skill_document import SkillDocument
from app.db.models.skill_pack import SkillPack
from app.db.models.thread_context_summary import ThreadContextSummary
from app.db.models.thread_conversation_turn import ThreadConversationTurn
from app.db.models.schema_comments import apply_schema_comments
from app.db.base import Base

apply_schema_comments(Base.metadata)

__all__ = [
    "AdminSession",
    "Datasource",
    "DatasourceMemoryDocument",
    "DatasourceProfile",
    "DatasourceQaExample",
    "DatasourceSchemaSnapshot",
    "LearningSignal",
    "OnboardingRun",
    "SkillDocument",
    "SkillPack",
    "SqlExecutionHistory",
    "ThreadContextSummary",
    "ThreadConversationTurn",
]
