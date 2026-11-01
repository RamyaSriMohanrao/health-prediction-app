"""SQLite storage for patient records, using plain parameterised SQL."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from backend.config import DATABASE_PATH

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT    NOT NULL,
    dob         TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    glucose     REAL    NOT NULL,
    haemoglobin REAL    NOT NULL,
    cholesterol REAL    NOT NULL,
    remarks     TEXT,
    created_at  TEXT
)
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit if the block succeeds, roll back if it fails, always close."""
    connection = sqlite3.connect(DATABASE_PATH)
    # Rows can then be read by column name and turned into dicts.
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create the patients table if it does not exist yet."""
    with get_connection() as connection:
        connection.execute(CREATE_TABLE_SQL)


def _fetch_patient(connection: sqlite3.Connection, patient_id: int) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return dict(row) if row else None


def list_patients() -> list[dict[str, Any]]:
    """Return every patient, oldest first."""
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM patients ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_patient(patient_id: int) -> dict[str, Any] | None:
    """Return one patient, or None if the id does not exist."""
    with get_connection() as connection:
        return _fetch_patient(connection, patient_id)


def get_patient_by_email(email: str) -> dict[str, Any] | None:
    """Return the patient with this email, or None. Used for the duplicate check."""
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM patients WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def create_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """Insert a new patient and return the saved row, including its id and created_at.

    Raises sqlite3.IntegrityError if the email already exists.
    """
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO patients
                (full_name, dob, email, glucose, haemoglobin, cholesterol, remarks, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient["full_name"],
                patient["dob"],
                patient["email"],
                patient["glucose"],
                patient["haemoglobin"],
                patient["cholesterol"],
                patient["remarks"],
                created_at,
            ),
        )
        saved = _fetch_patient(connection, cursor.lastrowid)
        if saved is None:
            raise RuntimeError("Patient was inserted but could not be read back.")
        return saved


def update_patient(patient_id: int, patient: dict[str, Any]) -> dict[str, Any] | None:
    """Update an existing patient and return the saved row, or None if the id does not exist.

    Raises sqlite3.IntegrityError if the new email belongs to another patient.
    """
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE patients
            SET full_name = ?, dob = ?, email = ?, glucose = ?,
                haemoglobin = ?, cholesterol = ?, remarks = ?
            WHERE id = ?
            """,
            (
                patient["full_name"],
                patient["dob"],
                patient["email"],
                patient["glucose"],
                patient["haemoglobin"],
                patient["cholesterol"],
                patient["remarks"],
                patient_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
        return _fetch_patient(connection, patient_id)


def delete_patient(patient_id: int) -> bool:
    """Delete a patient. Return True if a row was deleted, False if the id did not exist."""
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        return cursor.rowcount > 0
