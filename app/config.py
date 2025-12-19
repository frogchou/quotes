import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", 10))
APP_NAME = "Quotes"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
