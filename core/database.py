"""
ClubMillies — Database setup.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import settings
from core.models import Base

# Async engine for the app
async_engine = create_async_engine(settings.db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for migrations/init
sync_engine = create_engine(settings.db_sync_url, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine)


async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def init_db_sync():
    Base.metadata.create_all(bind=sync_engine)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
