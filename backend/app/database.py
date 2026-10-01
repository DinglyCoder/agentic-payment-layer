from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings
from .models import Base

settings = get_settings()
engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        existing = await connection.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("payments")}
        )
        additions = {
            "risk_signals": "JSON NOT NULL DEFAULT '[]'",
            "policy_version": "VARCHAR(32)",
            "resolution_attempts": "INTEGER NOT NULL DEFAULT 0",
            "next_resolution_attempt_at": "DATETIME",
            "resolution_error": "VARCHAR(240)",
        }
        for name, definition in additions.items():
            if name not in existing:
                statement = f"ALTER TABLE payments ADD COLUMN {name} {definition}"
                await connection.execute(text(statement))


async def close_database() -> None:
    await engine.dispose()
