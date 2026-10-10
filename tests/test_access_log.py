from datetime import timedelta
from types import SimpleNamespace

import access_log


def _request(tenant_id, path="/", ua="Mozilla/5.0 (iPhone)", headers=None, method="GET"):
    h = {"user-agent": ua, **(headers or {})}
    return SimpleNamespace(
        state=SimpleNamespace(tenant={"id": tenant_id} if tenant_id else None),
        headers=h, method=method, client=SimpleNamespace(host="10.0.0.5"),
        url=SimpleNamespace(path=path, query=""),
    )


def _tenant(conn, slug):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES (%s, %s) RETURNING id", (slug, slug))
        tid = cur.fetchone()[0]
    conn.commit()
    return tid


def _user(conn, tid, username, name=""):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (tenant_id, username, password, name) VALUES (%s, %s, 'x', %s) RETURNING id",
                    (tid, username, name))
        uid = cur.fetchone()[0]
    conn.commit()
    return {"id": uid, "username": username}


def test_client_ip_prefers_proxy_headers():
    assert access_log.client_ip(_request(1, headers={"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"})) == "1.1.1.1"
    assert access_log.client_ip(_request(1, headers={"x-forwarded-for": "3.3.3.3, 10.0.0.1"})) == "3.3.3.3"
    assert access_log.client_ip(_request(1)) == "10.0.0.5"


def test_should_log_page_and_bot_detection():
    assert access_log.should_log_page("GET", "/news/1")
    assert not access_log.should_log_page("GET", "/static/css/a.css")
    assert not access_log.should_log_page("POST", "/admin/news/create")
    assert access_log.is_bot("Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert access_log.is_bot("")
    assert not access_log.is_bot("Mozilla/5.0 (iPhone)")


def test_record_summary_and_member_activity_are_per_tenant(db, monkeypatch):
    monkeypatch.setattr(access_log, "get_conn", lambda: __import__("psycopg2").connect(db.dsn))
    a, b = _tenant(db, "a"), _tenant(db, "b")
    kim = _user(db, a, "kim", "김성도")
    _user(db, a, "lee", "이성도")
    other = _user(db, b, "park")

    access_log.record(_request(a), "login", kim, 303)
    access_log.record(_request(a, "/news/1"), "page", kim, 200)
    access_log.record(_request(a, "/", headers={"x-forwarded-for": "9.9.9.9"}), "page", None, 200)
    access_log.record(_request(a, "/", ua="Googlebot"), "page", None, 200)
    access_log.record(_request(a, "/login", method="POST"), "login_fail", None, 200, username="kim")
    access_log.record(_request(b), "page", other, 200)
    access_log.record(_request(None), "page", None, 200)  # 랜딩(테넌트 없음)은 기록 안 함

    s = access_log.summary(db, a)
    assert s == {"views": 2, "visitors": 2, "members": 1, "login_fails": 1}

    members = access_log.member_activity(db, a)
    assert [m["username"] for m in members] == ["kim", "lee"]
    assert members[0]["days_ago"] == 0 and members[0]["logins"] == 1 and members[0]["views"] == 1
    assert members[1]["last_seen"] is None

    r = access_log.search(db, a)
    assert r["total"] == 4  # 봇 제외
    assert access_log.search(db, a, show_bots=True)["total"] == 5
    assert access_log.search(db, a, members_only=True)["total"] == 2
    assert access_log.search(db, a, event="login_fail")["logs"][0]["username"] == "kim"
    assert access_log.search(db, a, q="9.9.9")["total"] == 1
    today = access_log.now_kst().strftime("%Y-%m-%d")
    assert access_log.search(db, a, date=today)["total"] == 4
    assert access_log.search(db, a, date="2000-01-01")["total"] == 0


def test_purge_old_keeps_recent(db):
    a = _tenant(db, "a")
    with db.cursor() as cur:
        cur.execute("INSERT INTO access_logs (tenant_id, created_at, event) VALUES (%s, %s, 'page'), (%s, %s, 'page')",
                    (a, access_log.now_kst() - timedelta(days=access_log.RETENTION_DAYS + 1), a, access_log.now_kst()))
    db.commit()
    access_log.purge_old(db)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM access_logs")
        assert cur.fetchone()[0] == 1
