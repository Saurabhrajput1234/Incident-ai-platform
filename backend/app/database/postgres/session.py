"""
Database session management.

Creates a single async SQLAlchemy engine and session factory
that are reused across the application lifetime.

get_db() is a FastAPI dependency — inject it into route handlers
or service constructors to get a request-scoped AsyncSession.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Shared async engine — one per application process
# echo=DEBUG prints all SQL to stdout in development
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

# Session factory — creates new AsyncSession instances
# expire_on_commit=False keeps objects accessible after commit
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db():
    """
    FastAPI dependency that yields a database session per request.
    Session is automatically closed when the request completes.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
