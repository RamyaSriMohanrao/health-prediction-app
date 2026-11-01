"""Pydantic request model and every validation rule for patient data."""

import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

FIELD_LABELS = {
    "full_name": "Full name",
    "dob": "Date of birth",
    "email": "Email",
    "glucose": "Glucose",
    "haemoglobin": "Haemoglobin",
    "cholesterol": "Cholesterol",
}

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 100
NAME_ALLOWED_SYMBOLS = " '-."

# Two-digit day, two-digit month, four-digit year. "\2" repeats the first separator,
# so 15/01/2000 and 15.01.2000 match but a mixed 15/01.2000 does not.
DOB_PATTERN = re.compile(r"(\d{2})([/.])(\d{2})\2(\d{4})")
MAX_AGE_YEARS = 120

# local part, "@", one or more domain labels joined by dots, then a letters-only ending (.com, .co.uk).
EMAIL_PATTERN = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}")

# Upper bound and unit for each blood value.
BLOOD_LIMITS = {
    "glucose": (1000, "mg/dL"),
    "haemoglobin": (25, "g/dL"),
    "cholesterol": (1000, "mg/dL"),
}


def _error(field: str, message: str) -> PydanticCustomError:
    # A plain ValueError would show as "Value error, <message>"; this keeps the message exactly as written.
    return PydanticCustomError(f"{field}_invalid", message)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_number(value: Any) -> float | None:
    """Return the value as a finite float, or None if it is not a number."""
    # bool is a subclass of int, so True would otherwise be accepted as 1.
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    # float() accepts "nan" and "inf", which are not real measurements.
    return number if math.isfinite(number) else None


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        # 29 February does not exist in the target year, so use 28 February.
        return day.replace(year=day.year - years, day=28)


class PatientInput(BaseModel):
    """The fields a client sends to create or update a patient."""

    full_name: str
    dob: date
    email: str
    glucose: float
    haemoglobin: float
    cholesterol: float

    @field_validator("full_name", mode="before")
    @classmethod
    def check_full_name(cls, value: Any) -> str:
        if _is_blank(value):
            raise _error("full_name", "Full name is required.")
        if not isinstance(value, str):
            raise _error("full_name", "Full name must be text.")
        name = value.strip()
        if not NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH:
            raise _error(
                "full_name",
                f"Full name must be between {NAME_MIN_LENGTH} and {NAME_MAX_LENGTH} characters.",
            )
        if not all(char.isalpha() or char in NAME_ALLOWED_SYMBOLS for char in name):
            raise _error(
                "full_name",
                "Full name can only contain letters, spaces, apostrophes, hyphens and dots.",
            )
        if not any(char.isalpha() for char in name):
            raise _error("full_name", "Full name must contain at least one letter.")
        return name

    @field_validator("dob", mode="before")
    @classmethod
    def check_dob(cls, value: Any) -> date:
        if _is_blank(value):
            raise _error("dob", "Date of birth is required.")
        if not isinstance(value, str):
            raise _error("dob", "Date of birth must be text in dd/mm/yyyy format.")
        match = DOB_PATTERN.fullmatch(value.strip())
        if match is None:
            raise _error("dob", "Date of birth must be in dd/mm/yyyy or dd.mm.yyyy format.")
        day, _separator, month, year = match.groups()
        try:
            dob = date(int(year), int(month), int(day))
        except ValueError:
            raise _error("dob", "Date of birth is not a real calendar date.")
        today = date.today()
        if dob > today:
            raise _error("dob", "Date of birth cannot be in the future.")
        if dob < _years_before(today, MAX_AGE_YEARS):
            raise _error("dob", f"Date of birth cannot be more than {MAX_AGE_YEARS} years ago.")
        return dob

    @field_validator("email", mode="before")
    @classmethod
    def check_email(cls, value: Any) -> str:
        if _is_blank(value):
            raise _error("email", "Email is required.")
        if not isinstance(value, str):
            raise _error("email", "Email must be text.")
        email = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise _error(
                "email",
                "Email must be a valid address with an @ and a domain ending such as .com.",
            )
        return email

    @field_validator("glucose", "haemoglobin", "cholesterol", mode="before")
    @classmethod
    def check_blood_value(cls, value: Any, info: ValidationInfo) -> float:
        field = info.field_name
        label = FIELD_LABELS[field]
        upper_bound, unit = BLOOD_LIMITS[field]
        if _is_blank(value):
            raise _error(field, f"{label} is required.")
        number = _to_number(value)
        if number is None:
            raise _error(field, f"{label} must be a number.")
        if number <= 0:
            raise _error(field, f"{label} must be greater than 0.")
        if number > upper_bound:
            raise _error(field, f"{label} must be {upper_bound} {unit} or less.")
        return number


class PatientOut(BaseModel):
    """A saved patient as returned by the API, with the date of birth shown as dd/mm/yyyy."""

    id: int
    full_name: str
    dob: str
    email: str
    glucose: float
    haemoglobin: float
    cholesterol: float
    remarks: str | None
    created_at: str | None


def format_dob(iso_dob: str) -> str:
    """Turn a stored ISO date (YYYY-MM-DD) into the display format dd/mm/yyyy."""
    return date.fromisoformat(iso_dob).strftime("%d/%m/%Y")


def format_errors(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Turn Pydantic error details into the [{field, message}] list the frontend shows."""
    formatted = []
    for error in errors:
        location = error.get("loc", ())
        # FastAPI prefixes the location with "body", so the field name is the last part.
        field = str(location[-1]) if location else "body"
        if error["type"] == "missing":
            message = f"{FIELD_LABELS.get(field, field)} is required."
        else:
            message = error["msg"]
        formatted.append({"field": field, "message": message})
    return formatted
