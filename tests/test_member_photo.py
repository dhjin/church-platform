"""섬기는 분들 사진 바꾸기 (TEST_DATABASE_URL 이 있을 때만)."""
import io
import os

import pytest


@pytest.fixture
def client(db, tmp_path, monkeypatch):
    os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "get_upload_dir", lambda tid: tmp_path)
    with db.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t1', '테스트교회') RETURNING id")
        tid = cur.fetchone()[0]
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t2', '남의교회') RETURNING id")
        other = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO users (tenant_id, username, password, role, name, email) VALUES (%s,'boss','x','owner','','') RETURNING id",
            (tid,),
        )
        uid = cur.fetchone()[0]
    db.commit()
    main.sessions["tok"] = {"id": uid, "username": "boss", "role": "owner", "tenant_id": tid}
    c = TestClient(main.app, base_url="http://t1.example.org")
    c.cookies.set("session_token", "tok")
    yield c, tid, other, tmp_path
    main.sessions.pop("tok", None)


def _member(db, tid, photo="/uploads/x/missing.png"):
    with db.cursor() as cur:
        cur.execute("INSERT INTO members (tenant_id, name, role, photo_path) VALUES (%s,'김목사','담임목사',%s) RETURNING id", (tid, photo))
        mid = cur.fetchone()[0]
    db.commit()
    return mid


def _photo(db, mid):
    with db.cursor() as cur:
        cur.execute("SELECT photo_path FROM members WHERE id=%s", (mid,))
        return cur.fetchone()[0]


def test_replace_photo_saves_file_and_updates_path(client, db):
    c, tid, _, upload_dir = client
    mid = _member(db, tid)
    r = c.post(f"/admin/member/photo/{mid}", files={"photo": ("me.JPG", io.BytesIO(b"jpg"), "image/jpeg")}, follow_redirects=False)
    assert r.status_code == 303
    path = _photo(db, mid)
    assert path.startswith(f"/uploads/{tid}/member_") and path.endswith(".jpg")
    assert (upload_dir / path.rsplit("/", 1)[1]).read_bytes() == b"jpg"


def test_cannot_change_other_church_member_or_upload_non_image(client, db):
    c, tid, other, _ = client
    theirs = _member(db, other, "/keep.png")
    r = c.post(f"/admin/member/photo/{theirs}", files={"photo": ("a.png", io.BytesIO(b"p"), "image/png")})
    assert r.status_code == 404
    assert _photo(db, theirs) == "/keep.png"
    mine = _member(db, tid, "/mine.png")
    r = c.post(f"/admin/member/photo/{mine}", files={"photo": ("a.html", io.BytesIO(b"<x>"), "text/html")})
    assert r.status_code == 400
    assert _photo(db, mine) == "/mine.png"


def test_admin_list_has_change_photo_button(client, db):
    c, tid, _, _ = client
    mid = _member(db, tid)
    assert f'/admin/member/photo/{mid}' in c.get("/admin").text
