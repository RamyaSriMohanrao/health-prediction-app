"""Validation tests built from the assignment's test-data table."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.schemas import PatientInput, format_errors

FIELDS = ("full_name", "dob", "email", "glucose", "haemoglobin", "cholesterol")

TEST_DATA = {
    1: ("Robyn Pears", "28.01.1960", "robyn@gmail.com", 232, 13.5, 180),
    2: ("John Hunter", "10.12.1990", "hunter@gmail", 94, 15, 200),
    3: ("Darryl Tim", "12.11.1993", "timd@smh.com.au", 240, 18.6, 326),
    4: ("Peter Larry", "31.11.2001", "Larry@hotmail.com", 88, 11.5, 165),
    5: ("Sam Kerr", "09.12.2006", "sam@news.com.au", 198, 8.9, 192),
    6: ("Robyn Pears", "28.01.1960", "robyn@gmail.com", 232, 13.5, 180),
    7: ("Madison XI", "12.09.1998", "madison@hotmail.com", 85, 7.6, 163),
    8: ("Kris Wu", "19.10.2030", "Kris.wu.gmail.com", 79, 16.5, 197),
    9: ("Tenille Singh", "30.11.1991", "Tenille@yahoo.com", 101, 15, 310),
    10: ("Prem Kumar", "28.04.1990", "prem@telstra.com", 155, 12.5, 265),
}

EMAIL_MESSAGE = "Email must be a valid address with an @ and a domain ending such as .com."


def record(test_number: int, **changes) -> dict:
    """Return a test-data row as a dict, with optional field changes for checking a single rule."""
    data = dict(zip(FIELDS, TEST_DATA[test_number]))
    data.update(changes)
    return data


def errors_for(data: dict) -> dict[str, str]:
    """Validate data that should fail and return {field: message} for every error."""
    with pytest.raises(ValidationError) as caught:
        PatientInput(**data)
    return {error["field"]: error["message"] for error in format_errors(caught.value.errors())}


# Row 6 repeats row 1. It passes validation; the API rejects it as a duplicate email.
@pytest.mark.parametrize("test_number", [1, 3, 5, 6, 7, 9, 10])
def test_valid_test_data_rows_pass(test_number):
    data = record(test_number)
    patient = PatientInput(**data)
    assert patient.full_name == data["full_name"]
    assert patient.email == data["email"].lower()


def test_row_2_rejects_email_without_domain_ending():
    assert errors_for(record(2)) == {"email": EMAIL_MESSAGE}


def test_row_4_rejects_impossible_calendar_date():
    assert errors_for(record(4)) == {"dob": "Date of birth is not a real calendar date."}


def test_row_8_reports_future_date_and_email_errors_together():
    assert errors_for(record(8)) == {
        "dob": "Date of birth cannot be in the future.",
        "email": EMAIL_MESSAGE,
    }


@pytest.mark.parametrize("dob", ["28.01.1960", "28/01/1960"])
def test_dot_and_slash_date_formats_both_accepted(dob):
    assert PatientInput(**record(1, dob=dob)).dob == date(1960, 1, 28)


def test_name_and_email_are_trimmed_and_email_lower_cased():
    patient = PatientInput(**record(9, full_name="  Tenille Singh  ", email=" Tenille@yahoo.com "))
    assert patient.full_name == "Tenille Singh"
    assert patient.email == "tenille@yahoo.com"


def test_future_date_rejected():
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    assert errors_for(record(1, dob=tomorrow)) == {"dob": "Date of birth cannot be in the future."}


def test_date_more_than_120_years_ago_rejected():
    too_old = f"28.01.{date.today().year - 121}"
    assert errors_for(record(1, dob=too_old)) == {
        "dob": "Date of birth cannot be more than 120 years ago."
    }


@pytest.mark.parametrize("dob", ["1960-01-28", "28/01.1960", "28.1.1960"])
def test_wrong_date_format_rejected(dob):
    assert errors_for(record(1, dob=dob)) == {
        "dob": "Date of birth must be in dd/mm/yyyy or dd.mm.yyyy format."
    }


@pytest.mark.parametrize("full_name", ["R", "Robyn Pears 2", "Robyn@Pears", "..."])
def test_invalid_name_rejected(full_name):
    assert set(errors_for(record(1, full_name=full_name))) == {"full_name"}


def test_non_numeric_glucose_rejected():
    assert errors_for(record(1, glucose="abc")) == {"glucose": "Glucose must be a number."}


def test_numeric_text_is_accepted():
    assert PatientInput(**record(1, glucose="232")).glucose == 232.0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("glucose", 0, "Glucose must be greater than 0."),
        ("haemoglobin", -3, "Haemoglobin must be greater than 0."),
        ("glucose", 1001, "Glucose must be 1000 mg/dL or less."),
        ("haemoglobin", 25.1, "Haemoglobin must be 25 g/dL or less."),
        ("cholesterol", 1500, "Cholesterol must be 1000 mg/dL or less."),
        ("cholesterol", True, "Cholesterol must be a number."),
        ("glucose", "nan", "Glucose must be a number."),
    ],
)
def test_blood_values_out_of_range_rejected(field, value, message):
    assert errors_for(record(1, **{field: value})) == {field: message}


def test_missing_and_blank_fields_reported_as_required():
    errors = errors_for({"full_name": "   ", "glucose": ""})
    assert errors == {
        "full_name": "Full name is required.",
        "dob": "Date of birth is required.",
        "email": "Email is required.",
        "glucose": "Glucose is required.",
        "haemoglobin": "Haemoglobin is required.",
        "cholesterol": "Cholesterol is required.",
    }
