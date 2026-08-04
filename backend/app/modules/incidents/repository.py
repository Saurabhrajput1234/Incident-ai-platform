"""
Incident Repository — database access layer.

This class is the ONLY place SQL queries live.
No business logic, no validation, no HTTP concerns here.

To replace PostgreSQL with ServiceNow in the future,
create a ServiceNowIncidentRepository with the same method
signatures and swap it out via dependency injection.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.incidents.model import Incident


class IncidentRepository:
    """
    Data access layer for the incidents table.
    All methods are async and return SQLAlchemy model instances.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _generate_incident_number(self) -> str:
        """
        Generate next sequential incident number.
        Format: INC0000001, INC0000002, ...
        NOTE: Not race-condition safe under high concurrency.
        Replace with a DB sequence in production if needed.
        """
        result = await self.db.execute(select(func.count()).select_from(Incident))
        count = result.scalar() or 0
        return f"INC{str(count + 1).zfill(7)}"

    async def create(self, data: dict) -> Incident:
        """Insert a new incident record and return the persisted instance."""
        incident = Incident(
            id=str(uuid.uuid4()),
            incident_number=await self._generate_incident_number(),
            **data
        )
        self.db.add(incident)
        await self.db.commit()
        await self.db.refresh(incident)  # reload from DB to get defaults
        return incident

    async def get_by_id(self, incident_id: str) -> Incident | None:
        """Fetch a single incident by primary key. Returns None if not found."""
        result = await self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def get_by_number(self, incident_number: str) -> Incident | None:
        """Fetch a single incident by incident number (e.g. INC0000001)."""
        result = await self.db.execute(
            select(Incident).where(Incident.incident_number == incident_number)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        offset: int = 0,
        limit: int = 20,
        priority: str | None = None,
        state: str | None = None,
        category: str | None = None,
        assignment_group: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Incident], int]:
        """
        Fetch a paginated, optionally filtered and sorted list of incidents.
        Returns a tuple of (records, total_count).
        total_count reflects the full filtered set, not just the page.
        """
        query = select(Incident)
        count_query = select(func.count()).select_from(Incident)

        # Build filter conditions dynamically
        filters = []
        if priority:
            filters.append(Incident.priority == priority)
        if state:
            filters.append(Incident.state == state)
        if category:
            filters.append(Incident.category == category)
        if assignment_group:
            filters.append(Incident.assignment_group == assignment_group)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        # Fallback to created_at if sort_by column doesn't exist on the model
        sort_col = getattr(Incident, sort_by, Incident.created_at)
        query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

        # Apply pagination
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        count_result = await self.db.execute(count_query)

        return result.scalars().all(), count_result.scalar()

    async def update(self, incident_id: str, data: dict) -> Incident | None:
        """
        Update an incident by id with provided fields.
        Always sets updated_at to current UTC time.
        Returns the updated instance, or None if not found.
        """
        data["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(Incident).where(Incident.id == incident_id).values(**data)
        )
        await self.db.commit()
        return await self.get_by_id(incident_id)

    async def delete(self, incident_id: str) -> bool:
        """
        Delete an incident by id.
        Returns True if a row was deleted, False otherwise.
        """
        result = await self.db.execute(
            delete(Incident).where(Incident.id == incident_id)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def search(
        self,
        query: str,
        offset: int = 0,
        limit: int = 20,
        priority: str | None = None,
        state: str | None = None,
        category: str | None = None,
        assignment_group: str | None = None,
    ) -> tuple[list[Incident], int]:
        """
        Case-insensitive keyword search across incident_number,
        short_description, description, caller, and assigned_to.
        Supports additional filtering on top of the keyword match.
        Returns (records, total_count).
        """
        # Match across all searchable text fields
        search_filter = or_(
            Incident.incident_number.ilike(f"%{query}%"),
            Incident.short_description.ilike(f"%{query}%"),
            Incident.description.ilike(f"%{query}%"),
            Incident.caller.ilike(f"%{query}%"),
            Incident.assigned_to.ilike(f"%{query}%"),
        )

        base_query = select(Incident).where(search_filter)
        count_query = select(func.count()).select_from(Incident).where(search_filter)

        # Optional additional filters narrowing search results
        filters = []
        if priority:
            filters.append(Incident.priority == priority)
        if state:
            filters.append(Incident.state == state)
        if category:
            filters.append(Incident.category == category)
        if assignment_group:
            filters.append(Incident.assignment_group == assignment_group)

        if filters:
            base_query = base_query.where(*filters)
            count_query = count_query.where(*filters)

        base_query = base_query.order_by(Incident.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(base_query)
        count_result = await self.db.execute(count_query)

        return result.scalars().all(), count_result.scalar()
