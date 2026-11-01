"""Health remark generation: a Groq AI call, with a rule-based fallback when it fails."""

import json
import logging
from datetime import date

import requests

from backend.config import GROQ_API_KEY, GROQ_MODEL
from backend.schemas import PatientInput

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 15
# Low temperature keeps the risk level consistent for the same values.
TEMPERATURE = 0.2

RULE_BASED_PREFIX = "[Rule-based]"

# Lowest to highest, so max() over this order picks the most serious level.
RISK_LEVELS = ("Low", "Moderate", "High")

SYSTEM_PROMPT = (
    "You are a cautious health screening assistant. You give a short screening hint from "
    "blood test values. You never give a diagnosis. You always reply with JSON only."
)


class AIRemarkError(ValueError):
    """Raised when the AI reply is missing settings or does not have the expected shape."""


def calculate_age(dob: date) -> int:
    today = date.today()
    had_birthday_this_year = (today.month, today.day) >= (dob.month, dob.day)
    return today.year - dob.year - (0 if had_birthday_this_year else 1)


def build_prompt(age: int, glucose: float, haemoglobin: float, cholesterol: float) -> str:
    """Only age and blood values are sent; name and email never leave the app."""
    return (
        f"Age: {age} years\n"
        f"Glucose: {glucose} mg/dL\n"
        f"Haemoglobin: {haemoglobin} g/dL\n"
        f"Cholesterol: {cholesterol} mg/dL\n"
        "Sex and fasting status are unknown.\n\n"
        "Respond with JSON only, in exactly this form: "
        '{"risk_level": "Low|Moderate|High", "remark": "..."}\n'
        "risk_level must be one of Low, Moderate or High. "
        "remark must be a single sentence in Australian English spelling (haemoglobin, anaemia). "
        "When risk_level is not Low, end the remark by recommending a doctor's review."
    )


def parse_ai_reply(content: str) -> tuple[str, str]:
    """Check the AI's JSON text and return (risk_level, remark)."""
    reply = json.loads(content)
    if not isinstance(reply, dict):
        raise AIRemarkError("AI reply is not a JSON object.")
    risk_level = reply.get("risk_level")
    remark = reply.get("remark")
    if risk_level not in RISK_LEVELS:
        raise AIRemarkError(f"AI reply has an unexpected risk_level: {risk_level!r}.")
    if not isinstance(remark, str) or not remark.strip():
        raise AIRemarkError("AI reply has no remark.")
    return risk_level, remark.strip()


def ask_groq(age: int, glucose: float, haemoglobin: float, cholesterol: float) -> tuple[str, str]:
    """Call Groq's chat completions API and return (risk_level, remark)."""
    if not GROQ_API_KEY or not GROQ_MODEL:
        raise AIRemarkError("GROQ_API_KEY or GROQ_MODEL is not set in .env.")
    response = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(age, glucose, haemoglobin, cholesterol)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": TEMPERATURE,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return parse_ai_reply(content)


def _join_with_and(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def rule_based_remark(glucose: float, haemoglobin: float, cholesterol: float) -> tuple[str, str]:
    """Classify the values against fixed adult reference ranges. Returns (risk_level, remark).

    Glucose ranges assume a fasting sample, because fasting status is not recorded.
    """
    findings: list[tuple[str, str]] = []

    if glucose >= 126:
        findings.append(("High", "glucose is high (diabetes risk)"))
    elif glucose >= 100:
        findings.append(("Moderate", "glucose is elevated (prediabetes risk)"))

    if haemoglobin < 12:
        findings.append(("Moderate", "haemoglobin is low (anaemia risk)"))
    elif haemoglobin > 17.5:
        findings.append(("Moderate", "haemoglobin is high"))

    if cholesterol >= 240:
        findings.append(("High", "cholesterol is high"))
    elif cholesterol >= 200:
        findings.append(("Moderate", "cholesterol is borderline high"))

    if not findings:
        return "Low", "Glucose, haemoglobin and cholesterol are all within the reference ranges."

    risk_level = max((level for level, _ in findings), key=RISK_LEVELS.index)
    summary = _join_with_and([description for _, description in findings])
    return risk_level, f"{summary[0].upper()}{summary[1:]}; a doctor's review is recommended."


def generate_remark(patient: PatientInput) -> str:
    """Return the remark text to store, in the form "{risk_level}: {remark}".

    Tries Groq first. Any failure is logged and the rule-based remark is used instead,
    so a patient is always saved even when the AI is unavailable.
    """
    try:
        risk_level, remark = ask_groq(
            calculate_age(patient.dob), patient.glucose, patient.haemoglobin, patient.cholesterol
        )
    # RequestException: network error, timeout or HTTP error such as a bad key.
    # ValueError: invalid JSON or an AIRemarkError. KeyError/IndexError/TypeError: unexpected response shape.
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("AI remark failed, using rule-based fallback: %s", exc)
        risk_level, remark = rule_based_remark(
            patient.glucose, patient.haemoglobin, patient.cholesterol
        )
        remark = f"{RULE_BASED_PREFIX} {remark}"
    return f"{risk_level}: {remark}"
