"""
ClubMillies — Database setup.
"""
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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
    ensure_schema_sync()


def init_db_sync():
    Base.metadata.create_all(bind=sync_engine)


def ensure_schema_sync():
    """SQLite-only lightweight migrations for existing DB files."""
    url = str(sync_engine.url)
    if "sqlite" not in url:
        return
    insp = inspect(sync_engine)

    def _cols(table: str) -> set[str]:
        try:
            return {c["name"] for c in insp.get_columns(table)}
        except Exception:
            return set()

    alters: list[str] = []
    tcols = _cols("trades")
    if tcols and "mt5_position_ticket" not in tcols:
        alters.append("ALTER TABLE trades ADD COLUMN mt5_position_ticket INTEGER")
    acols = _cols("accounts")
    if acols:
        if "starting_balance" not in acols:
            alters.append("ALTER TABLE accounts ADD COLUMN starting_balance FLOAT")
        if "is_demo" not in acols:
            alters.append("ALTER TABLE accounts ADD COLUMN is_demo BOOLEAN")
    aicols = _cols("ai_analyses")
    if aicols:
        if "account_id" not in aicols:
            alters.append("ALTER TABLE ai_analyses ADD COLUMN account_id INTEGER")
        if "trade_id" not in aicols:
            alters.append("ALTER TABLE ai_analyses ADD COLUMN trade_id INTEGER")
        if "metrics" not in aicols:
            alters.append("ALTER TABLE ai_analyses ADD COLUMN metrics TEXT")
    twcols = _cols("tweets")
    if twcols:
        if "ai_direction" not in twcols:
            alters.append("ALTER TABLE tweets ADD COLUMN ai_direction TEXT")
        if "ai_confidence" not in twcols:
            alters.append("ALTER TABLE tweets ADD COLUMN ai_confidence INTEGER")
        if "ai_reasoning" not in twcols:
            alters.append("ALTER TABLE tweets ADD COLUMN ai_reasoning TEXT")

    if not alters:
        return
    with sync_engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))
        if any("starting_balance" in a for a in alters):
            conn.execute(
                text(
                    "UPDATE accounts SET starting_balance = balance "
                    "WHERE starting_balance IS NULL OR starting_balance = 0"
                )
            )


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
