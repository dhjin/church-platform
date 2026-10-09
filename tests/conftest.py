import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def db():
    """TEST_DATABASE_URL 이 있을 때만 실행. 스키마를 만들고 테스트 데이터는 테스트마다 비운다."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL 미설정")
    import psycopg2

    conn = psycopg2.connect(TEST_DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute((Path(__file__).resolve().parent.parent / "init_schema.sql").read_text())
        cur.execute("TRUNCATE tenants RESTART IDENTITY CASCADE")
    conn.commit()
    yield conn
    conn.close()
