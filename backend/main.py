"""FastAPI app: patient CRUD API, plus the frontend page and its static files."""

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import database
from backend.ai_service import generate_remark
from backend.config import PROJECT_ROOT
from backend.schemas import PatientInput, PatientOut, format_dob, format_errors

FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database.init_db()
    yield


app = FastAPI(title="Health Prediction App", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return every validation failure as a 422 list of {field, message}."""
    return JSONResponse(status_code=422, content={"detail": format_errors(exc.errors())})


def error(status_code: int, field: str, message: str) -> HTTPException:
    # Same {field, message} list shape as validation errors, so the frontend handles all errors one way.
    return HTTPException(status_code=status_code, detail=[{"field": field, "message": message}])


def not_found(patient_id: int) -> HTTPException:
    return error(404, "id", f"No patient found with id {patient_id}.")


def duplicate_email() -> HTTPException:
    return error(409, "email", "A patient with this email already exists.")


def to_record(patient: PatientInput, remarks: str | None) -> dict[str, Any]:
    """Shape validated input into the dict the database layer expects."""
    return {**patient.model_dump(), "dob": patient.dob.isoformat(), "remarks": remarks}


def to_patient_out(row: dict[str, Any]) -> PatientOut:
    return PatientOut(**{**row, "dob": format_dob(row["dob"])})


def blood_values_changed(existing: dict[str, Any], patient: PatientInput) -> bool:
    return (
        existing["glucose"] != patient.glucose
        or existing["haemoglobin"] != patient.haemoglobin
        or existing["cholesterol"] != patient.cholesterol
    )


@app.get("/api/patients")
def list_patients() -> list[PatientOut]:
    return [to_patient_out(row) for row in database.list_patients()]


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: int) -> PatientOut:
    row = database.get_patient(patient_id)
    if row is None:
        raise not_found(patient_id)
    return to_patient_out(row)


@app.post("/api/patients", status_code=201)
def create_patient(patient: PatientInput) -> PatientOut:
    # Checked before generating the remark, so a duplicate never costs an AI call.
    if database.get_patient_by_email(patient.email) is not None:
        raise duplicate_email()
    record = to_record(patient, generate_remark(patient))
    try:
        saved = database.create_patient(record)
    except sqlite3.IntegrityError:
        # Another request saved the same email between the check above and this insert.
        raise duplicate_email()
    return to_patient_out(saved)


@app.put("/api/patients/{patient_id}")
def update_patient(patient_id: int, patient: PatientInput) -> PatientOut:
    existing = database.get_patient(patient_id)
    if existing is None:
        raise not_found(patient_id)
    owner = database.get_patient_by_email(patient.email)
    if owner is not None and owner["id"] != patient_id:
        raise duplicate_email()

    if blood_values_changed(existing, patient):
        remarks = generate_remark(patient)
    else:
        remarks = existing["remarks"]

    try:
        saved = database.update_patient(patient_id, to_record(patient, remarks))
    except sqlite3.IntegrityError:
        raise duplicate_email()
    if saved is None:
        raise not_found(patient_id)
    return to_patient_out(saved)


@app.delete("/api/patients/{patient_id}", status_code=204)
def delete_patient(patient_id: int) -> None:
    if not database.delete_patient(patient_id):
        raise not_found(patient_id)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
