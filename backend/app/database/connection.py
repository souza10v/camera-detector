from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,   # descarta conexões stale automaticamente
    pool_recycle=300,     # recicla conexões a cada 5 min
    pool_size=5,
    max_overflow=10,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Lightweight column migrations — ADD COLUMN IF NOT EXISTS is idempotent
_MIGRATIONS = [
    """
    ALTER TABLE face_detections
        ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'upload'
    """,
    """
    ALTER TABLE face_detections
        ALTER COLUMN reading_id DROP NOT NULL
    """,
    # Permite file_type = 'stream' (antes só aceitava 'image' | 'video')
    """
    ALTER TABLE plate_readings
        ALTER COLUMN file_type TYPE VARCHAR(20)
    """,
]


async def create_tables():
    async with engine.begin() as conn:
        from app.models import reading, face  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        # Apply incremental column migrations on existing tables
        for migration in _MIGRATIONS:
            try:
                await conn.execute(text(migration))
            except Exception:
                pass  # column/constraint already in desired state
