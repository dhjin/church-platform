import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import psycopg2

import middleware
import site_config

ROOT = Path(__file__).resolve().parent.parent


def _tenant(conn, slug):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, church_name) VALUES (%s, %s) RETURNING id", (slug, slug))
        tid = cur.fetchone()[0]
    conn.commit()
    return tid


def test_custom_domain_wins_over_slug(db, monkeypatch):
    monkeypatch.setattr(middleware, "get_conn", lambda: psycopg2.connect(db.dsn))
    a, www = _tenant(db, "a"), _tenant(db, "www")
    with db.cursor() as cur:
        cur.execute("INSERT INTO tenant_domains (domain, tenant_id) VALUES ('example.org', %s), ('www.example.org', %s)", (a, a))
    db.commit()
    assert middleware._lookup_tenant("example.org", None)["id"] == a
    assert middleware._lookup_tenant("www.example.org", "www")["id"] == a  # 'www' slug 교회보다 도메인 우선
    assert middleware._lookup_tenant("a.thechurch-plus.org", "a")["id"] == a
    assert middleware._lookup_tenant("platform.thechurch-plus.org", "platform") is None
    assert middleware._lookup_tenant("other.org", None) is None


def test_profile_and_english_texts_normalized():
    cfg = site_config.normalize_config({
        "texts": {"pastor_title": "목사", "email": "a@b.kr", "location_short": "x" * 500},
        "mission_image": "/uploads/1/m.png",
        "en": {"texts": {"church_name": "Plus Church", "bogus": "y", "hero_title": ""},
               "worship_schedule": [{"name": "Sunday", "time": "11 AM"}, {"name": ""}]},
    })
    assert cfg["texts"]["pastor_title"] == "목사"
    assert len(cfg["texts"]["location_short"]) == site_config.PROFILE_TEXT_LIMITS["location_short"]
    assert cfg["mission_image"] == "/uploads/1/m.png"
    assert cfg["en"]["texts"] == {"church_name": "Plus Church"}
    assert cfg["en"]["worship_schedule"] == [{"name": "Sunday", "time": "11 AM"}]
    assert "pastor_title" not in site_config.AI_CONFIG_SCHEMA["properties"]["texts"]["properties"]
    assert site_config.normalize_config({"mission_image": "https://evil/x.png"})["mission_image"] == ""


def test_default_colors_keep_style_css_palette():
    css = site_config.theme_css(site_config.normalize_config({"theme": {"font": "system"}}))
    assert "--primary" not in css and "--accent" not in css
    assert site_config.font_href(site_config.normalize_config({"theme": {"font": "system"}})) == ""
    assert "--primary-color:#222831" in site_config.theme_css(site_config.apply_catalog_theme(site_config.normalize_config(None), "modern"))


def _website_db(path: Path, uploads: Path):
    uploads.mkdir()
    (uploads / "p.png").write_bytes(b"png")
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, created_at TEXT, name TEXT, email TEXT);
        CREATE TABLE church_info (id INTEGER PRIMARY KEY, content TEXT, updated_at TEXT);
        CREATE TABLE church_about (id INTEGER PRIMARY KEY, vision_title TEXT, vision_content TEXT, mission_content TEXT,
                                   pastoral_direction TEXT, serving_people TEXT, updated_at TEXT);
        CREATE TABLE news (id INTEGER PRIMARY KEY, title TEXT, content TEXT, date TEXT, views INTEGER, author TEXT, image_path TEXT);
        CREATE TABLE pastoral_posts (id INTEGER PRIMARY KEY, title TEXT, content TEXT, image_path TEXT, author TEXT, views INTEGER, created_at TEXT);
        CREATE TABLE comments (id INTEGER PRIMARY KEY, post_type TEXT, post_id INTEGER, user_id INTEGER, content TEXT, created_at TEXT);
        INSERT INTO users VALUES (5, 'admin', '$2b$12$hash', 'admin', '2026-01-01', '', ''), (9, 'kim@x.kr', '$2b$12$h2', 'user', '2026-02-01', '김', 'kim@x.kr');
        INSERT INTO church_info VALUES (1, '환영', '2026-01-01');
        INSERT INTO church_about VALUES (1, '비전', '내용', '사명', '', '', '2026-01-01');
        INSERT INTO news VALUES (7, '소식', '본문', '2026-03-01', 3, '관리자', NULL);
        INSERT INTO pastoral_posts VALUES (3, '편지', '<img src="/uploads/p.png">', '/uploads/p.png', '목사', 1, '2026-03-02');
        INSERT INTO comments VALUES (1, 'news', 7, 9, '아멘', '2026-03-03'), (2, 'pastoral', 3, 99, '고아', '2026-03-03');
    """)
    c.commit()
    c.close()


def test_import_church_website(db, tmp_path):
    _website_db(tmp_path / "church.db", tmp_path / "uploads")
    other = _tenant(db, "other")
    with db.cursor() as cur:  # 다른 교회가 이미 news id 7 을 쓰고 있다 → 이 글만 새 id
        cur.execute("INSERT INTO news (id, tenant_id, title, date) VALUES (7, %s, '남의 글', '2026-01-01')", (other,))
    db.commit()
    target = tmp_path / "plat_uploads"
    cmd = [sys.executable, str(ROOT / "scripts/import_church_website.py"), "--sqlite", str(tmp_path / "church.db"),
           "--uploads", str(tmp_path / "uploads"), "--slug", "plus", "--church-name", "더하는 교회",
           "--domain", "Example.org", "--target-uploads", str(target)]
    env = {"DATABASE_URL": db.dsn, "PATH": "/usr/bin:/bin"}
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    tid = result["tenant_id"]
    assert result["comments_skipped"] == 1
    assert result["ids_changed"] == 1

    with db.cursor() as cur:
        cur.execute("SELECT domain FROM tenant_domains WHERE tenant_id=%s", (tid,))
        assert cur.fetchall() == [("example.org",)]
        cur.execute("SELECT username, password, role FROM users WHERE tenant_id=%s ORDER BY id", (tid,))
        assert cur.fetchall() == [("admin", "$2b$12$hash", "owner"), ("kim@x.kr", "$2b$12$h2", "user")]
        cur.execute("SELECT id, content, image_path FROM pastoral_posts WHERE tenant_id=%s", (tid,))
        assert cur.fetchone() == (3, f'<img src="/uploads/{tid}/p.png">', f"/uploads/{tid}/p.png")  # 예전 id 유지
        cur.execute("SELECT id FROM news WHERE tenant_id=%s", (tid,))
        new_news_id = cur.fetchone()[0]
        assert new_news_id > 7
        cur.execute("SELECT kind, old_id, new_id FROM legacy_post_ids WHERE tenant_id=%s", (tid,))
        assert cur.fetchall() == [("news", 7, new_news_id)]
        cur.execute("INSERT INTO news (tenant_id, title, date) VALUES (%s, '다음 글', '2026-04-01') RETURNING id", (tid,))
        assert cur.fetchone()[0] > new_news_id  # 시퀀스가 옮긴 id 뒤로 맞춰졌다
        cur.execute("""SELECT c.content, n.title, u.username FROM comments c JOIN news n ON n.id = c.post_id
                       JOIN users u ON u.id = c.user_id WHERE c.tenant_id=%s""", (tid,))
        assert cur.fetchall() == [("아멘", "소식", "kim@x.kr")]
        cur.execute("SELECT config FROM tenant_site_configs WHERE tenant_id=%s AND is_active", (tid,))
        cfg = site_config.normalize_config(cur.fetchone()[0])
    assert cfg["texts"]["denomination"] == "기독교 한국침례회"
    assert cfg["logo_path"] == f"/uploads/{tid}/site_logo.png"
    assert len(cfg["about_images"]) == 3 and cfg["mission_image"]
    assert cfg["share_image"] == f"/uploads/{tid}/site_og-image.jpg"
    assert (target / str(tid) / "p.png").exists()

    db.commit()  # 열린 읽기 트랜잭션이 스크립트의 스키마 적용을 막지 않도록
    again = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)
    assert again.returncode != 0 and "--replace" in again.stderr


def test_old_upload_paths_redirect_into_tenant_folder():
    assert middleware._OLD_UPLOAD.match("/uploads/news_abc.jpg")
    assert not middleware._OLD_UPLOAD.match("/uploads/3/news_abc.jpg")
    assert not middleware._OLD_UPLOAD.match("/uploads/../etc/passwd")
