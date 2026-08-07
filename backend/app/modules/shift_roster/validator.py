"""
Shift Roster Validation Engine.

Validates parsed roster data before any database operations.
Returns a detailed ValidationReport with all errors and warnings.
"""
import re
from app.modules.shift_roster.enums import ShiftType, EngineerLevel
from app.modules.shift_roster.schemas import ValidationReport

# Columns that must exist in the uploaded file
REQUIRED_COLUMNS = {"engineer_name", "email", "assignment_group", "roster_date", "shift"}

VALID_SHIFTS = {s.value for s in ShiftType}
VALID_LEVELS = {l.value for l in EngineerLevel}
EMAIL_PATTERN = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")


def validate_roster_data(rows: list[dict]) -> ValidationReport:
    """
    Validate a list of parsed roster rows.

    Checks:
    - Required columns present
    - No empty engineer name or email
    - Valid email format
    - Valid shift values
    - Valid level values (if provided)
    - Duplicate email + date combinations
    - Empty rows skipped with warning

    Returns a ValidationReport with is_valid flag, error list, and row counts.
    """
    errors: list[str] = []
    warnings: list[str] = []
    valid_rows = 0
    seen: set[tuple] = set()  # (email, roster_date) uniqueness check

    if not rows:
        return ValidationReport(
            is_valid=False,
            total_rows=0,
            valid_rows=0,
            errors=["File is empty or contains no data rows."],
            warnings=[],
        )

    # Check required columns using the first row
    first_row_keys = {k.lower().strip() for k in rows[0].keys()}
    missing_cols = REQUIRED_COLUMNS - first_row_keys
    if missing_cols:
        return ValidationReport(
            is_valid=False,
            total_rows=len(rows),
            valid_rows=0,
            errors=[f"Missing required columns: {', '.join(sorted(missing_cols))}"],
            warnings=[],
        )

    for i, row in enumerate(rows, start=2):  # row 1 is header
        row_errors = []

        engineer_name = str(row.get("engineer_name") or "").strip()
        email = str(row.get("email") or "").strip()
        assignment_group = str(row.get("assignment_group") or "").strip()
        shift = str(row.get("shift") or "").strip().lower()
        roster_date = row.get("roster_date")
        level = str(row.get("level") or "").strip().lower()

        # Skip entirely empty rows
        if not any([engineer_name, email, assignment_group, shift]):
            warnings.append(f"Row {i}: Empty row skipped.")
            continue

        if not engineer_name:
            row_errors.append(f"Row {i}: Missing engineer_name.")
        if not email:
            row_errors.append(f"Row {i}: Missing email.")
        elif not EMAIL_PATTERN.match(email):
            row_errors.append(f"Row {i}: Invalid email format '{email}'.")
        if not assignment_group:
            row_errors.append(f"Row {i}: Missing assignment_group.")
        if not roster_date:
            row_errors.append(f"Row {i}: Missing roster_date.")
        if not shift:
            row_errors.append(f"Row {i}: Missing shift.")
        elif shift not in VALID_SHIFTS:
            row_errors.append(f"Row {i}: Invalid shift '{shift}'. Valid: {', '.join(VALID_SHIFTS)}.")
        if level and level not in VALID_LEVELS:
            row_errors.append(f"Row {i}: Invalid level '{level}'. Valid: {', '.join(VALID_LEVELS)}.")

        # Duplicate check per email + date
        if email and roster_date:
            key = (email.lower(), str(roster_date))
            if key in seen:
                row_errors.append(f"Row {i}: Duplicate entry for '{email}' on {roster_date}.")
            else:
                seen.add(key)

        if row_errors:
            errors.extend(row_errors)
        else:
            valid_rows += 1

    return ValidationReport(
        is_valid=len(errors) == 0,
        total_rows=len(rows),
        valid_rows=valid_rows,
        errors=errors,
        warnings=warnings,
    )
