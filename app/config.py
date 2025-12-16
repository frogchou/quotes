import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", 10))
APP_NAME = "Quotes"
