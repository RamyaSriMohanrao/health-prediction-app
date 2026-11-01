"""Application settings, loaded once from the .env file at the project root."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# An explicit path means the .env file is found no matter which folder uvicorn or pytest is started from.
load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "").strip()

DATABASE_PATH: Path = PROJECT_ROOT / "patients.db"
