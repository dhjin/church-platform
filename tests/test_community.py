"""커뮤니티 게시판 (TEST_DATABASE_URL 이 있을 때만 DB 테스트)."""
import io
import os

import pytest
from PIL import Image

import community


def _jpeg(w=3000, h=2000, gps=True) -> bytes:
    img = Image.new("RGB", (w, h), (200, 100, 50))
    exif = Image.Exif()
    exif[0x0112] = 1
    if gps:
        exif[0x8825] = {1: "N", 2: (37.0, 30.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_process_photo_shrinks_and_strips_exif():
    data, ext = community.process_photo(_jpeg())
    assert ext == ".jpg"
    img = Image.open(io.BytesIO(data))
    assert max(img.size) == community.MAX_SIDE
    assert not img.getexif()


def test_process_photo_rejects_fake_image():
    with pytest.raises(community.PhotoError):
        community.process_photo(b"<html><script>alert(1)</script></html>")
    with pytest.raises(community.PhotoError):
        community.process_photo(b"")


@pytest.fixture
def board(db, tmp_path, monkeypatch):
    os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main, "get_upload_dir", lambda tid: tmp_path)
    monkeypatch.setattr(community, "post_limiter", community.RateLimiter(limit=100, window=3600))
    users = {}
    with db.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t1', '테스트교회') RETURNING id")
        tid = cur.fetchone()[0]
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES ('t2', '남의교회') RETURNING id")
        other = cur.fetchone()[0]
        for name, role, t in [("kim", "user", tid), ("lee", "user", tid), ("wait", "pending", tid),
                              ("boss", "owner", tid), ("far", "user", other)]:
            cur.execute(
                "INSERT INTO users (tenant_id, username, password, role, name, email) VALUES (%s,%s,'x',%s,%s,'') RETURNING id",
                (t, f"{name}@ex.org", role, name.upper()),
            )
            users[name] = cur.fetchone()[0]
            main.sessions[f"tok-{name}"] = {"id": users[name], "username": f"{name}@ex.org",
                                            "role": role, "tenant_id": t}
    db.commit()

    def client(who=None):
        c = TestClient(main.app, base_url="http://t1.example.org")
        if who:
            c.cookies.set("session_token", f"tok-{who}")
        return c

    yield client, tid, users, tmp_path
    for name in users:
        main.sessions.pop(f"tok-{name}", None)


def _post(c, title="주일 소풍", content="즐거웠어요", photos=()):
    files = [("photos", (f"p{i}.jpg", io.BytesIO(p), "image/jpeg")) for i, p in enumerate(photos)]
    return c.post("/community/new", data={"title": title, "content": content}, files=files or None,
                  follow_redirects=False)


def test_member_posts_with_photos_and_everyone_can_read(board, db):
    client, tid, users, upload_dir = board
    r = _post(client("kim"), photos=[_jpeg(), _jpeg(800, 600, gps=False)])
    assert r.status_code == 303
    post_id = int(r.headers["location"].rsplit("/", 1)[1])
    with db.cursor() as cur:
        cur.execute("SELECT image_path FROM board_images WHERE post_id=%s ORDER BY sort_order", (post_id,))
        paths = [p[0] for p in cur.fetchall()]
    assert len(paths) == 2 and all(p.startswith(f"/uploads/{tid}/board_") for p in paths)
    assert all((upload_dir / p.rsplit("/", 1)[1]).exists() for p in paths)

    page = client().get(f"/community/{post_id}").text
    assert "주일 소풍" in page and paths[0] in page and "KIM" in page
    assert "kim@ex.org" not in page  # 이메일은 보이지 않는다
    listing = client().get("/community").text
    assert f"/community/{post_id}" in listing and "&#128247; 2" in listing


def test_pending_and_anonymous_cannot_post(board):
    client, *_ = board
    assert _post(client("wait")).status_code == 403
    assert _post(client()).status_code == 401
    assert client().get("/community/new", follow_redirects=False).status_code == 303
    assert "/community/new" not in client("wait").get("/community").text


def test_rejects_non_image_and_too_many_photos(board, db):
    client, *_ = board
    c = client("kim")
    r = c.post("/community/new", data={"title": "x"},
               files=[("photos", ("a.jpg", io.BytesIO(b"<html>"), "image/jpeg"))])
    assert r.status_code == 400
    small = _jpeg(10, 10, gps=False)
    assert _post(c, photos=[small] * (community.MAX_PHOTOS + 1)).status_code == 400
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM board_posts")
        assert cur.fetchone()[0] == 0


def test_rate_limit(board, monkeypatch):
    client, *_ = board
    monkeypatch.setattr(community, "post_limiter", community.RateLimiter(limit=1, window=3600))
    c = client("kim")
    assert _post(c).status_code == 303
    assert _post(c).status_code == 429


def test_only_author_or_manager_can_edit_and_delete(board, db):
    client, tid, users, upload_dir = board
    r = _post(client("kim"), photos=[_jpeg(50, 50, gps=False)] * 2)
    post_id = int(r.headers["location"].rsplit("/", 1)[1])
    with db.cursor() as cur:
        cur.execute("SELECT id, image_path FROM board_images WHERE post_id=%s ORDER BY sort_order", (post_id,))
        imgs = cur.fetchall()

    assert client("lee").post(f"/community/{post_id}/edit", data={"title": "탈취"}).status_code == 403
    assert client("lee").post(f"/community/{post_id}/delete").status_code == 403

    r = client("kim").post(f"/community/{post_id}/edit",
                           data={"title": "고침", "content": "", "remove_images": [str(imgs[0][0])]},
                           files=[("photos", ("n.jpg", io.BytesIO(_jpeg(60, 60, gps=False)), "image/jpeg"))],
                           follow_redirects=False)
    assert r.status_code == 303
    with db.cursor() as cur:
        cur.execute("SELECT title FROM board_posts WHERE id=%s", (post_id,))
        assert cur.fetchone()[0] == "고침"
        cur.execute("SELECT id, image_path FROM board_images WHERE post_id=%s ORDER BY sort_order, id", (post_id,))
        now = cur.fetchall()
    assert len(now) == 2 and now[0][0] == imgs[1][0]  # 남은 사진이 앞, 새 사진이 뒤
    assert not (upload_dir / imgs[0][1].rsplit("/", 1)[1]).exists()

    client("lee").post(f"/community/{post_id}/comment", data={"content": "멋져요"})
    assert client("boss").post(f"/community/{post_id}/delete", follow_redirects=False).status_code == 303
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM board_posts")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM comments WHERE post_type='board'")
        assert cur.fetchone()[0] == 0
    assert not any(upload_dir.iterdir())


def test_comments_and_tenant_isolation(board, db):
    client, tid, users, _ = board
    r = _post(client("kim"))
    post_id = int(r.headers["location"].rsplit("/", 1)[1])
    assert client("wait").post(f"/community/{post_id}/comment", data={"content": "스팸"}).status_code == 403
    client("lee").post(f"/community/{post_id}/comment", data={"content": "아멘"})
    assert "아멘" in client().get(f"/community/{post_id}").text

    other = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(
        __import__("main").app, base_url="http://t2.example.org")
    assert other.get(f"/community/{post_id}").status_code == 404
    assert "주일 소풍" not in other.get("/community").text


def test_demoted_user_is_blocked_even_with_old_session(board, db):
    client, tid, users, _ = board
    with db.cursor() as cur:
        cur.execute("UPDATE users SET role='pending' WHERE id=%s", (users["lee"],))
    db.commit()
    assert _post(client("lee")).status_code == 403


def test_nav_has_community_link(board):
    client, *_ = board
    assert 'href="/community"' in client().get("/pastoral").text
