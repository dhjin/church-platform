"""회원가입 승인제·차단 도메인·관리자 승인 흐름 (TEST_DATABASE_URL 이 있을 때만)."""
import os

import pytest


@pytest.fixture
def app(db, monkeypatch):
    os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import main
    import signup_guard
    from fastapi.testclient import TestClient

    monkeypatch.setattr(signup_guard, "signup_limiter", signup_guard.RateLimiter(limit=3, window=3600))
    with db.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t1', '테스트교회') RETURNING id")
        tid = cur.fetchone()[0]
        cur.execute("INSERT INTO users (tenant_id, username, password, role) VALUES (%s,'boss','x','owner') RETURNING id", (tid,))
        owner_id = cur.fetchone()[0]
    db.commit()
    yield main, TestClient(main.app, base_url="http://t1.example.org"), tid, owner_id
    main.sessions.clear()


def _user(db, email):
    with db.cursor() as cur:
        cur.execute("SELECT id, role FROM users WHERE email=%s", (email,))
        return cur.fetchone()


def _temp_pw(html):
    return html.split("<b>")[1].split("</b>")[0]


def test_signup_is_pending_until_owner_approves(app, db):
    main, c, tid, owner_id = app
    r = c.post("/register", data={"name": "홍길동", "email": "hong@gmail.com"})
    assert "관리자 승인" in r.text
    uid, role = _user(db, "hong@gmail.com")
    assert role == "pending"
    pw = _temp_pw(r.text)

    r = c.post("/login", data={"username": "hong@gmail.com", "password": pw}, follow_redirects=False)
    assert r.status_code == 200 and "승인을 기다리는" in r.text

    main.sessions["own"] = {"id": owner_id, "username": "boss", "role": "owner", "tenant_id": tid}
    c.cookies.set("session_token", "own")
    assert c.post(f"/admin/users/role/{uid}", data={"role": "user"}, follow_redirects=False).status_code == 303
    c.cookies.clear()

    r = c.post("/login", data={"username": "hong@gmail.com", "password": pw}, follow_redirects=False)
    assert r.status_code == 303


def test_blocked_domain_and_honeypot_cannot_sign_up(app, db):
    _, c, _, _ = app
    r = c.post("/register", data={"name": "스팸", "email": "x@immenseignite.info"})
    assert "가입할 수 없습니다" in r.text
    r = c.post("/register", data={"name": "봇봇", "email": "bot@gmail.com", "website": "http://spam"})
    assert "가입할 수 없습니다" in r.text
    assert _user(db, "x@immenseignite.info") is None and _user(db, "bot@gmail.com") is None


def test_existing_blocked_domain_user_cannot_log_in_or_comment(app, db):
    main, c, tid, _ = app
    with db.cursor() as cur:
        cur.execute("INSERT INTO users (tenant_id, username, password, role, email) VALUES (%s,%s,%s,'user',%s) RETURNING id",
                    (tid, "old@immenseignite.info", main.hash_password("pw123456"), "old@immenseignite.info"))
        uid = cur.fetchone()[0]
    db.commit()
    r = c.post("/login", data={"username": "old@immenseignite.info", "password": "pw123456"}, follow_redirects=False)
    assert r.status_code == 200 and "승인을 기다리는" in r.text

    main.sessions["spam"] = {"id": uid, "username": "old@immenseignite.info", "role": "user", "tenant_id": tid}
    c.cookies.set("session_token", "spam")
    assert c.post("/news/1/comment", data={"content": "광고"}).status_code == 403


def test_signup_rate_limited_per_ip(app, db):
    _, c, _, _ = app
    for i in range(3):
        assert "관리자 승인" in c.post("/register", data={"name": "사람", "email": f"p{i}@gmail.com"}).text
    r = c.post("/register", data={"name": "사람", "email": "p9@gmail.com"})
    assert "너무 많습니다" in r.text and _user(db, "p9@gmail.com") is None


def test_delete_user_drops_session_and_comment_redirect_stays_local(app, db):
    main, c, tid, owner_id = app
    with db.cursor() as cur:
        cur.execute("INSERT INTO users (tenant_id, username, password, role) VALUES (%s,'u1','x','user') RETURNING id", (tid,))
        uid = cur.fetchone()[0]
        cur.execute("INSERT INTO comments (tenant_id, post_type, post_id, user_id, content) VALUES (%s,'news',1,%s,'hi') RETURNING id",
                    (tid, owner_id))
        cid = cur.fetchone()[0]
    db.commit()
    main.sessions["u1"] = {"id": uid, "username": "u1", "role": "user", "tenant_id": tid}
    main.sessions["own"] = {"id": owner_id, "username": "boss", "role": "owner", "tenant_id": tid}
    c.cookies.set("session_token", "own")
    c.post(f"/admin/users/delete/{uid}", follow_redirects=False)
    assert "u1" not in main.sessions

    r = c.post(f"/comment/{cid}/delete?redirect=https://evil.example", follow_redirects=False)
    assert r.headers["location"] == "/"
