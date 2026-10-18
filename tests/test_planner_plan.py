"""목양 플래너는 프리미엄 요금제에서만 열린다."""
import os

import pytest

from billing import config


def test_planner_allowed_by_plan(monkeypatch):
    assert config.planner_allowed("premium")
    assert not config.planner_allowed("plus")
    assert not config.planner_allowed("standard")
    assert not config.planner_allowed("unknown")
    monkeypatch.setattr(config, "PLANNER_MIN_PLAN", "plus")
    assert config.planner_allowed("plus") and config.planner_allowed("premium")
    assert not config.planner_allowed("standard")


@pytest.fixture
def owner(db):
    os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import main
    from fastapi.testclient import TestClient

    with db.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t1', '테스트교회') RETURNING id")
        tid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO users (tenant_id, username, password, role, name, email) VALUES (%s,'boss','x','owner','','') RETURNING id",
            (tid,),
        )
        uid = cur.fetchone()[0]
    db.commit()
    main.sessions["plan"] = {"id": uid, "username": "boss", "role": "owner", "tenant_id": tid}
    c = TestClient(main.app, base_url="http://t1.example.org")
    c.cookies.set("session_token", "plan")
    yield c, tid
    main.sessions.pop("plan", None)


def _set_plan(db, tid, plan):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO subscriptions (tenant_id, provider, plan, amount, customer_key) VALUES (%s,'toss',%s,0,'c1')"
            " ON CONFLICT (tenant_id) DO UPDATE SET plan=EXCLUDED.plan",
            (tid, plan),
        )
    db.commit()


@pytest.mark.parametrize("plan", [None, "standard", "plus"])
def test_lower_plans_see_upgrade_page(owner, db, plan):
    c, tid = owner
    if plan:
        _set_plan(db, tid, plan)
    for path in ("/planner/dashboard", "/planner/attendance", "/planner/donations"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/planner/upgrade", path
    assert c.post("/planner/attendance/save", data={"service_date": "2026-10-11"}).status_code == 402
    assert c.post("/api/planner/members/1/contact").status_code == 402
    page = c.get("/planner/upgrade")
    assert page.status_code == 200 and "프리미엄" in page.text and "49,000" in page.text


def test_premium_opens_planner(owner, db):
    c, tid = owner
    _set_plan(db, tid, "premium")
    assert c.get("/planner/dashboard").status_code == 200
    assert c.get("/planner/attendance").status_code == 200


def test_upgrade_page_needs_owner(owner):
    c, _ = owner
    c.cookies.clear()
    assert c.get("/planner/upgrade").status_code == 403


def test_dashboard_never_names_the_model(owner, db, monkeypatch):
    import care_decision
    c, tid = owner
    _set_plan(db, tid, "premium")
    page = c.get("/planner/dashboard").text
    assert "Jev" not in page and "AI 분석" not in page  # 기본 규칙일 때는 표시 없음
    monkeypatch.setattr(care_decision, "recommend", lambda members, today: ([], "Jev"))
    page = c.get("/planner/dashboard").text
    assert "AI 분석" in page and "Jev" not in page
