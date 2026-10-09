"""교회별 사이트 설정(테마·홈 섹션 구성·문구).

설정은 tenant_site_configs 테이블에 JSON으로 버전별로 저장한다. is_active 인 행이 실제 사이트에 쓰이고,
나머지는 이전 버전이거나 AI가 만든 미리보기 초안이다. 템플릿은 정해진 섹션 부품만 조합하고,
설정값은 normalize_config()를 통과한 값(허용된 키, 색상 hex, 길이 제한)만 쓴다.
"""
import copy
import json
import re
from typing import Optional

from database import get_conn

# 테마 카탈로그. 교회가 미리보기 후 한 번에 적용할 수 있는 완성된 조합(색·글꼴·히어로 스타일·홈 섹션 순서).
# 적용해도 교회 이름·문구·예배 시간 같은 내용은 바뀌지 않는다.
THEME_PRESETS = {
    "classic": {
        "label": "클래식 네이비", "description": "신뢰감 있는 남색과 따뜻한 오렌지. 전통적인 교회에 어울리는 기본 테마.",
        "primary": "#1e3a5f", "accent": "#f4a261", "font": "noto-sans", "hero_style": "gradient",
        "home_sections": ["intro", "videos", "schedule_news", "contact"],
    },
    "warm": {
        "label": "따뜻한 브라운", "description": "나무와 흙빛 톤의 아늑한 분위기. 가족 중심, 지역 공동체 교회에 추천.",
        "primary": "#6b3a2a", "accent": "#e9a23b", "font": "gowun-dodum", "hero_style": "solid",
        "home_sections": ["intro", "schedule_news", "videos", "contact"],
    },
    "forest": {
        "label": "포레스트 그린", "description": "생명과 성장을 떠올리게 하는 초록과 금색. 개척·전원 교회에 추천.",
        "primary": "#1f5130", "accent": "#c9a227", "font": "noto-serif", "hero_style": "gradient",
        "home_sections": ["intro", "schedule_news", "contact", "videos"],
    },
    "modern": {
        "label": "모던 차콜", "description": "차콜과 청록의 깔끔한 대비. 청년·도심 교회, 영상 사역 중심 교회에 추천.",
        "primary": "#222831", "accent": "#00adb5", "font": "noto-sans", "hero_style": "solid",
        "home_sections": ["videos", "intro", "schedule_news", "contact"],
    },
    "grace": {
        "label": "은혜 퍼플", "description": "보랏빛과 분홍의 부드러운 조합. 예배·찬양 사역을 강조하는 교회에 추천.",
        "primary": "#4b3f72", "accent": "#f2a7c3", "font": "nanum-myeongjo", "hero_style": "gradient",
        "home_sections": ["intro", "videos", "schedule_news", "contact"],
    },
    "sky": {
        "label": "하늘 블루", "description": "밝은 하늘색과 노랑의 경쾌한 조합. 다음세대·주일학교 사역 교회에 추천.",
        "primary": "#1b6ca8", "accent": "#ffc857", "font": "jua", "hero_style": "light",
        "home_sections": ["intro", "schedule_news", "videos", "contact"],
    },
    "minimal": {
        "label": "미니멀 화이트", "description": "흰 배경에 검정 포인트만 쓴 단정한 디자인. 글과 말씀을 돋보이게 합니다.",
        "primary": "#2b2b2b", "accent": "#b08d57", "font": "noto-serif", "hero_style": "light",
        "home_sections": ["intro", "schedule_news", "videos", "contact"],
    },
}

HERO_STYLES = {"gradient": "그라데이션", "solid": "단색", "light": "밝은 배경"}

FONTS = {
    "noto-sans": {"label": "본고딕 (기본)", "family": "'Noto Sans KR', sans-serif", "google": "Noto+Sans+KR:wght@400;500;700"},
    "noto-serif": {"label": "본명조 (차분한)", "family": "'Noto Serif KR', serif", "google": "Noto+Serif+KR:wght@400;600;700"},
    "nanum-myeongjo": {"label": "나눔명조 (전통적인)", "family": "'Nanum Myeongjo', serif", "google": "Nanum+Myeongjo:wght@400;700;800"},
    "gowun-dodum": {"label": "고운돋움 (부드러운)", "family": "'Gowun Dodum', sans-serif", "google": "Gowun+Dodum"},
    "jua": {"label": "주아 (밝고 친근한)", "family": "'Jua', sans-serif", "google": "Jua"},
}

# 홈 화면에서 순서를 바꾸거나 숨길 수 있는 섹션. 히어로는 항상 맨 위에 고정.
HOME_SECTIONS = {
    "intro": "교회 비전 영상 + 환영 인사",
    "videos": "설교·QT·숏츠 영상",
    "schedule_news": "예배 시간 + 교회소식",
    "contact": "찾아오시는 길(지도)",
}

TEXT_LIMITS = {
    "denomination": 60,
    "hero_title": 80,
    "hero_subtitle": 120,
    "hero_info": 200,
    "welcome_title": 40,
    "mission_title": 40,
    "footer_blessing": 200,
    "concept": 600,
}

MAX_SCHEDULE_ROWS = 10
MAX_ABOUT_IMAGES = 4

DEFAULT_CONFIG = {
    "theme": {"preset": "classic", "primary": "#1e3a5f", "accent": "#f4a261", "font": "noto-sans", "hero_style": "gradient"},
    "texts": {
        "denomination": "",
        "hero_title": "하나님 나라와 의를 구하는 교회",
        "hero_subtitle": "오신 것을 환영합니다",
        "hero_info": "",
        "welcome_title": "환영합니다",
        "mission_title": "교회의 사명",
        "footer_blessing": "하나님의 사랑과 은혜가 함께 하시기를 기도합니다.",
        "concept": "",
    },
    "home_sections": ["intro", "videos", "schedule_news", "contact"],
    "worship_schedule": [
        {"name": "주일 예배", "time": "일요일 오전 11:00"},
        {"name": "수요 예배", "time": "수요일 오후 7:30"},
        {"name": "금요 기도회", "time": "금요일 오후 8:00"},
    ],
    "logo_path": "",
    "about_images": [],
}

# AI가 설정안을 만들 때 쓰는 JSON 스키마(구조화 출력). 이미지 경로는 AI가 정하지 않는다.
AI_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {"type": "string", "description": "이 디자인안의 컨셉 설명(2~3문장)"},
        "theme": {
            "type": "object",
            "properties": {
                "preset": {"type": "string", "enum": list(THEME_PRESETS)},
                "primary": {"type": "string", "description": "#rrggbb"},
                "accent": {"type": "string", "description": "#rrggbb"},
                "font": {"type": "string", "enum": list(FONTS)},
                "hero_style": {"type": "string", "enum": list(HERO_STYLES)},
            },
            "required": ["preset", "primary", "accent", "font", "hero_style"],
            "additionalProperties": False,
        },
        "texts": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in TEXT_LIMITS if k != "concept"},
            "required": [k for k in TEXT_LIMITS if k != "concept"],
            "additionalProperties": False,
        },
        "home_sections": {"type": "array", "items": {"type": "string", "enum": list(HOME_SECTIONS)}},
        "worship_schedule": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "time": {"type": "string"}},
                "required": ["name", "time"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["concept", "theme", "texts", "home_sections", "worship_schedule"],
    "additionalProperties": False,
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_UPLOAD_PATH = re.compile(r"^/uploads/\d+/[A-Za-z0-9_.-]+$")


def _clean_text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def normalize_config(raw: Optional[dict], base: Optional[dict] = None) -> dict:
    """raw 를 base(기본값: DEFAULT_CONFIG) 위에 덮어쓰고, 허용되지 않은 값은 버린다."""
    cfg = copy.deepcopy(base if base is not None else DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return cfg

    theme = raw.get("theme")
    if isinstance(theme, dict):
        if theme.get("preset") in THEME_PRESETS:
            cfg["theme"]["preset"] = theme["preset"]
        for key in ("primary", "accent"):
            if isinstance(theme.get(key), str) and _HEX.match(theme[key]):
                cfg["theme"][key] = theme[key].lower()
        if theme.get("font") in FONTS:
            cfg["theme"]["font"] = theme["font"]
        if theme.get("hero_style") in HERO_STYLES:
            cfg["theme"]["hero_style"] = theme["hero_style"]

    texts = raw.get("texts")
    if isinstance(texts, dict):
        for key, limit in TEXT_LIMITS.items():
            if key in texts:
                cfg["texts"][key] = _clean_text(texts[key], limit)
    if "concept" in raw:
        cfg["texts"]["concept"] = _clean_text(raw["concept"], TEXT_LIMITS["concept"])

    sections = raw.get("home_sections")
    if isinstance(sections, list):
        seen = []
        for s in sections:
            if s in HOME_SECTIONS and s not in seen:
                seen.append(s)
        cfg["home_sections"] = seen

    schedule = raw.get("worship_schedule")
    if isinstance(schedule, list):
        rows = []
        for row in schedule[:MAX_SCHEDULE_ROWS]:
            if not isinstance(row, dict):
                continue
            name, time = _clean_text(row.get("name"), 40), _clean_text(row.get("time"), 40)
            if name:
                rows.append({"name": name, "time": time})
        cfg["worship_schedule"] = rows

    if "logo_path" in raw:
        logo = raw["logo_path"]
        cfg["logo_path"] = logo if isinstance(logo, str) and _UPLOAD_PATH.match(logo) else ""
    images = raw.get("about_images")
    if isinstance(images, list):
        cfg["about_images"] = [p for p in images if isinstance(p, str) and _UPLOAD_PATH.match(p)][:MAX_ABOUT_IMAGES]
    return cfg


def apply_catalog_theme(cfg: dict, preset: str) -> dict:
    """카탈로그 테마의 디자인 요소만 cfg 에 적용한다(문구·예배 시간·이미지는 그대로)."""
    item = THEME_PRESETS[preset]
    return normalize_config({
        "theme": {"preset": preset, "primary": item["primary"], "accent": item["accent"],
                  "font": item["font"], "hero_style": item["hero_style"]},
        "home_sections": item["home_sections"],
    }, base=cfg)


# ─── 색상 ────────────────────────────────────────────────────────────────────

def _mix(hex_color: str, other: str, ratio: float) -> str:
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * ratio):02x}" for x, y in zip(a, b))


def theme_css(cfg: dict) -> str:
    """style.css 의 CSS 변수를 덮어쓰는 :root 블록. 값은 normalize_config 를 거친 hex 뿐이다."""
    theme = cfg["theme"]
    primary, accent = theme["primary"], theme["accent"]
    font = FONTS.get(theme["font"], FONTS["noto-sans"])["family"]
    return (
        ":root{"
        f"--primary-color:{primary};"
        f"--primary-light:{_mix(primary, '#ffffff', 0.2)};"
        f"--primary-lighter:{_mix(primary, '#ffffff', 0.45)};"
        f"--primary-dark:{_mix(primary, '#000000', 0.3)};"
        f"--accent-color:{accent};"
        f"--accent-hover:{_mix(accent, '#000000', 0.15)};"
        f"--accent-light:{_mix(accent, '#ffffff', 0.55)};"
        "}"
        f"body{{font-family:{font},-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif}}"
        + _HERO_CSS.get(theme.get("hero_style", "gradient"), "")
    )


_HERO_CSS = {
    "gradient": "",
    "solid": ".hero{background:var(--primary-color)}",
    "light": (".hero{background:linear-gradient(180deg,var(--accent-light) 0%,#ffffff 100%);color:var(--primary-dark)}"
              ".hero .hero-title,.hero .hero-subtitle,.hero .hero-info{color:var(--primary-dark)}"
              ".hero .btn-secondary{color:var(--primary-color);border-color:var(--primary-color)}"),
}


def font_href(cfg: dict) -> str:
    font = FONTS.get(cfg["theme"]["font"], FONTS["noto-sans"])
    return f"https://fonts.googleapis.com/css2?family={font['google']}&display=swap"


# ─── 저장소 ──────────────────────────────────────────────────────────────────

def _row_to_config(row) -> dict:
    data = row if isinstance(row, dict) else json.loads(row)
    return normalize_config(data)


def load_active_config(tenant_id: int) -> dict:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config FROM tenant_site_configs WHERE tenant_id=%s AND is_active ORDER BY id DESC LIMIT 1",
                (tenant_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return _row_to_config(row[0]) if row else normalize_config(None)


def load_version(tenant_id: int, version_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config FROM tenant_site_configs WHERE tenant_id=%s AND id=%s",
                (tenant_id, version_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return _row_to_config(row[0]) if row else None


def save_version(tenant_id: int, cfg: dict, source: str, note: str = "", activate: bool = True,
                 created_by: Optional[str] = None) -> int:
    cfg = normalize_config(cfg)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if activate:
                cur.execute("UPDATE tenant_site_configs SET is_active=FALSE WHERE tenant_id=%s AND is_active", (tenant_id,))
            cur.execute(
                """INSERT INTO tenant_site_configs (tenant_id, config, source, note, is_active, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (tenant_id, json.dumps(cfg, ensure_ascii=False), source, note[:200], activate, created_by),
            )
            version_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return version_id


def activate_version(tenant_id: int, version_id: int) -> bool:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tenant_site_configs WHERE tenant_id=%s AND id=%s", (tenant_id, version_id))
            if not cur.fetchone():
                return False
            cur.execute("UPDATE tenant_site_configs SET is_active=FALSE WHERE tenant_id=%s AND is_active", (tenant_id,))
            cur.execute("UPDATE tenant_site_configs SET is_active=TRUE WHERE tenant_id=%s AND id=%s", (tenant_id, version_id))
        conn.commit()
    finally:
        conn.close()
    return True


def list_versions(tenant_id: int, limit: int = 20) -> list:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, source, note, is_active, created_by, created_at FROM tenant_site_configs
                   WHERE tenant_id=%s ORDER BY id DESC LIMIT %s""",
                (tenant_id, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "source": r[1], "note": r[2], "is_active": r[3], "created_by": r[4], "created_at": r[5]}
        for r in rows
    ]
