"""Quick DB check — run from backend/ with venv activated."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from app.core.config import settings


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        print("=== Assignment Groups in engineers table ===")
        r = await db.execute(text("SELECT DISTINCT assignment_group FROM engineers ORDER BY 1"))
        for row in r.fetchall():
            print(" ", repr(row[0]))

        print("\n=== shift_roster row count ===")
        r = await db.execute(text("SELECT COUNT(*) FROM shift_roster"))
        print(" ", r.scalar())

        print("\n=== Sample roster rows ===")
        r = await db.execute(text(
            "SELECT e.assigned_to, e.assignment_group, sr.shift_code, sr.roster_date "
            "FROM shift_roster sr JOIN engineers e ON sr.engineer_id = e.id LIMIT 5"
        ))
        for row in r.fetchall():
            print(" ", row)

        print("\n=== Today's roster ===")
        r = await db.execute(text(
            "SELECT e.assigned_to, e.assignment_group, sr.shift_code "
            "FROM shift_roster sr JOIN engineers e ON sr.engineer_id = e.id "
            "WHERE sr.roster_date = CURRENT_DATE LIMIT 10"
        ))
        rows = r.fetchall()
        if rows:
            for row in rows:
                print(" ", row)
        else:
            print("  NO ROWS FOR TODAY — roster may be for a different month")

    await engine.dispose()


asyncio.run(main())
