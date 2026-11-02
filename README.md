# Health Prediction App

A patient records application with create, read, update and delete (CRUD) operations, strict
input validation, and an AI-generated health remark for each patient's blood test results.

Each record stores a patient's full name, date of birth, email, glucose, haemoglobin and
cholesterol. When a record is saved, the app sends the patient's age and blood values to the
Groq API and stores a short screening remark with a risk level (Low, Moderate or High). If the
AI service is unavailable, a rule-based remark is used instead, so a record is never lost.

## Tech stack

| Layer      | Technology                                                    |
|------------|---------------------------------------------------------------|
| Backend    | Python 3.10+, FastAPI, Uvicorn                                |
| Validation | Pydantic v2                                                   |
| Database   | SQLite through Python's built-in `sqlite3` module, plain SQL  |
| AI         | Groq chat completions API, called with `requests`             |
| Config     | `python-dotenv` (settings loaded from `.env`)                 |
| Frontend   | One HTML page, Bootstrap 5 (CDN), vanilla JavaScript (`fetch`)|
| Tests      | pytest                                                        |

## Project structure

```
health-prediction-app/
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, CRUD routes, serves the frontend
│   ├── schemas.py       # Pydantic models and all validation rules
│   ├── database.py      # SQLite connection, table creation, CRUD queries
│   ├── ai_service.py    # Groq API call and rule-based fallback
│   └── config.py        # Loads settings from .env
├── frontend/
│   ├── index.html       # Form and records table
│   ├── app.js           # API calls, rendering, edit and delete handlers
│   └── styles.css       # Small custom styles
├── tests/
│   └── test_validation.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

1. Install Python 3.10 or newer.

2. Create and activate a virtual environment in the project folder.

   Windows (PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   macOS / Linux:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, paste a Groq API key after `GROQ_API_KEY=`, and set the model:
   ```
   GROQ_API_KEY=
   GROQ_MODEL=openai/gpt-oss-120b
   ```
   An API key can be created at https://console.groq.com/keys. The app was tested with
   `openai/gpt-oss-120b`; any Groq chat model that supports JSON mode can be used.
   `.env` is listed in `.gitignore` and must never be committed.

## Running the app

```
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000 in a browser.

- The SQLite database file `patients.db` is created automatically in the project folder on first
  start. Delete it to start again with an empty table.
- Interactive API documentation is available at http://127.0.0.1:8000/docs.
- Changes to `.env` take effect after restarting the server.

## Running the tests

```
python -m pytest
```

Run this from the project folder. `python -m pytest` is used instead of plain `pytest` because it
adds the project folder to Python's import path, which lets the tests import the `backend`
package.

The tests use the assignment's test data and cover: valid records passing, `hunter@gmail`
rejected, `31.11.2001` rejected, a future date rejected, a non-numeric glucose rejected, both
errors reported together for the Kris Wu record, and dot and slash date formats both accepted.

## API endpoints

| Method | Path                 | Purpose                                                        |
|--------|----------------------|----------------------------------------------------------------|
| GET    | `/api/patients`      | List all patients                                              |
| GET    | `/api/patients/{id}` | Get one patient                                                |
| POST   | `/api/patients`      | Validate, generate the AI remark, save                         |
| PUT    | `/api/patients/{id}` | Validate, regenerate the remark if a blood value changed, save |
| DELETE | `/api/patients/{id}` | Delete one patient                                             |

| Status | Meaning                                                   |
|--------|-----------------------------------------------------------|
| 201    | Patient created                                           |
| 204    | Patient deleted                                           |
| 404    | No patient with that id                                   |
| 409    | The email already belongs to another patient              |
| 422    | Validation failed; every field error is listed together   |

All errors use the same shape, so the frontend shows them the same way:

```json
{"detail": [{"field": "email", "message": "A patient with this email already exists."}]}
```

## Validation rules

The backend is the authority on validation; the form sends values exactly as typed. All field
errors are collected and returned together in one response.

| Field           | Rule                                                                                     |
|-----------------|------------------------------------------------------------------------------------------|
| Full name       | Required, trimmed, 2–100 characters, letters, spaces, apostrophes, hyphens and dots only |
| Date of birth   | Required, `dd/mm/yyyy` or `dd.mm.yyyy`, a real calendar date, not in the future, not more than 120 years ago. Shown back as `dd/mm/yyyy` |
| Email           | Required, trimmed, stored lower-case, must have the form `local@domain.tld`              |
| Glucose         | Required, numeric, greater than 0, at most 1000 mg/dL                                    |
| Haemoglobin     | Required, numeric, greater than 0, at most 25 g/dL                                       |
| Cholesterol     | Required, numeric, greater than 0, at most 1000 mg/dL                                    |
| Duplicate email | Rejected on create; on update, rejected if the email belongs to a different patient     |

Duplicate emails are checked in code to give a clear message, and are also blocked by a
`UNIQUE` constraint in the database in case two requests arrive at the same time.

## AI integration

`backend/ai_service.py` calls Groq's OpenAI-compatible chat completions endpoint with
`requests.post`.

- **Privacy:** only the patient's age (calculated from the date of birth) and the three blood
  values are sent. The name and email never leave the app.
- **Prompt:** states the units (glucose mg/dL, haemoglobin g/dL, cholesterol mg/dL), that sex and
  fasting status are unknown, and asks for JSON only in the form
  `{"risk_level": "Low|Moderate|High", "remark": "..."}`. The remark is one sentence and ends by
  recommending a doctor's review when the risk level is not Low.
- **Request settings:** JSON mode (`response_format`), temperature 0.2 for consistent answers,
  and a 15-second timeout.
- **Checking the reply:** the JSON is parsed and checked; the risk level must be exactly Low,
  Moderate or High, and the remark must not be empty.
- **Stored format:** `"{risk_level}: {remark}"`, for example
  `High: Elevated glucose suggests possible diabetes and warrants a doctor's review.`
- **When it runs:** on every create, and on update only when a blood value has changed.

### Rule-based fallback

If the AI call fails for any reason (missing settings, network error, timeout, invalid API key,
invalid or unexpected JSON), the failure reason is logged in the server terminal and
`rule_based_remark()` is used instead. Fallback remarks are marked `[Rule-based]`, so it is visible
which path produced them, for example:

```
High: [Rule-based] Glucose is high (diabetes risk); a doctor's review is recommended.
```

Reference ranges used by the fallback (adults):

| Value       | Ranges                                                                    |
|-------------|---------------------------------------------------------------------------|
| Glucose     | < 100 normal; 100–125 elevated (prediabetes risk); ≥ 126 high (diabetes risk) |
| Haemoglobin | < 12 low (anaemia risk); 12–17.5 normal; > 17.5 high                      |
| Cholesterol | < 200 desirable; 200–239 borderline high; ≥ 240 high                      |

The overall risk level is the most serious finding: high glucose or high cholesterol gives High;
elevated glucose, borderline cholesterol, or haemoglobin outside the normal range gives Moderate;
all values in range gives Low.

## Test data results

The assignment's test data entered through the app, unmodified and in order:

| #  | Name          | Result   | Reason                                                              |
|----|---------------|----------|---------------------------------------------------------------------|
| 1  | Robyn Pears   | Saved    | All fields valid                                                    |
| 2  | John Hunter   | Rejected | `hunter@gmail` has no domain ending such as `.com`                  |
| 3  | Darryl Tim    | Saved    | All fields valid                                                    |
| 4  | Peter Larry   | Rejected | 31 November is not a real date; November has 30 days                |
| 5  | Sam Kerr      | Saved    | All fields valid                                                    |
| 6  | Robyn Pears   | Rejected | Duplicate: the email already belongs to record 1                    |
| 7  | Madison XI    | Saved    | All fields valid                                                    |
| 8  | Kris Wu       | Rejected | Two errors together: date of birth in the future, and no `@` in the email |
| 9  | Tenille Singh | Saved    | All fields valid; email stored as `tenille@yahoo.com`               |
| 10 | Prem Kumar    | Saved    | All fields valid                                                    |

Most saved records are rated High because their glucose or cholesterol is well above the
reference ranges (for example, Robyn Pears has a glucose of 232 mg/dL against a normal level
below 100).

## Assumptions and limitations

- Remarks are screening hints, not a medical diagnosis, and are labelled as such in the app.
- Reference ranges are for adults. Glucose ranges assume a fasting sample, because fasting status
  is not recorded. Haemoglobin ranges are a combined range, because sex is not recorded.
- The rule-based fallback rates any haemoglobin outside 12–17.5 g/dL as Moderate. It does not
  separate a slightly low value from a very low one; the AI can make that distinction.
- AI answers can vary slightly between runs for the same values. A low temperature reduces but
  does not remove this.
- On update, the remark is regenerated only when a blood value changes. Changing only the date
  of birth keeps the existing remark, even though age is part of the AI prompt.
- The email check is a practical pattern (`local@domain.tld`), not the full email standard.
- The Kris Wu test expects 19.10.2030 to be a future date, so it will need new data after that
  day.
- The app is designed for local use: there is no login or user management, and SQLite stores
  all data in a single local file.
