"""
Shift Roster Service — business logic layer.

Import flow:
  1. Parse file (Excel or CSV)
  2. For each engineer row: upsert into engineers table
  3. Delete existing roster records for same date range
  4. Bulk insert daily shift records into shift_roster
  5. Create upload summary in shift_roster_uploads
"""
import logging
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.shift_roster.parser import parse_excel, parse_csv, ParsedRoster
from app.modules.shift_roster.repository import ShiftRosterRepository
from app.modules.shift_roster.schemas import (
    UploadSummary, EngineerResponse, ShiftRosterResponse,
    EngineerAvailability, RosterHistoryResponse, ShiftRosterUpdate
)
from app.modules.shift_roster.enums import UploadStatus, EngineerStatus, SHIFT_DEFINITIONS
from app.common.exceptions.base import NotFoundError, BadRequestError

logger = logging.getLogger(__name__)

VALID_SHIFT_CODES = set(SHIFT_DEFINITIONS.keys())


class ShiftRosterService:

    def __init__(self, db: AsyncSession):
        self.repo = ShiftRosterRepository(db)

    async def upload_roster(self, file_bytes: bytes, filename: str, uploaded_by: str | None = None) -> UploadSummary:
        """Parse, validate and import an Excel or CSV roster file."""
        logger.info(f"Processing roster upload: {filename}")

        # Detect file type and parse
        if filename.endswith(".xlsx"):
            try:
                parsed: ParsedRoster = parse_excel(file_bytes)
            except ValueError as e:
                raise BadRequestError(str(e))
        elif filename.endswith(".csv"):
            try:
                parsed: ParsedRoster = parse_csv(file_bytes)
            except ValueError as e:
                raise BadRequestError(str(e))
        else:
            raise BadRequestError("Only .xlsx and .csv files are supported")

        if not parsed.rows:
            raise BadRequestError("No valid engineer rows found in file")

        # Create upload metadata record
        upload = await self.repo.create_upload({
            "file_name": filename,
            "roster_start_date": parsed.roster_start_date,
            "roster_end_date": parsed.roster_end_date,
            "uploaded_by": uploaded_by,
            "total_records": len(parsed.rows),
            "imported_records": 0,
            "failed_records": len(parsed.errors),
            "upload_status": UploadStatus.SUCCESS,
        })

        imported = 0
        failed = len(parsed.errors)
        errors = list(parsed.errors)

        for row in parsed.rows:
            try:
                # Upsert by (email, assignment_group) — an engineer can belong to
                # multiple groups; each (email, group) pair is a distinct record
                existing = await self.repo.get_engineer_by_email_and_group(row.email, row.assignment_group)
                if existing:
                    await self.repo.update_engineer(existing.id, {
                        "assigned_to": row.assigned_to,
                        "default_shift": row.default_shift,
                        "level": row.level,
                        "status": EngineerStatus.ACTIVE,
                    })
                    engineer_id = existing.id
                else:
                    engineer = await self.repo.create_engineer({
                        "assignment_group": row.assignment_group,
                        "assigned_to": row.assigned_to,
                        "email": row.email,
                        "default_shift": row.default_shift,
                        "level": row.level,
                        "status": EngineerStatus.ACTIVE,
                    })
                    engineer_id = engineer.id

                # Replace only this engineer+group's roster for this date range
                await self.repo.delete_roster_by_date_range(
                    engineer_id,
                    parsed.roster_start_date,
                    parsed.roster_end_date,
                )

                # Insert daily records — skip invalid shift codes
                daily_records = []
                for roster_date, shift_code in row.daily_shifts.items():
                    if shift_code not in VALID_SHIFT_CODES:
                        errors.append(f"{row.assigned_to} on {roster_date}: invalid shift '{shift_code}' — skipped")
                        failed += 1
                        continue
                    daily_records.append({
                        "upload_id": upload.id,
                        "engineer_id": engineer_id,
                        "roster_date": roster_date,
                        "shift_code": shift_code,
                    })

                if daily_records:
                    await self.repo.bulk_insert_roster(daily_records)

                imported += 1

            except Exception as e:
                logger.error(f"Failed to import row for {row.assigned_to}: {e}")
                errors.append(f"{row.assigned_to}: {str(e)}")
                failed += 1

        # Determine final status
        status = UploadStatus.SUCCESS
        if imported == 0:
            status = UploadStatus.FAILED
        elif failed > 0:
            status = UploadStatus.PARTIAL

        await self.repo.commit()

        # Update upload summary
        await self.repo.update_upload(upload.id, {
            "imported_records": imported,
            "failed_records": failed,
            "upload_status": status,
        })

        logger.info(f"Upload complete: {imported} imported, {failed} failed")

        return UploadSummary(
            upload_id=upload.id,
            file_name=filename,
            roster_start_date=parsed.roster_start_date,
            roster_end_date=parsed.roster_end_date,
            total_records=len(parsed.rows),
            imported_records=imported,
            failed_records=failed,
            upload_status=status,
            errors=errors,
        )

    async def search_engineers(
        self,
        assignment_group: str | None = None,
        level: str | None = None,
        name: str | None = None,
        email: str | None = None,
        status: str | None = "active",
        roster_date: date | None = None,
        shift_code: str | None = None,
    ) -> list[EngineerAvailability]:
        """
        Search engineers with optional filters.
        If roster_date provided, includes each engineer's shift on that date.
        """
        if roster_date:
            rows = await self.repo.search_engineers_with_shift(
                roster_date=roster_date,
                assignment_group=assignment_group,
                level=level,
                name=name,
                email=email,
                status=status,
                shift_code=shift_code,
            )
            return [
                EngineerAvailability(
                    engineer_id=eng.id,
                    assigned_to=eng.assigned_to,
                    email=eng.email,
                    assignment_group=eng.assignment_group,
                    level=eng.level,
                    default_shift=eng.default_shift,
                    roster_date=roster.roster_date,
                    shift_code=roster.shift_code,
                )
                for eng, roster in rows
            ]

        # No date — return engineers without shift info
        engineers = await self.repo.search_engineers(
            assignment_group=assignment_group,
            level=level,
            status=status,
            name=name,
            email=email,
        )
        return [
            EngineerAvailability(
                engineer_id=eng.id,
                assigned_to=eng.assigned_to,
                email=eng.email,
                assignment_group=eng.assignment_group,
                level=eng.level,
                default_shift=eng.default_shift,
            )
            for eng in engineers
        ]

    async def get_engineers(
        self,
        assignment_group: str | None = None,
        level: str | None = None,
        name: str | None = None,
        email: str | None = None,
        status: str | None = "active",
    ) -> list[EngineerResponse]:
        engineers = await self.repo.search_engineers(
            assignment_group=assignment_group,
            level=level,
            status=status,
            name=name,
            email=email,
        )
        return [EngineerResponse.model_validate(e) for e in engineers]

    async def get_engineers_by_email(self, email: str, assignment_group: str | None = None) -> list[EngineerResponse]:
        """Return all engineer records for an email, optionally filtered by group."""
        engineers = await self.repo.get_engineers_by_email(email, assignment_group)
        if not engineers:
            raise NotFoundError(f"Engineer with email '{email}' not found")
        return [EngineerResponse.model_validate(e) for e in engineers]

    async def get_engineer(self, email: str) -> EngineerResponse:
        """Return first engineer record for email (backwards compat)."""
        engineer = await self.repo.get_engineer_by_email(email)
        if not engineer:
            raise NotFoundError(f"Engineer with email '{email}' not found")
        return EngineerResponse.model_validate(engineer)

    async def update_engineer(self, email: str, assignment_group: str, payload) -> EngineerResponse:
        existing = await self.repo.get_engineer_by_email_and_group(email, assignment_group)
        if not existing:
            raise NotFoundError(f"Engineer '{email}' in group '{assignment_group}' not found")
        updated = await self.repo.update_engineer(existing.id, payload.model_dump(exclude_none=True))
        await self.repo.commit()
        return EngineerResponse.model_validate(updated)

    async def delete_engineer(self, email: str, assignment_group: str | None = None) -> None:
        """Mark engineer(s) as inactive. If group given, only that record; else all records for email."""
        engineers = await self.repo.get_engineers_by_email(email, assignment_group)
        if not engineers:
            raise NotFoundError(f"Engineer with email '{email}' not found")
        for eng in engineers:
            await self.repo.update_engineer(eng.id, {"status": EngineerStatus.INACTIVE})
        await self.repo.commit()
        logger.info(f"Engineer(s) marked inactive: {email} (group={assignment_group or 'all'})")

    async def get_available_engineers(
        self,
        roster_date: date,
        shift_code: str | None = None,
        assignment_group: str | None = None,
        level: str | None = None,
    ) -> list[EngineerAvailability]:
        """
        Primary Triage Agent query:
        Returns engineers and their shift on a given date.
        """
        records = await self.repo.get_roster_by_date(
            roster_date=roster_date,
            assignment_group=assignment_group,
            shift_code=shift_code,
            level=level,
        )

        result = []
        for r in records:
            eng = await self.repo.get_engineer_by_id(r.engineer_id)
            if eng and eng.status == EngineerStatus.ACTIVE:
                result.append(EngineerAvailability(
                    engineer_id=eng.id,
                    assigned_to=eng.assigned_to,
                    email=eng.email,
                    assignment_group=eng.assignment_group,
                    level=eng.level,
                    default_shift=eng.default_shift,
                    roster_date=r.roster_date,
                    shift_code=r.shift_code,
                ))
        return result

    async def get_engineer_roster(
        self, email: str, start: date, end: date, assignment_group: str | None = None
    ) -> list[ShiftRosterResponse]:
        engineers = await self.repo.get_engineers_by_email(email, assignment_group)
        if not engineers:
            raise NotFoundError(f"Engineer with email '{email}' not found")
        records = []
        for eng in engineers:
            records.extend(await self.repo.get_roster_by_engineer(eng.id, start, end))
        return [ShiftRosterResponse.model_validate(r) for r in records]

    async def get_engineer_change_history(self, email: str, assignment_group: str | None = None) -> list[RosterHistoryResponse]:
        engineers = await self.repo.get_engineers_by_email(email, assignment_group)
        if not engineers:
            raise NotFoundError(f"Engineer with email '{email}' not found")
        records = []
        for eng in engineers:
            records.extend(await self.repo.get_history_by_engineer(eng.id))
        return [RosterHistoryResponse.model_validate(r) for r in records]

    async def update_roster_entry(
        self, roster_id: str, payload: ShiftRosterUpdate
    ) -> ShiftRosterResponse:
        """Update a single daily roster entry and record in history."""
        entry = await self.repo.get_roster_entry_by_id(roster_id)
        if not entry:
            raise NotFoundError(f"Roster entry '{roster_id}' not found")

        # Record history before changing
        await self.repo.create_history({
            "roster_id": roster_id,
            "engineer_id": entry.engineer_id,
            "roster_date": entry.roster_date,
            "previous_shift": entry.shift_code,
            "new_shift": payload.shift_code,
            "changed_by": payload.changed_by,
            "reason": payload.reason,
        })

        await self.repo.update_roster_entry(roster_id, payload.shift_code)
        await self.repo.commit()

        updated = await self.repo.get_roster_entry_by_id(roster_id)
        return ShiftRosterResponse.model_validate(updated)

    async def get_upload_history(self):
        return await self.repo.get_uploads()
