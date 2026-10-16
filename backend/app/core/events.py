from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.config import settings
from app.models.base import Base
from app.models import iteration  # noqa: F401 — ensure iteration KB tables loaded
from app.models import knowledge_card  # noqa: F401 — knowledge cards + skills clusters
from app.models import survey  # noqa: F401 — all survey models loaded
from app.models import user  # noqa: F401 — UserAccount table loaded
from app.models import analytics  # noqa: F401 — analytics events table loaded

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start services after the schema has been prepared explicitly.

    Alembic owns shared/production schema changes. AUTO_CREATE_SCHEMA is a
    deliberate local-development escape hatch and does not run ALTER statements
    that can hide migration drift.
    """
    from app.core.database import async_session_factory, engine

    if settings.auto_create_schema:
        logger.warning(
            "AUTO_CREATE_SCHEMA is enabled; use Alembic for shared or production databases"
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        logger.info("Automatic schema creation disabled; expecting `alembic upgrade head`")

    # Seed iteration knowledge base (idempotent).
    try:
        from app.services.iteration_kb import seed_dashscope_debugging

        async with async_session_factory() as db:
            await seed_dashscope_debugging(db)
    except Exception:
        logger.warning("Failed to seed iteration KB (this is non-fatal)", exc_info=True)

    # Seed knowledge cards + skills clusters on startup (idempotent).
    try:
        from app.services.knowledge_ingestion import ingest_all as seed_knowledge

        async with async_session_factory() as db:
            result = await seed_knowledge(db)
            logger.info("Knowledge cards seeded: %s", result)
    except Exception:
        logger.warning("Failed to seed knowledge cards (non-fatal)", exc_info=True)

    yield
    await engine.dispose()
