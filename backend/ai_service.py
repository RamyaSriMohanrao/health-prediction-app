"""Health remark generation for a patient's blood values."""

from backend.schemas import PatientInput

RULE_BASED_PREFIX = "[Rule-based]"

# Lowest to highest, so max() over this order picks the most serious level.
RISK_LEVELS = ("Low", "Moderate", "High")


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
    """Return the remark text to store, in the form "{risk_level}: {remark}"."""
    risk_level, remark = rule_based_remark(patient.glucose, patient.haemoglobin, patient.cholesterol)
    return f"{risk_level}: {RULE_BASED_PREFIX} {remark}"
