"""교회소식·주보 수정과 관리자 화면 목록 (TEST_DATABASE_URL 이 있을 때만)."""
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
        cur.execute(
            "INSERT INTO users (tenant_id, username, password, role, name, email) VALUES (%s,'boss','x','owner','','') RETURNING id",
            (tid,),
        )
        uid = cur.fetchone()[0]
    db.commit()
    main.sessions["tok"] = {"id": uid, "username": "boss", "role": "owner", "tenant_id": tid}
    c = TestClient(main.app, base_url="http://t1.example.org")
    c.cookies.set("session_token", "tok")
    yield c, tid
    main.sessions.pop("tok", None)


def _png(name="a.png"):
    return ("images", (name, io.BytesIO(b"\x89PNG fake"), "image/png"))


def test_owner_can_open_edit_page_and_detail_shows_edit_button(client, db):
    c, tid = client
    with db.cursor() as cur:
        cur.execute("INSERT INTO news (tenant_id, title, content, date, author) VALUES (%s,'주보','본문','2026-10-04 09:00','boss') RETURNING id", (tid,))
        nid = cur.fetchone()[0]
    db.commit()
    r = c.get(f"/admin/news/edit/{nid}")
    assert r.status_code == 200
    assert 'value="2026-10-04"' in r.text
    assert "✏️ 수정" in c.get(f"/news/{nid}").text


def test_update_keeps_unchecked_images_removes_checked_and_appends_new(client, db):
    c, tid = client
    with db.cursor() as cur:
        cur.execute("INSERT INTO news (tenant_id, title, content, date, author) VALUES (%s,'주보','','2026-10-04 09:00','boss') RETURNING id", (tid,))
        nid = cur.fetchone()[0]
        cur.execute("INSERT INTO news_images (tenant_id, news_id, image_path, sort_order) VALUES (%s,%s,'/a',0),(%s,%s,'/b',1) RETURNING id",
                    (tid, nid, tid, nid))
        ids = [r[0] for r in cur.fetchall()]
    db.commit()
    r = c.post(f"/admin/news/update/{nid}",
               data={"title": "새 제목", "content": "고침", "date": "2026-10-04", "remove_images": [str(ids[0])]},
               files=[_png()], follow_redirects=False)
    assert r.status_code == 303
    with db.cursor() as cur:
        cur.execute("SELECT image_path FROM news_images WHERE news_id=%s ORDER BY sort_order", (nid,))
        paths = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT title, date FROM news WHERE id=%s", (nid,))
        title, date = cur.fetchone()
    assert paths[0] == "/b" and len(paths) == 2 and paths[1].startswith(f"/uploads/{tid}/news_")
    assert title == "새 제목" and date == "2026-10-04 09:00"  # 날짜를 안 바꾸면 원래 값 유지


def test_adding_image_to_legacy_post_keeps_its_cover(client, db):
    c, tid = client
    with db.cursor() as cur:
        cur.execute("INSERT INTO news (tenant_id, title, content, date, author, image_path) VALUES (%s,'옛글','','2026-01-01','boss','/old.jpg') RETURNING id", (tid,))
        nid = cur.fetchone()[0]
    db.commit()
    assert "/old.jpg" in c.get(f"/admin/news/edit/{nid}").text
    c.post(f"/admin/news/update/{nid}", data={"title": "옛글", "content": "", "date": "2026-01-08"}, files=[_png()])
    with db.cursor() as cur:
        cur.execute("SELECT image_path FROM news_images WHERE news_id=%s ORDER BY sort_order", (nid,))
        paths = [x[0] for x in cur.fetchall()]
        cur.execute("SELECT date FROM news WHERE id=%s", (nid,))
        assert cur.fetchone()[0] == "2026-01-08"
    assert paths[0] == "/old.jpg" and len(paths) == 2


def test_bulletin_update_changes_title_date_and_image(client, db):
    c, tid = client
    with db.cursor() as cur:
        cur.execute("INSERT INTO bulletins (tenant_id, title, date, image_path) VALUES (%s,'틀린 제목','2026-10-04','/uploads/x.png') RETURNING id", (tid,))
        bid = cur.fetchone()[0]
    db.commit()
    r = c.post(f"/admin/bulletin/update/{bid}", data={"title": "", "date": "2026-10-11"},
               files={"image": ("b.png", io.BytesIO(b"x"), "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    with db.cursor() as cur:
        cur.execute("SELECT title, date::text, image_path FROM bulletins WHERE id=%s", (bid,))
        title, date, path = cur.fetchone()
    assert (title, date) == ("2026-10-11 주보", "2026-10-11") and path.startswith(f"/uploads/{tid}/bulletin_2026-10-11_")


def test_admin_page_renders_with_many_news(client, db):
    c, tid = client
    with db.cursor() as cur:
        for i in range(30):
            cur.execute("INSERT INTO news (tenant_id, title, content, date, author) VALUES (%s,%s,'','2026-09-01','boss')", (tid, f"소식 {i}"))
    db.commit()
    r = c.get("/admin")
    assert r.status_code == 200
    assert 'class="admin-quicknav"' in r.text and 'id="news"' in r.text
