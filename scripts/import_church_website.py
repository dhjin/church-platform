"""church-website(단일 교회, SQLite) 데이터를 platform 의 교회(tenant) 하나로 옮긴다.

    python scripts/import_church_website.py --sqlite /data/church.db --uploads /data/uploads \\
        --slug thehaneun --church-name "더하는 교회" --domain thechurch-plus.org --domain www.thechurch-plus.org

- 같은 slug 의 교회가 이미 있으면 멈춘다(--replace 를 주면 그 교회를 지우고 다시 만든다).
- 회원 비밀번호는 해시 그대로 옮기므로 기존 비밀번호로 로그인된다. church-website 의 admin 은 owner 가 된다.
- 업로드 파일은 uploads/<tenant_id>/ 로 복사하고, DB 와 본문 HTML 의 /uploads/ 경로를 바꾼다.
- 기본 실행은 한 트랜잭션이라 중간에 실패하면 DB 는 그대로다(복사된 파일만 남을 수 있음).
"""
import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import site_config  # noqa: E402
from database import get_conn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# church-website 에 하드코딩돼 있던 더하는교회 문구·예배시간(main.py TRANSLATIONS["ko"])
THEHANEUN_CONFIG = {
    "theme": {"preset": "classic", "primary": "#1e3a5f", "accent": "#f4a261", "font": "system", "hero_style": "gradient"},
    "texts": {
        "denomination": "기독교 한국침례회",
        "hero_title": "하나님 나라와 의를 구하는 교회",
        "hero_subtitle": "더하는 교회에 오신 것을 환영합니다",
        "hero_info": "기독교 한국침례회 · 교회 대표 김한기 목사",
        "welcome_title": "환영합니다",
        "mission_title": "교회의 5대 사명",
        "footer_blessing": "하나님의 사랑과 은혜가 함께 하시기를 기도합니다.",
        "pastor_title": "목사",
        "location_short": "대전시 유성구 학하동",
        "email": "muhan52@hanmail.net",
    },
    "home_sections": ["intro", "videos", "schedule_news", "contact"],
    "worship_schedule": [
        {"name": "주일 예배", "time": "일요일 오전 10:40"},
        {"name": "주일 성경공부 및 목장 모임", "time": "일요일 오후 1:00"},
        {"name": "수요 예배", "time": "수요일 오후 7:30 (Zoom)"},
        {"name": "금요 기도회", "time": "금요일 오후 7:30"},
        {"name": "아침 예배", "time": "오전 7:00 (Zoom)"},
    ],
    "en": {
        "texts": {
            "church_name": "Deohaneun Church", "pastor_name": "Hangi Kim",
            "denomination": "Korea Baptist Convention",
            "address": "755-6, Hakha-dong, Yuseong-gu, Daejeon, 1F",
            "location_short": "Hakha-dong, Yuseong-gu, Daejeon",
            "hero_title": "Seeking the Kingdom of God and His Righteousness",
            "hero_subtitle": "Welcome to Deohaneun Church",
            "hero_info": "Korea Baptist Convention · Senior Pastor Rev. Hangi Kim",
        },
        "worship_schedule": [
            {"name": "Sunday Worship", "time": "Sunday 10:40 AM"},
            {"name": "Sunday Bible Study & Small Group", "time": "Sunday 1:00 PM"},
            {"name": "Wednesday Worship", "time": "Wednesday 7:30 PM (Zoom)"},
            {"name": "Friday Prayer Meeting", "time": "Friday 7:30 PM"},
            {"name": "Morning Worship", "time": "7:00 AM (Zoom)"},
        ],
    },
}

# church-website 교회소개 페이지에 박혀 있던 이미지(static/images). 비전 옆 3장 + 사명 옆 1장.
ABOUT_IMAGES = ["gods-vision.png", "mission-structure.png", "our-values.png"]
MISSION_IMAGE = "our-vision.png"

UPLOAD_REF = re.compile(r"/uploads/(?!\d+/)([^\s\"'<>)?#]+)")


def rows(src, table, columns):
    have = {r[1] for r in src.execute(f"PRAGMA table_info({table})")}
    if not have:
        return []
    cols = [c if c in have else f"NULL AS {c}" for c in columns]
    return [dict(zip(columns, r)) for r in src.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id")]


def insert_keeping_ids(cur, tid, table, kind, src_rows, columns, values) -> dict:
    """소식·목양의 窓은 예전 글 주소(/news/3, /pastoral/12)가 그대로 열리도록 가능한 한 같은 id 로 넣는다.
    다른 교회가 이미 쓰는 id 는 새 id 를 받고 legacy_post_ids 에 남겨 예전 주소를 새 주소로 돌려보낸다.
    새 id 는 기존 최대 id 보다 크므로 예전 id 와 겹치지 않는다."""
    cols = ", ".join(["tenant_id"] + columns)
    marks = ", ".join(["%s"] * (len(columns) + 1))
    mapping, collided = {}, []
    for r in src_rows:
        cur.execute(f"SELECT 1 FROM {table} WHERE id=%s", (r["id"],))
        if cur.fetchone():
            collided.append(r)
            continue
        cur.execute(f"INSERT INTO {table} (id, {cols}) VALUES (%s, {marks})", (r["id"], tid, *values(r)))
        mapping[r["id"]] = r["id"]
    cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), GREATEST((SELECT MAX(id) FROM {table}), 1))")
    for r in collided:
        cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING id", (tid, *values(r)))
        mapping[r["id"]] = cur.fetchone()[0]
        cur.execute("INSERT INTO legacy_post_ids (tenant_id, kind, old_id, new_id) VALUES (%s, %s, %s, %s)",
                    (tid, kind, r["id"], mapping[r["id"]]))
    return mapping


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--uploads", required=True, help="church-website 의 uploads 디렉터리")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--church-name", required=True)
    ap.add_argument("--pastor-name", default="김한기")
    ap.add_argument("--phone", default="042-626-0291")
    ap.add_argument("--address", default="대전시 유성구 학하동 755-6 1층")
    ap.add_argument("--domain", action="append", default=[])
    ap.add_argument("--images", default=str(ROOT / "static/images"),
                    help="church-website 의 static/images (logo.png, 교회소개 이미지)")
    ap.add_argument("--target-uploads", default=str(ROOT / "uploads"))
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    src = sqlite3.connect(args.sqlite)
    conn = get_conn()
    cur = conn.cursor()
    with open(ROOT / "init_schema.sql") as f:
        cur.execute(f.read())

    cur.execute("SELECT id FROM tenants WHERE slug=%s", (args.slug,))
    existing = cur.fetchone()
    if existing:
        if not args.replace:
            sys.exit(f"slug '{args.slug}' 교회가 이미 있습니다(id={existing[0]}). 다시 옮기려면 --replace")
        cur.execute("DELETE FROM tenants WHERE id=%s", (existing[0],))

    cur.execute(
        """INSERT INTO tenants (slug, church_name, pastor_name, phone, address, plan, status)
           VALUES (%s, %s, %s, %s, %s, 'premium', 'active') RETURNING id""",
        (args.slug, args.church_name, args.pastor_name, args.phone, args.address),
    )
    tid = cur.fetchone()[0]
    for domain in args.domain:
        cur.execute("INSERT INTO tenant_domains (domain, tenant_id) VALUES (%s, %s)", (domain.lower().strip(), tid))

    # 업로드 파일 복사, 경로 변환
    target = Path(args.target_uploads) / str(tid)
    target.mkdir(parents=True, exist_ok=True)
    src_uploads = Path(args.uploads)
    copied = 0
    for f in src_uploads.rglob("*") if src_uploads.exists() else []:
        if f.is_file():
            dest = target / f.relative_to(src_uploads)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied += 1

    def fix(value):
        return UPLOAD_REF.sub(rf"/uploads/{tid}/\1", value) if isinstance(value, str) else value

    def text(value):
        return fix(value) if value is not None else ""

    # 회원
    user_map = {}
    for u in rows(src, "users", ["id", "username", "password", "role", "created_at", "name", "email"]):
        role = "owner" if u["role"] == "admin" else "user"
        cur.execute(
            """INSERT INTO users (tenant_id, username, password, role, name, email, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (tid, u["username"], u["password"], role, u["name"] or "", u["email"] or "", u["created_at"]),
        )
        user_map[u["id"]] = cur.fetchone()[0]

    for r in rows(src, "church_info", ["id", "content", "updated_at"])[:1]:
        cur.execute("INSERT INTO church_info (tenant_id, content, updated_at) VALUES (%s, %s, %s)",
                    (tid, text(r["content"]), r["updated_at"]))
    for r in rows(src, "church_about", ["id", "vision_title", "vision_content", "mission_content",
                                        "pastoral_direction", "serving_people", "updated_at"])[:1]:
        cur.execute(
            """INSERT INTO church_about (tenant_id, vision_title, vision_content, mission_content,
                                         pastoral_direction, serving_people, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (tid, text(r["vision_title"]), text(r["vision_content"]), text(r["mission_content"]),
             text(r["pastoral_direction"]), text(r["serving_people"]), r["updated_at"]),
        )

    for r in rows(src, "sermons", ["id", "title", "pastor", "date", "description", "youtube_url"]):
        cur.execute("INSERT INTO sermons (tenant_id, title, pastor, date, description, youtube_url) VALUES (%s,%s,%s,%s,%s,%s)",
                    (tid, r["title"], r["pastor"] or "", r["date"], r["description"] or "", r["youtube_url"]))
    for table in ("visions", "shorts", "qtys"):
        for r in rows(src, table, ["id", "title", "youtube_url", "date", "author"]):
            cur.execute(f"INSERT INTO {table} (tenant_id, title, youtube_url, date, author) VALUES (%s,%s,%s,%s,%s)",
                        (tid, r["title"], r["youtube_url"], r["date"], r["author"] or ""))

    news_map = insert_keeping_ids(
        cur, tid, "news", "news", rows(src, "news", ["id", "title", "content", "date", "views", "author", "image_path"]),
        ["title", "content", "date", "views", "author", "image_path"],
        lambda r: (r["title"], text(r["content"]), r["date"], r["views"] or 0, r["author"] or "", fix(r["image_path"])),
    )
    for r in rows(src, "news_images", ["id", "news_id", "image_path", "sort_order"]):
        if r["news_id"] in news_map:
            cur.execute("INSERT INTO news_images (tenant_id, news_id, image_path, sort_order) VALUES (%s,%s,%s,%s)",
                        (tid, news_map[r["news_id"]], fix(r["image_path"]), r["sort_order"] or 0))

    pastoral_map = insert_keeping_ids(
        cur, tid, "pastoral_posts", "pastoral",
        rows(src, "pastoral_posts", ["id", "title", "content", "image_path", "author", "views", "created_at"]),
        ["title", "content", "image_path", "author", "views", "created_at"],
        lambda r: (r["title"], text(r["content"]), fix(r["image_path"]), r["author"] or "", r["views"] or 0, r["created_at"]),
    )
    for r in rows(src, "pastoral_images", ["id", "pastoral_id", "image_path", "sort_order"]):
        if r["pastoral_id"] in pastoral_map:
            cur.execute("INSERT INTO pastoral_images (tenant_id, pastoral_id, image_path, sort_order) VALUES (%s,%s,%s,%s)",
                        (tid, pastoral_map[r["pastoral_id"]], fix(r["image_path"]), r["sort_order"] or 0))

    for r in rows(src, "members", ["id", "name", "role", "bio", "photo_path", "display_order"]):
        cur.execute(
            "INSERT INTO members (tenant_id, name, role, bio, photo_path, display_order) VALUES (%s,%s,%s,%s,%s,%s)",
            (tid, r["name"], r["role"] or "", text(r["bio"]), fix(r["photo_path"]), r["display_order"] or 0),
        )

    post_maps = {"news": news_map, "pastoral": pastoral_map}
    skipped_comments = 0
    for r in rows(src, "comments", ["id", "post_type", "post_id", "user_id", "content", "created_at"]):
        post_id = post_maps.get(r["post_type"], {}).get(r["post_id"])
        user_id = user_map.get(r["user_id"])
        if post_id is None or user_id is None:
            skipped_comments += 1
            continue
        cur.execute(
            "INSERT INTO comments (tenant_id, post_type, post_id, user_id, content, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
            (tid, r["post_type"], post_id, user_id, r["content"], r["created_at"]),
        )

    # 로고와 사이트 설정(문구·예배시간)
    cfg = json.loads(json.dumps(THEHANEUN_CONFIG))
    images = Path(args.images)

    def site_image(name):
        if not (images / name).exists():
            return ""
        shutil.copy2(images / name, target / f"site_{name}")
        return f"/uploads/{tid}/site_{name}"

    cfg["logo_path"] = site_image("logo.png")
    cfg["about_images"] = [p for p in map(site_image, ABOUT_IMAGES) if p]
    cfg["mission_image"] = site_image(MISSION_IMAGE)
    cfg["share_image"] = site_image("og-image.jpg")  # 카카오톡 공유 미리보기
    cfg = site_config.normalize_config(cfg)
    cur.execute(
        """INSERT INTO tenant_site_configs (tenant_id, config, source, note, is_active, created_by)
           VALUES (%s, %s, 'manual', 'church-website 에서 이전', TRUE, 'import')""",
        (tid, json.dumps(cfg, ensure_ascii=False)),
    )

    conn.commit()
    conn.close()
    print(json.dumps({
        "tenant_id": tid, "slug": args.slug, "domains": args.domain, "users": len(user_map),
        "news": len(news_map), "pastoral_posts": len(pastoral_map), "files_copied": copied,
        "ids_changed": sum(old != new for m in (news_map, pastoral_map) for old, new in m.items()),
        "comments_skipped": skipped_comments,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
