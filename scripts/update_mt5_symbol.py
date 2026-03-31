import sys
from pathlib import Path
import asyncio

from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import AsyncSessionLocal, init_db
from core.models import Account


async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Account)
            .where(Account.broker_type == "mt5")
            .values(symbol="XAUUSD.s")
        )
        await session.commit()

        rows = await session.execute(
            select(Account.id, Account.name, Account.broker_type, Account.symbol)
        )
        for row in rows.all():
            print(row)


if __name__ == "__main__":
    asyncio.run(main())

