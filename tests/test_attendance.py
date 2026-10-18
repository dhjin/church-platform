"""출석 기록 (DB 테스트는 TEST_DATABASE_URL 이 있을 때만)."""
import os
from datetime import date

import pytest

import attendance

SUNDAYS = [date(2026, 10, 11), date(2026, 10, 4), date(2026, 9, 27)]


def test_default_service_date_is_last_sunday():
    assert attendance.default_service_date(date(2026, 10, 18)) == date(2026, 10, 18)  # 일요일
    assert attendance.default_service_date(date(2026, 10, 17)) == date(2026, 10, 11)  # 토요일
    assert attendance.default_service_date(date(2026, 10, 12)) == date(2026, 10, 11)  # 월요일


def test_parse_service_type():
    assert attendance.parse_service_type("수요예배") == "수요예배"
    assert attendance.parse_service_type("<script>") == "주일예배"
    assert attendance.parse_service_type(None) == "주일예배"


def test_long_absences():
    members = [
        {"id": 1, "name": "A", "status": "active"},    # 최근 출석
        {"id": 2, "name": "B", "status": "active"},    # 3번 연속 결석
        {"id": 3, "name": "C", "status": "active"},    # 출석 기록 없음 → 제외
        {"id": 4, "name": "D", "status": "inactive"},  # 비활성 → 제외
        {"id": 5, "name": "E", "status": "active"},    # 더 오래 결석
    ]
    last = {1: SUNDAYS[0], 2: date(2026, 9, 20), 4: date(2026, 9, 1), 5: date(2026, 8, 30)}
    out = attendance.long_absences(members, last, {1}, SUNDAYS)
    assert [m["id"] for m in out] == [5, 2]
    assert out[1]["last_attended"] == date(2026, 9, 20)
    # 기록이 3번보다 적으면 판단하지 않는다
    assert attendance.long_absences(members, last, {1}, SUNDAYS[:2]) == []


@pytest.fixture
def client(db):
    os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import main
    from fastapi.testclient import TestClient

    with db.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t1', '테스트교회'), ('t2', '다른교회') RETURNING id")
        tid, other = [r[0] for r in cur.fetchall()]
        cur.execute(
            "INSERT INTO users (tenant_id, username, password, role, name, email) VALUES (%s,'boss','x','owner','','') RETURNING id",
            (tid,),
        )
        uid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO subscriptions (tenant_id, provider, plan, amount, customer_key) VALUES (%s,'toss','premium',49000,'c1')",
            (tid,),
        )
    db.commit()
    main.sessions["att"] = {"id": uid, "username": "boss", "role": "owner", "tenant_id": tid}
    c = TestClient(main.app, base_url="http://t1.example.org")
    c.cookies.set("session_token", "att")
    yield c, tid, other
    main.sessions.pop("att", None)


def _member(db, tid, name, cell=""):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO congregation_members (tenant_id, name, cell_group) VALUES (%s,%s,%s) RETURNING id", (tid, name, cell)
        )
        mid = cur.fetchone()[0]
    db.commit()
    return mid


def _present(db, tid, day, kind="주일예배"):
    with db.cursor() as cur:
        cur.execute(
            "SELECT member_id FROM attendance_records WHERE tenant_id=%s AND service_date=%s AND service_type=%s ORDER BY member_id",
            (tid, day, kind),
        )
        return [r[0] for r in cur.fetchall()]


def test_save_replaces_and_ignores_other_church(client, db):
    c, tid, other = client
    a, b = _member(db, tid, "김", "1구역"), _member(db, tid, "이")
    stranger = _member(db, other, "남의교회")

    r = c.post("/planner/attendance/save", data={"service_date": "2026-10-11", "member_ids": [a, b, stranger]},
               follow_redirects=False)
    assert r.status_code == 303 and "saved=1" in r.headers["location"]
    assert _present(db, tid, "2026-10-11") == [a, b]
    assert _present(db, other, "2026-10-11") == []

    # 다시 저장하면 그날 기록을 바꾼다 (체크 해제 반영)
    c.post("/planner/attendance/save", data={"service_date": "2026-10-11", "member_ids": [b]})
    assert _present(db, tid, "2026-10-11") == [b]

    # 아무도 체크 안 하고 저장해도 된다
    c.post("/planner/attendance/save", data={"service_date": "2026-10-11", "service_type": "수요예배"})
    assert _present(db, tid, "2026-10-11", "수요예배") == []

    page = c.get("/planner/attendance?date=2026-10-11")
    assert page.status_code == 200
    assert "1구역" in page.text and "1 / 2명 출석" in page.text


def test_dashboard_and_member_show_attendance(client, db):
    c, tid, _ = client
    a, b = _member(db, tid, "꾸준한성도"), _member(db, tid, "결석성도")
    c.post("/planner/attendance/save", data={"service_date": "2026-09-20", "member_ids": [a, b]})
    for d in SUNDAYS:
        c.post("/planner/attendance/save", data={"service_date": d.isoformat(), "member_ids": [a]})
    # 수요예배 기록은 장기 결석 판단에 섞이지 않는다
    c.post("/planner/attendance/save", data={"service_date": "2026-10-14", "service_type": "수요예배", "member_ids": [a]})

    dash = c.get("/planner/dashboard").text
    section = dash.split("장기 결석")[1].split("성도 목록")[0]
    assert "결석성도" in section and "꾸준한성도" not in section
    assert "마지막 출석 2026-09-20" in section

    detail = c.get(f"/planner/members/{a}").text
    assert "2026-10-14" in detail and "4번" in detail


def test_attendance_requires_owner(client, db):
    c, _, _ = client
    c.cookies.clear()
    assert c.get("/planner/attendance").status_code == 403
    assert c.post("/planner/attendance/save", data={"service_date": "2026-10-11"}).status_code == 403
