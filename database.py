import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    if _DATABASE_URL:
        return psycopg2.connect(_DATABASE_URL)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "church"),
        user=os.getenv("DB_USER", "church"),
        password=os.getenv("DB_PASSWORD", ""),
    )
