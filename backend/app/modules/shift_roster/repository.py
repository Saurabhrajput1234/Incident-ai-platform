"""
Shift Roster Repository — database operations only.
No business logic here.
"""
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select, delete, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.shift_roster.model import Engineer, ShiftRoster, ShiftRosterUpload, ShiftRosterHistory


class ShiftRosterRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # shift_roster_uploads
    # -------------------------------------------------------------------------

    async def create_upload(self, data: dict) -> ShiftRosterUpload:
        record = ShiftRosterUpload(id=str(uuid.uuid4()), **data)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update_upload(self, upload_id: str, data: dict) -> None:
        await self.db.execute(
            update(ShiftRosterUpload).where(ShiftRosterUpload.id == upload_id).values(**data)
        )
        await self.db.commit()

    async def get_uploads(self) -> list[ShiftRosterUpload]:
        result = await self.db.execute(
            select(ShiftRosterUpload).order_by(ShiftRosterUpload.uploaded_at.desc())
        )
        return result.scalars().all()

    # -------------------------------------------------------------------------
    # engineers  (upsert by email)
    # -------------------------------------------------------------------------

    async def get_engineer_by_email(self, email: str) -> Engineer | None:
        result = await self.db.execute(
            select(Engineer).where(Engineer.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_engineer_by_id(self, engineer_id: str) -> Engineer | None:
        result = await self.db.execute(
            select(Engineer).where(Engineer.id == engineer_id)
        )
        return result.scalar_one_or_none()

    async def create_engineer(self, data: dict) -> Engineer:
        engineer = Engineer(id=str(uuid.uuid4()), **data)
        self.db.add(engineer)
        await self.db.flush()  # get id without committing
        return engineer

    async def update_engineer(self, engineer_id: str, data: dict) -> Engineer | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(Engineer).where(Engineer.id == engineer_id).values(**data)
        )
        return await self.get_engineer_by_id(engineer_id)

    async def search_engineers(
        self,
        assignment_group: str | None = None,
        level: str | None = None,
        status: str | None = None,
        name: str | None = None,
        email: str | None = None,
    ) -> list[Engineer]:
        query = select(Engineer)
        if assignment_group:
            query = query.where(Engineer.assignment_group.ilike(f"%{assignment_group}%"))
        if level:
            query = query.where(Engineer.level == level)
        if status:
            query = query.where(Engineer.status == status)
        if name:
            query = query.where(Engineer.assigned_to.ilike(f"%{name}%"))
        if email:
            query = query.where(Engineer.email.ilike(f"%{email}%"))
        query = query.order_by(Engineer.assignment_group, Engineer.assigned_to)
        result = await self.db.execute(query)
        return result.scalars().all()

    # -------------------------------------------------------------------------
    # shift_roster (daily records)
    # -------------------------------------------------------------------------

    async def bulk_insert_roster(self, records: list[dict]) -> int:
        objects = [ShiftRoster(id=str(uuid.uuid4()), **r) for r in records]
        self.db.add_all(objects)
        await self.db.flush()
        return len(objects)

    async def delete_roster_by_date_range(self, engineer_id: str, start: date, end: date) -> int:
        """Delete existing roster records for an engineer within a date range."""
        result = await self.db.execute(
            delete(ShiftRoster).where(
                and_(
                    ShiftRoster.engineer_id == engineer_id,
                    ShiftRoster.roster_date >= start,
                    ShiftRoster.roster_date <= end,
                )
            )
        )
        return result.rowcount

    async def get_roster_by_engineer(
        self, engineer_id: str, start: date, end: date
    ) -> list[ShiftRoster]:
        result = await self.db.execute(
            select(ShiftRoster)
            .where(and_(
                ShiftRoster.engineer_id == engineer_id,
                ShiftRoster.roster_date >= start,
                ShiftRoster.roster_date <= end,
            ))
            .order_by(ShiftRoster.roster_date)
        )
        return result.scalars().all()

    async def get_roster_by_date(
        self,
        roster_date: date,
        assignment_group: str | None = None,
        shift_code: str | None = None,
        level: str | None = None,
    ) -> list[ShiftRoster]:
        """Get all roster records for a specific date — used by Triage Agent."""
        query = (
            select(ShiftRoster)
            .join(Engineer, ShiftRoster.engineer_id == Engineer.id)
            .where(ShiftRoster.roster_date == roster_date)
        )
        if assignment_group:
            query = query.where(Engineer.assignment_group.ilike(f"%{assignment_group}%"))
        if shift_code:
            query = query.where(ShiftRoster.shift_code == shift_code)
        if level:
            query = query.where(Engineer.level == level)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def search_engineers_with_shift(
        self,
        roster_date: date,
        assignment_group: str | None = None,
        level: str | None = None,
        name: str | None = None,
        email: str | None = None,
        status: str | None = None,
        shift_code: str | None = None,
    ) -> list[tuple]:
        """Search engineers joined with their shift on a given date."""
        query = (
            select(Engineer, ShiftRoster)
            .join(ShiftRoster, ShiftRoster.engineer_id == Engineer.id)
            .where(ShiftRoster.roster_date == roster_date)
        )
        if assignment_group:
            query = query.where(Engineer.assignment_group.ilike(f"%{assignment_group}%"))
        if level:
            query = query.where(Engineer.level == level)
        if name:
            query = query.where(Engineer.assigned_to.ilike(f"%{name}%"))
        if email:
            query = query.where(Engineer.email.ilike(f"%{email}%"))
        if status:
            query = query.where(Engineer.status == status)
        if shift_code:
            query = query.where(ShiftRoster.shift_code == shift_code)
        query = query.order_by(Engineer.assignment_group, Engineer.assigned_to)
        result = await self.db.execute(query)
        return result.all()

    async def get_roster_entry_by_id(self, roster_id: str) -> ShiftRoster | None:
        result = await self.db.execute(
            select(ShiftRoster).where(ShiftRoster.id == roster_id)
        )
        return result.scalar_one_or_none()

    async def update_roster_entry(self, roster_id: str, shift_code: str) -> None:
        await self.db.execute(
            update(ShiftRoster)
            .where(ShiftRoster.id == roster_id)
            .values(shift_code=shift_code, updated_at=datetime.now(timezone.utc))
        )

    # -------------------------------------------------------------------------
    # shift_roster_history
    # -------------------------------------------------------------------------

    async def create_history(self, data: dict) -> ShiftRosterHistory:
        record = ShiftRosterHistory(id=str(uuid.uuid4()), **data)
        self.db.add(record)
        return record

    async def get_history_by_engineer(self, engineer_id: str) -> list[ShiftRosterHistory]:
        result = await self.db.execute(
            select(ShiftRosterHistory)
            .where(ShiftRosterHistory.engineer_id == engineer_id)
            .order_by(ShiftRosterHistory.changed_at.desc())
        )
        return result.scalars().all()

    async def commit(self) -> None:
        await self.db.commit()
