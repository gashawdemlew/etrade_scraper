import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import Table, Column, String, JSON, TIMESTAMP, MetaData, func, select
from sqlalchemy.orm import sessionmaker

from .config import settings

logger = logging.getLogger("db")

# Use DATABASE_URL from central config
DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
metadata = MetaData()

scraped_table = Table(
    "scraped_tins",
    metadata,
    Column("tin", String, primary_key=True),
    Column("data", JSON),
    Column("updated_at", TIMESTAMP, server_default=func.now(), onupdate=func.now()),
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    logger.info("Database initialized")


async def get_scraped_tin(tin: str):
    """Return stored data for a tin or None."""
    async with AsyncSessionLocal() as session:
        stmt = select(scraped_table.c.data).where(scraped_table.c.tin == tin)
        res = await session.execute(stmt)
        row = res.scalar_one_or_none()
        if row is not None:
            return {"tin": tin, "data": row}
        return None


async def upsert_scraped_tin(tin: str, data):
    """Insert or update scraped data for a tin."""
    async with AsyncSessionLocal() as session:
        stmt = select(scraped_table.c.tin).where(scraped_table.c.tin == tin)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            await session.execute(
                scraped_table.update().where(scraped_table.c.tin == tin).values(data=data, updated_at=func.now())
            )
        else:
            await session.execute(scraped_table.insert().values(tin=tin, data=data))
        await session.commit()
