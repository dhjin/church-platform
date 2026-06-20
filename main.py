from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import psycopg2
import psycopg2.errors
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import bcrypt
import secrets
import shutil
import re
import os
from typing import Optional, List
from pydantic import BaseModel
from dotenv import load_dotenv

from elasticsearch import Elasticsearch

from database import get_conn
from middleware import TenantMiddleware

load_dotenv()

app = FastAPI(title="Church Platform")
app.add_middleware(TenantMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

UPLOAD_BASE = Path("uploads")
UPLOAD_BASE.mkdir(exist_ok=True)

sessions: dict = {}
platform_sessions: dict = {}

ES_URL = os.getenv("ES_URL", "http://elasticsearch:9200")
es = Elasticsearch(ES_URL)
ES_INDEX = "theology_articles"

LANDING_HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>교회 플랫폼 — 30일 무료 시작</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Tahoma,sans-serif;background:#f0f4f8;color:#333}
.hero{background:linear-gradient(135deg,#1e3a5f,#2d6a9f);color:#fff;padding:64px 20px 48px;text-align:center}
.hero h1{font-size:2.2rem;margin-bottom:.8rem}
.hero p{font-size:1.05rem;opacity:.9;margin-bottom:0}
.features{max-width:860px;margin:40px auto 0;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px}
.card{background:rgba(255,255,255,.12);border-radius:10px;padding:20px;text-align:center}
.card h3{font-size:.95rem;margin-top:.4rem}
.card .icon{font-size:1.6rem}
.section{max-width:520px;margin:48px auto;padding:0 20px}
.section h2{font-size:1.3rem;color:#1e3a5f;margin-bottom:4px}
.section p.sub{font-size:.88rem;color:#666;margin-bottom:24px}
.form-wrap{background:#fff;border-radius:14px;padding:32px;box-shadow:0 4px 20px rgba(0,0,0,.08)}
.field{margin-bottom:18px}
label{display:block;font-size:.82rem;font-weight:600;color:#555;margin-bottom:6px}
input{width:100%;padding:10px 12px;border:1.5px solid #d1d9e0;border-radius:8px;font-size:.95rem;outline:none;transition:border .2s}
input:focus{border-color:#2d6a9f}
input.error{border-color:#e53e3e}
.slug-wrap{display:flex;align-items:center;gap:0}
.slug-pre{background:#f0f4f8;border:1.5px solid #d1d9e0;border-right:none;border-radius:8px 0 0 8px;padding:10px 10px;font-size:.8rem;color:#888;white-space:nowrap}
.slug-wrap input{border-radius:0 8px 8px 0;border-left:none}
.slug-suf{background:#f0f4f8;border:1.5px solid #d1d9e0;border-left:none;border-radius:0 8px 8px 0;padding:10px 8px;font-size:.78rem;color:#888;white-space:nowrap}
.slug-wrap2{display:flex;align-items:center}
.slug-wrap2 input{border-radius:8px 0 0 8px}
.divider{border:none;border-top:1px solid #eee;margin:22px 0}
.btn{width:100%;padding:13px;background:#1e3a5f;color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;transition:background .2s;margin-top:4px}
.btn:hover{background:#2d6a9f}
.btn:disabled{background:#aaa;cursor:not-allowed}
.msg{margin-top:16px;padding:12px 16px;border-radius:8px;font-size:.9rem;display:none}
.msg.success{background:#e6f4ea;color:#1a6b2e;display:block}
.msg.error{background:#fde8e8;color:#9b1c1c;display:block}
.msg a{color:#1e3a5f;font-weight:600}
.hint{font-size:.78rem;color:#888;margin-top:4px}
.footer{text-align:center;padding:32px 20px;color:#999;font-size:.82rem}
</style></head><body>

<div class="hero">
  <h1>✝ 교회 플랫폼</h1>
  <p>귀 교회만의 웹사이트를 30일 무료로 시작하세요</p>
  <div class="features">
    <div class="card"><div class="icon">🌐</div><h3>전용 서브도메인</h3></div>
    <div class="card"><div class="icon">🎬</div><h3>설교·영상 관리</h3></div>
    <div class="card"><div class="icon">📰</div><h3>소식 &amp; 목양의 창</h3></div>
    <div class="card"><div class="icon">💝</div><h3>온라인 헌금 연동</h3></div>
  </div>
</div>

<div class="section">
  <h2>교회 등록</h2>
  <p class="sub">카드 없이 즉시 시작 · 30일 무료 체험</p>
  <div class="form-wrap">
    <div class="field">
      <label>교회명 *</label>
      <input id="church_name" type="text" placeholder="세종침례교회">
    </div>
    <div class="field">
      <label>웹사이트 주소 (slug) *</label>
      <div class="slug-wrap2">
        <input id="slug" type="text" placeholder="sejong" style="border-radius:8px 0 0 8px">
        <div class="slug-suf">.thechurch-plus.org</div>
      </div>
      <div class="hint">소문자·숫자·하이픈만 사용 (예: sejong-church)</div>
    </div>
    <div class="field">
      <label>담임목사명</label>
      <input id="pastor_name" type="text" placeholder="홍길동">
    </div>
    <div class="field">
      <label>연락처</label>
      <input id="phone" type="text" placeholder="010-1234-5678">
    </div>
    <div class="field">
      <label>주소</label>
      <input id="address" type="text" placeholder="세종시 조치원읍 ...">
    </div>
    <hr class="divider">
    <div class="field">
      <label>관리자 아이디 *</label>
      <input id="admin_username" type="text" placeholder="admin">
    </div>
    <div class="field">
      <label>관리자 비밀번호 * <span style="font-weight:400">(8자 이상)</span></label>
      <input id="admin_password" type="password" placeholder="••••••••">
    </div>
    <div class="field">
      <label>비밀번호 확인 *</label>
      <input id="admin_password2" type="password" placeholder="••••••••">
    </div>
    <div class="field">
      <label>초대 코드 *</label>
      <input id="invite_code" type="text" placeholder="운영자에게 발급받은 코드 입력">
    </div>
    <button class="btn" id="submitBtn" onclick="submitForm()">30일 무료 시작하기</button>
    <div class="msg" id="msg"></div>
  </div>
</div>

<div class="section" style="margin-top:0;margin-bottom:32px">
  <div class="form-wrap" style="background:#f8fafc;box-shadow:none;border:1.5px solid #e2e8f0">
    <h3 style="color:#1e3a5f;margin-bottom:12px;font-size:1rem">서비스 이용 안내</h3>
    <ul style="font-size:.85rem;color:#555;line-height:1.9;padding-left:1.2em">
      <li><b>기본 도메인:</b> <code>{slug}.thechurch-plus.org</code> — 무료 제공</li>
      <li><b>독립 도메인 사용 시:</b> 도메인 구매·갱신 비용은 별도 부담 (연 단위, 도메인 종류에 따라 상이)</li>
      <li><b>월 구독료:</b> 30일 무료 체험 후 월 19,000원</li>
      <li><b>초대 코드:</b> 현재 초대 코드를 받은 교회만 등록 가능합니다. 문의: 운영자에게 연락해 주세요.</li>
    </ul>
  </div>
</div>

<div class="footer">
  <p>이미 등록하셨나요? <a href="#" onclick="goLogin()" style="color:#1e3a5f;font-weight:600">내 교회 사이트로 이동 →</a></p>
  <p style="margin-top:8px">&copy; 2026 Church Platform · 월 19,000원 구독 (30일 무료 후)</p>
</div>

<script>
function goLogin() {
  const slug = prompt('교회 slug를 입력하세요 (예: sejong):');
  if (slug) location.href = 'https://' + slug.trim() + '.thechurch-plus.org/login';
}

async function submitForm() {
  const btn = document.getElementById('submitBtn');
  const msg = document.getElementById('msg');
  msg.className = 'msg'; msg.style.display = 'none';

  const church_name = document.getElementById('church_name').value.trim();
  const slug = document.getElementById('slug').value.trim().toLowerCase();
  const pastor_name = document.getElementById('pastor_name').value.trim();
  const phone = document.getElementById('phone').value.trim();
  const address = document.getElementById('address').value.trim();
  const admin_username = document.getElementById('admin_username').value.trim();
  const admin_password = document.getElementById('admin_password').value;
  const admin_password2 = document.getElementById('admin_password2').value;
  const invite_code = document.getElementById('invite_code').value.trim();

  if (!church_name || !slug || !admin_username || !admin_password || !invite_code) {
    msg.className = 'msg error'; msg.textContent = '필수 항목(*)을 모두 입력해주세요.'; return;
  }
  if (!/^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$/.test(slug)) {
    msg.className = 'msg error'; msg.textContent = 'slug는 소문자·숫자·하이픈 3~30자, 영숫자로 시작·끝나야 합니다.'; return;
  }
  if (admin_password.length < 8) {
    msg.className = 'msg error'; msg.textContent = '비밀번호는 8자 이상이어야 합니다.'; return;
  }
  if (admin_password !== admin_password2) {
    msg.className = 'msg error'; msg.textContent = '비밀번호가 일치하지 않습니다.'; return;
  }

  btn.disabled = true; btn.textContent = '등록 중...';
  try {
    const res = await fetch('/api/register-tenant', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({slug, church_name, pastor_name, phone, address, admin_username, admin_password, invite_code})
    });
    const data = await res.json();
    if (!res.ok) {
      msg.className = 'msg error'; msg.textContent = data.detail || '등록 실패. 다시 시도해주세요.';
    } else {
      const url = 'https://' + slug + '.thechurch-plus.org';
      msg.className = 'msg success';
      msg.innerHTML = '🎉 등록 완료! <a href="' + url + '">' + url + '</a> 에서 지금 바로 시작하세요.';
    }
  } catch(e) {
    msg.className = 'msg error'; msg.textContent = '네트워크 오류. 잠시 후 다시 시도해주세요.';
  } finally {
    btn.disabled = false; btn.textContent = '30일 무료 시작하기';
  }
}
</script>
</body></html>"""

TRANSLATIONS = {
    "ko": {
        "lang": "ko", "lang_name": "한국어", "other_lang": "en", "other_lang_name": "English",
        "church_name": "교회", "church_name_full": "교회", "denomination": "",
        "senior_pastor": "", "senior_pastor_short": "", "pastor_label": "",
        "nav_home": "홈", "nav_about": "교회소개", "nav_direction": "목회방향",
        "nav_vision": "비전과 가치", "nav_schedule": "예배시간 안내", "nav_location": "찾아오시는 길",
        "nav_people": "섬기는 분들", "nav_videos": "영상", "nav_church_vision": "교회 비전",
        "nav_sermons": "최근설교", "nav_shorts": "숏츠", "nav_qt": "오늘의 QT",
        "nav_pastoral": "목양의 窓", "nav_worship": "예배안내", "nav_news": "교회소식",
        "nav_admin": "관리자", "nav_logout": "로그아웃", "nav_login": "로그인",
        "hero_title": "하나님 나라와 의를 구하는 교회", "hero_subtitle": "오신 것을 환영합니다",
        "hero_info": "", "hero_worship_btn": "예배 안내", "hero_about_btn": "교회 소개",
        "welcome_title": "환영합니다", "info_affiliation": "소속:", "info_pastor": "교회대표:",
        "info_location": "위치:", "info_location_val": "",
        "tab_vision": "교회 비전", "tab_sermons": "최근설교", "tab_shorts": "숏츠", "tab_qt": "오늘의 QT",
        "prev_video": "이전영상", "next_video": "다음영상",
        "schedule_title": "예배 시간 안내", "news_title": "교회소식",
        "sunday_worship": "주일 예배", "sunday_time": "일요일 오전 10:40",
        "sunday_study": "주일 성경공부 및 목장 모임", "sunday_study_time": "일요일 오후 1:00",
        "wed_worship": "수요 예배", "wed_time": "수요일 오후 7:30",
        "fri_prayer": "금요 기도회", "fri_time": "금요일 오후 7:30",
        "morning_worship": "아침 예배", "morning_time": "오전 7:00",
        "news_col_num": "번호", "news_col_title": "제목", "news_col_date": "작성일", "news_col_views": "조회",
        "contact_title": "찾아오시는 길", "naver_map": "네이버 지도로 길찾기", "kakao_map": "카카오맵으로 길찾기",
        "footer_address_label": "주소", "footer_address": "", "footer_tel": "",
        "footer_copyright": "&copy; 2026. All rights reserved.",
        "footer_blessing": "하나님의 사랑과 은혜가 함께 하시기를 기도합니다.",
        "footer_email": "", "footer_phone": "",
        "about_title": "교회소개", "mission_5_title": "교회의 5대 사명",
        "direction_title": "목회방향", "direction_preparing": "준비 중입니다.",
        "people_title": "섬기는 분들", "people_preparing": "준비 중입니다.",
        "pastoral_title": "목양의 窓", "pastoral_subtitle": "말씀을 삶으로 살아가며 나누는 목양의 기록입니다.",
        "pastoral_search_placeholder": "제목 또는 내용으로 검색...", "pastoral_search_btn": "검색",
        "pastoral_search_result": "검색 결과", "pastoral_all_list": "전체 목록",
        "pastoral_col_title": "제목", "pastoral_col_date": "날짜",
        "pastoral_col_author": "작성자", "pastoral_col_views": "조회",
        "pastoral_empty": "아직 게시글이 없습니다.", "pastoral_no_result": "에 대한 검색 결과가 없습니다.",
        "pastoral_prev": "&laquo; 이전", "pastoral_next": "다음 &raquo;",
        "pastoral_back": "&larr; 목록으로 돌아가기",
        "pastoral_author_label": "&#128221; 작성자:", "pastoral_date_label": "&#128197; 작성일:",
        "pastoral_views_label": "&#128065; 조회수:", "pastoral_default_author": "관리자",
        "comments_title": "댓글", "no_comments": "아직 댓글이 없습니다.",
        "comment_placeholder": "댓글을 입력하세요...", "comment_submit": "댓글 작성",
        "comment_login_prompt": "댓글을 작성하려면", "comment_login_link": "로그인",
        "comment_login_suffix": "해 주세요.", "comment_delete": "삭제",
        "comment_delete_confirm": "댓글을 삭제하시겠습니까?",
        "news_author_label": "작성자:", "news_date_label": "작성일:", "news_views_label": "조회수:",
        "news_back": "&larr; 목록으로 돌아가기", "news_default_author": "관리자",
        "login_title": "로그인", "login_username": "이메일", "login_password": "비밀번호",
        "login_button": "로그인", "login_no_account": "계정이 없으신가요?",
        "login_register_link": "회원가입", "login_back": "&larr; 메인 페이지로 돌아가기",
        "login_error": "아이디 또는 비밀번호가 올바르지 않습니다.",
        "register_title": "회원가입", "register_name": "이름", "register_email": "이메일",
        "register_username": "아이디", "register_password": "비밀번호",
        "register_password_confirm": "비밀번호 확인", "register_button": "회원가입",
        "register_has_account": "이미 계정이 있으신가요?", "register_login_link": "로그인",
        "register_back": "&larr; 메인 페이지로 돌아가기", "register_password_hint": "6자 이상",
        "register_success": "회원가입이 완료되었습니다. 로그인해 주세요.",
        "err_name_short": "이름은 2자 이상이어야 합니다.",
        "err_username_short": "아이디는 3자 이상이어야 합니다.",
        "err_password_short": "비밀번호는 6자 이상이어야 합니다.",
        "err_password_mismatch": "비밀번호가 일치하지 않습니다.",
        "err_email_invalid": "올바른 이메일 주소를 입력하세요.",
        "err_username_taken": "이미 사용 중인 아이디입니다.",
        "err_email_taken": "이미 사용 중인 이메일입니다.",
    },
    "en": {
        "lang": "en", "lang_name": "English", "other_lang": "ko", "other_lang_name": "한국어",
        "church_name": "Church", "church_name_full": "Church", "denomination": "",
        "senior_pastor": "", "senior_pastor_short": "", "pastor_label": "",
        "nav_home": "Home", "nav_about": "About", "nav_direction": "Pastoral Direction",
        "nav_vision": "Vision & Values", "nav_schedule": "Worship Schedule",
        "nav_location": "Location", "nav_people": "Our Staff", "nav_videos": "Media",
        "nav_church_vision": "Church Vision", "nav_sermons": "Sermons", "nav_shorts": "Shorts",
        "nav_qt": "Daily QT", "nav_pastoral": "Pastoral Window", "nav_worship": "Worship Info",
        "nav_news": "Church News", "nav_admin": "Admin", "nav_logout": "Logout", "nav_login": "Login",
        "hero_title": "Seeking the Kingdom of God and His Righteousness",
        "hero_subtitle": "Welcome to our Church", "hero_info": "",
        "hero_worship_btn": "Worship Info", "hero_about_btn": "About Us",
        "welcome_title": "Welcome", "info_affiliation": "Affiliation:", "info_pastor": "Senior Pastor:",
        "info_location": "Location:", "info_location_val": "",
        "tab_vision": "Church Vision", "tab_sermons": "Sermons", "tab_shorts": "Shorts", "tab_qt": "Daily QT",
        "prev_video": "Previous", "next_video": "Next",
        "schedule_title": "Worship Schedule", "news_title": "Church News",
        "sunday_worship": "Sunday Worship", "sunday_time": "Sunday 10:40 AM",
        "sunday_study": "Sunday Bible Study & Small Group", "sunday_study_time": "Sunday 1:00 PM",
        "wed_worship": "Wednesday Worship", "wed_time": "Wednesday 7:30 PM",
        "fri_prayer": "Friday Prayer Meeting", "fri_time": "Friday 7:30 PM",
        "morning_worship": "Morning Worship", "morning_time": "7:00 AM",
        "news_col_num": "No.", "news_col_title": "Title", "news_col_date": "Date", "news_col_views": "Views",
        "contact_title": "Location & Directions",
        "naver_map": "Get Directions (Naver)", "kakao_map": "Get Directions (Kakao)",
        "footer_address_label": "Address", "footer_address": "", "footer_tel": "",
        "footer_copyright": "&copy; 2026. All rights reserved.",
        "footer_blessing": "May God's love and grace be with you.",
        "footer_email": "", "footer_phone": "",
        "about_title": "About Us", "mission_5_title": "Five Missions of the Church",
        "direction_title": "Pastoral Direction", "direction_preparing": "Coming soon.",
        "people_title": "Our Staff", "people_preparing": "Coming soon.",
        "pastoral_title": "Pastoral Window",
        "pastoral_subtitle": "A record of pastoral fellowship and the Word.",
        "pastoral_search_placeholder": "Search by title or content...", "pastoral_search_btn": "Search",
        "pastoral_search_result": "search results", "pastoral_all_list": "All Posts",
        "pastoral_col_title": "Title", "pastoral_col_date": "Date",
        "pastoral_col_author": "Author", "pastoral_col_views": "Views",
        "pastoral_empty": "No posts yet.", "pastoral_no_result": "No results found for",
        "pastoral_prev": "&laquo; Prev", "pastoral_next": "Next &raquo;",
        "pastoral_back": "&larr; Back to List",
        "pastoral_author_label": "&#128221; Author:", "pastoral_date_label": "&#128197; Date:",
        "pastoral_views_label": "&#128065; Views:", "pastoral_default_author": "Admin",
        "comments_title": "Comments", "no_comments": "No comments yet.",
        "comment_placeholder": "Write a comment...", "comment_submit": "Post Comment",
        "comment_login_prompt": "Please", "comment_login_link": "log in",
        "comment_login_suffix": "to write a comment.", "comment_delete": "Delete",
        "comment_delete_confirm": "Are you sure you want to delete this comment?",
        "news_author_label": "Author:", "news_date_label": "Date:", "news_views_label": "Views:",
        "news_back": "&larr; Back to List", "news_default_author": "Admin",
        "login_title": "Login", "login_username": "Email", "login_password": "Password",
        "login_button": "Login", "login_no_account": "Don't have an account?",
        "login_register_link": "Sign Up", "login_back": "&larr; Back to Home",
        "login_error": "Invalid username or password.",
        "register_title": "Sign Up", "register_name": "Full Name", "register_email": "Email",
        "register_username": "Username", "register_password": "Password",
        "register_password_confirm": "Confirm Password", "register_button": "Sign Up",
        "register_has_account": "Already have an account?", "register_login_link": "Login",
        "register_back": "&larr; Back to Home", "register_password_hint": "At least 6 characters",
        "register_success": "Registration successful. Please log in.",
        "err_name_short": "Name must be at least 2 characters.",
        "err_username_short": "Username must be at least 3 characters.",
        "err_password_short": "Password must be at least 6 characters.",
        "err_password_mismatch": "Passwords do not match.",
        "err_email_invalid": "Please enter a valid email address.",
        "err_username_taken": "This username is already taken.",
        "err_email_taken": "This email is already in use.",
    },
}


def get_t(lang: str = "ko") -> dict:
    return TRANSLATIONS.get(lang, TRANSLATIONS["ko"])


def get_lang_prefix(lang: str) -> str:
    return "/en" if lang == "en" else ""


def get_upload_dir(tenant_id: int) -> Path:
    d = UPLOAD_BASE / str(tenant_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def is_sha256_hash(h: str) -> bool:
    return len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def verify_sha256(password: str, hashed: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == hashed


def extract_youtube_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)",
        r"(?:https?://)?(?:www\.)?youtube\.com/live/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def extract_first_image_from_content(content: str) -> Optional[str]:
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    return m.group(1) if m else None


def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session_token")
    if not token or token not in sessions:
        return None
    session = sessions[token]
    tenant = getattr(request.state, "tenant", None)
    if tenant is None or session.get("tenant_id") != tenant["id"]:
        return None
    return session


def require_admin(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def init_db():
    schema = Path(__file__).parent / "init_schema.sql"
    conn = get_conn()
    cur = conn.cursor()
    with open(schema) as f:
        cur.execute(f.read())
    conn.commit()
    cur.close()
    conn.close()


@app.on_event("startup")
async def startup_event():
    init_db()


# ─── Tenant registration ──────────────────────────────────────────────────────

PLATFORM_ADMIN_KEY = os.getenv("PLATFORM_ADMIN_KEY", "")


def require_platform_admin(request: Request):
    key = request.headers.get("X-Admin-Key", "")
    if not PLATFORM_ADMIN_KEY or key != PLATFORM_ADMIN_KEY:
        raise HTTPException(403, "Forbidden")


class TenantRegisterRequest(BaseModel):
    slug: str
    church_name: str
    pastor_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    admin_username: str
    admin_password: str
    invite_code: str


@app.post("/api/register-tenant")
async def register_tenant(data: TenantRegisterRequest):
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$", data.slug):
        raise HTTPException(400, "slug은 소문자·숫자·하이픈 3~30자, 알파뉴머릭으로 시작·끝나야 합니다.")
    if len(data.admin_password) < 8:
        raise HTTPException(400, "비밀번호는 8자 이상이어야 합니다.")

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, used_at FROM invite_codes WHERE code = %s",
            (data.invite_code.strip(),),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(400, "유효하지 않은 초대 코드입니다.")
        if row[1] is not None:
            raise HTTPException(400, "이미 사용된 초대 코드입니다.")
        invite_id = row[0]

        trial_ends = datetime.now() + timedelta(days=30)
        cur.execute(
            """
            INSERT INTO tenants (slug, church_name, pastor_name, phone, address, trial_ends_at)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (data.slug, data.church_name, data.pastor_name, data.phone, data.address, trial_ends),
        )
        tenant_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO users (tenant_id, username, password, role, name, email, created_at)
            VALUES (%s, %s, %s, 'admin', %s, %s, NOW())
            """,
            (tenant_id, data.admin_username, hash_password(data.admin_password),
             data.admin_username, data.admin_username),
        )
        cur.execute(
            "INSERT INTO church_info (tenant_id, content, updated_at) VALUES (%s, %s, NOW())",
            (tenant_id, f"{data.church_name}에 오신 것을 환영합니다."),
        )
        cur.execute(
            """
            INSERT INTO church_about
                (tenant_id, vision_title, vision_content, mission_content, pastoral_direction, serving_people, updated_at)
            VALUES (%s, %s, '', '', '', '', NOW())
            """,
            (tenant_id, f"{data.church_name}의 비전"),
        )
        cur.execute(
            "UPDATE invite_codes SET used_at = NOW(), used_by_tenant_id = %s WHERE id = %s",
            (tenant_id, invite_id),
        )
        conn.commit()
        return {"tenant_id": tenant_id, "slug": data.slug, "trial_ends_at": trial_ends.isoformat()}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(409, f"슬러그 '{data.slug}'는 이미 사용 중입니다.")
    finally:
        cur.close()
        conn.close()


class InviteCodeCreateRequest(BaseModel):
    note: Optional[str] = ""
    count: Optional[int] = 1


@app.post("/api/admin/invite-codes")
async def create_invite_codes(data: InviteCodeCreateRequest, request: Request):
    require_platform_admin(request)
    if not 1 <= data.count <= 20:
        raise HTTPException(400, "count는 1~20 사이여야 합니다.")
    conn = get_conn()
    cur = conn.cursor()
    try:
        codes = []
        for _ in range(data.count):
            code = secrets.token_urlsafe(12)
            cur.execute(
                "INSERT INTO invite_codes (code, note) VALUES (%s, %s) RETURNING code",
                (code, data.note),
            )
            codes.append(cur.fetchone()[0])
        conn.commit()
        return {"codes": codes}
    finally:
        cur.close()
        conn.close()


@app.get("/api/admin/invite-codes")
async def list_invite_codes(request: Request):
    require_platform_admin(request)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT ic.code, ic.note, ic.created_at, ic.used_at, t.slug
            FROM invite_codes ic
            LEFT JOIN tenants t ON t.id = ic.used_by_tenant_id
            ORDER BY ic.created_at DESC
            """
        )
        rows = cur.fetchall()
        return {"codes": [
            {"code": r[0], "note": r[1], "created_at": r[2], "used_at": r[3], "used_by": r[4]}
            for r in rows
        ]}
    finally:
        cur.close()
        conn.close()


# ─── Home ─────────────────────────────────────────────────────────────────────

async def _home(request: Request, lang: str = "ko"):
    tenant = request.state.tenant
    tenant_id = tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT content FROM church_info WHERE tenant_id=%s", (tenant_id,))
    row = cur.fetchone()
    church_intro = row[0] if row else f"{tenant['church_name']}에 오신 것을 환영합니다."

    cur.execute(
        "SELECT id, title, youtube_url, date, author FROM visions WHERE tenant_id=%s ORDER BY date DESC LIMIT 5",
        (tenant_id,),
    )
    visions = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[2])
        visions.append({
            "id": r[0], "title": r[1], "youtube_url": r[2], "youtube_id": vid,
            "thumbnail": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg" if vid else None,
            "date": r[3], "author": r[4],
        })

    cur.execute(
        "SELECT id, title, pastor, date, description, youtube_url FROM sermons WHERE tenant_id=%s ORDER BY date DESC LIMIT 5",
        (tenant_id,),
    )
    sermons = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[5]) if r[5] else None
        sermons.append({
            "id": r[0], "title": r[1], "pastor": r[2], "date": r[3],
            "description": r[4], "youtube_url": r[5], "youtube_id": vid,
            "thumbnail": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg" if vid else None,
        })

    cur.execute(
        "SELECT id, title, youtube_url, date, author FROM shorts WHERE tenant_id=%s ORDER BY date DESC LIMIT 10",
        (tenant_id,),
    )
    shorts = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[2])
        shorts.append({
            "id": r[0], "title": r[1], "youtube_url": r[2], "youtube_id": vid,
            "thumbnail": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg" if vid else None,
            "date": r[3], "author": r[4],
        })

    cur.execute(
        "SELECT id, title, youtube_url, date, author FROM qtys WHERE tenant_id=%s ORDER BY date DESC LIMIT 10",
        (tenant_id,),
    )
    qtys = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[2])
        qtys.append({
            "id": r[0], "title": r[1], "youtube_url": r[2], "youtube_id": vid,
            "thumbnail": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg" if vid else None,
            "date": r[3], "author": r[4],
        })

    cur.execute(
        "SELECT id, title, content, date, views, author, image_path FROM news WHERE tenant_id=%s ORDER BY date DESC LIMIT 5",
        (tenant_id,),
    )
    news_list = [
        {"id": r[0], "title": r[1], "content": r[2], "date": r[3], "views": r[4], "author": r[5], "image_path": r[6]}
        for r in cur.fetchall()
    ]

    cur.close()
    conn.close()
    user = get_current_user(request)
    return templates.TemplateResponse("index.html", {
        "request": request, "t": t, "lp": lp,
        "visions": visions, "sermons": sermons, "shorts": shorts,
        "qtys": qtys, "news_list": news_list,
        "church_intro": church_intro, "user": user,
    })


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if getattr(request.state, "tenant", None) is None:
        return HTMLResponse(LANDING_HTML)
    return await _home(request, "ko")


@app.get("/en/", response_class=HTMLResponse)
async def home_en(request: Request):
    if getattr(request.state, "tenant", None) is None:
        return HTMLResponse(LANDING_HTML)
    return await _home(request, "en")


# ─── About / Direction / People ───────────────────────────────────────────────

async def _about_page(request: Request, lang: str = "ko"):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT vision_title, vision_content, mission_content, pastoral_direction, serving_people FROM church_about WHERE tenant_id=%s",
        (tenant_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    about = {
        "vision_title": row[0] if row else "",
        "vision_content": row[1] if row else "",
        "mission_content": row[2] if row else "",
        "pastoral_direction": row[3] if row else "",
        "serving_people": row[4] if row else "",
    }
    return templates.TemplateResponse("about.html", {"request": request, "about": about, "t": t, "lp": lp})


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _about_page(request, "ko")


@app.get("/en/about", response_class=HTMLResponse)
async def about_page_en(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _about_page(request, "en")


async def _direction_page(request: Request, lang: str = "ko"):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT pastoral_direction FROM church_about WHERE tenant_id=%s", (tenant_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    content = row[0] if row and row[0] else t["direction_preparing"]
    return templates.TemplateResponse("direction.html", {"request": request, "content": content, "t": t, "lp": lp})


@app.get("/direction", response_class=HTMLResponse)
async def direction_page(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _direction_page(request, "ko")


@app.get("/en/direction", response_class=HTMLResponse)
async def direction_page_en(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _direction_page(request, "en")


async def _people_page(request: Request, lang: str = "ko"):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, role, bio, photo_path, display_order FROM members WHERE tenant_id=%s ORDER BY display_order ASC, id ASC",
        (tenant_id,),
    )
    members = [
        {"id": r[0], "name": r[1], "role": r[2], "bio": r[3], "photo_path": r[4], "display_order": r[5]}
        for r in cur.fetchall()
    ]
    cur.execute("SELECT serving_people FROM church_about WHERE tenant_id=%s", (tenant_id,))
    row = cur.fetchone()
    intro = row[0] if row and row[0] else ""
    cur.close()
    conn.close()
    return templates.TemplateResponse("people.html", {
        "request": request, "members": members, "intro": intro, "t": t, "lp": lp,
    })


@app.get("/people", response_class=HTMLResponse)
async def people_page(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _people_page(request, "ko")


@app.get("/en/people", response_class=HTMLResponse)
async def people_page_en(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _people_page(request, "en")


# ─── Pastoral ────────────────────────────────────────────────────────────────

async def _pastoral_list(request: Request, lang: str = "ko", page: int = 1, q: str = ""):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    per_page = 20
    offset = (page - 1) * per_page
    conn = get_conn()
    cur = conn.cursor()
    if q.strip():
        s = f"%{q.strip()}%"
        cur.execute(
            "SELECT COUNT(*) FROM pastoral_posts WHERE tenant_id=%s AND (title LIKE %s OR content LIKE %s)",
            (tenant_id, s, s),
        )
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT id, title, content, image_path, author, views, created_at FROM pastoral_posts WHERE tenant_id=%s AND (title LIKE %s OR content LIKE %s) ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (tenant_id, s, s, per_page, offset),
        )
    else:
        cur.execute("SELECT COUNT(*) FROM pastoral_posts WHERE tenant_id=%s", (tenant_id,))
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT id, title, content, image_path, author, views, created_at FROM pastoral_posts WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (tenant_id, per_page, offset),
        )
    posts = [
        {"id": r[0], "title": r[1], "content": r[2], "image_path": r[3],
         "author": r[4], "views": r[5], "created_at": r[6]}
        for r in cur.fetchall()
    ]
    cur.close()
    conn.close()
    total_pages = max(1, (total + per_page - 1) // per_page)
    user = get_current_user(request)
    return templates.TemplateResponse("pastoral_list.html", {
        "request": request, "posts": posts, "user": user, "t": t, "lp": lp,
        "page": page, "total_pages": total_pages, "total": total, "q": q,
    })


@app.get("/pastoral", response_class=HTMLResponse)
async def pastoral_list(request: Request, page: int = 1, q: str = ""):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _pastoral_list(request, "ko", page, q)


@app.get("/en/pastoral", response_class=HTMLResponse)
async def pastoral_list_en(request: Request, page: int = 1, q: str = ""):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _pastoral_list(request, "en", page, q)


async def _pastoral_detail(request: Request, post_id: int, lang: str = "ko"):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE pastoral_posts SET views = views + 1 WHERE id=%s AND tenant_id=%s",
        (post_id, tenant_id),
    )
    conn.commit()
    cur.execute(
        "SELECT id, title, content, image_path, author, views, created_at FROM pastoral_posts WHERE id=%s AND tenant_id=%s",
        (post_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(404, "Post not found")
    post = {"id": row[0], "title": row[1], "content": row[2], "image_path": row[3],
            "author": row[4], "views": row[5], "created_at": row[6]}
    cur.execute(
        "SELECT image_path FROM pastoral_images WHERE pastoral_id=%s AND tenant_id=%s ORDER BY sort_order ASC",
        (post_id, tenant_id),
    )
    pastoral_images = [r[0] for r in cur.fetchall()]
    if not pastoral_images and post["image_path"]:
        pastoral_images = [post["image_path"]]
    cur.execute(
        """
        SELECT c.id, c.content, c.created_at, u.username, u.name, c.user_id
        FROM comments c JOIN users u ON c.user_id = u.id AND u.tenant_id = c.tenant_id
        WHERE c.post_type='pastoral' AND c.post_id=%s AND c.tenant_id=%s
        ORDER BY c.created_at ASC
        """,
        (post_id, tenant_id),
    )
    comments = [
        {"id": r[0], "content": r[1],
         "created_at": r[2].strftime("%Y-%m-%d %H:%M") if hasattr(r[2], "strftime") else str(r[2]),
         "username": r[3], "name": r[4], "user_id": r[5]}
        for r in cur.fetchall()
    ]
    cur.close()
    conn.close()
    user = get_current_user(request)
    return templates.TemplateResponse("pastoral_detail.html", {
        "request": request, "post": post, "pastoral_images": pastoral_images,
        "comments": comments, "user": user, "t": t, "lp": lp,
    })


@app.get("/pastoral/{post_id}", response_class=HTMLResponse)
async def pastoral_detail(request: Request, post_id: int):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _pastoral_detail(request, post_id, "ko")


@app.get("/en/pastoral/{post_id}", response_class=HTMLResponse)
async def pastoral_detail_en(request: Request, post_id: int):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _pastoral_detail(request, post_id, "en")


# ─── News ────────────────────────────────────────────────────────────────────

async def _view_news(request: Request, news_id: int, lang: str = "ko"):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE news SET views = views + 1 WHERE id=%s AND tenant_id=%s", (news_id, tenant_id))
    conn.commit()
    cur.execute(
        "SELECT id, title, content, date, views, author, image_path FROM news WHERE id=%s AND tenant_id=%s",
        (news_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(404, "Post not found")
    news = {"id": row[0], "title": row[1], "content": row[2], "date": row[3],
            "views": row[4], "author": row[5], "image_path": row[6]}
    cur.execute(
        "SELECT image_path FROM news_images WHERE news_id=%s AND tenant_id=%s ORDER BY sort_order ASC",
        (news_id, tenant_id),
    )
    news_images = [r[0] for r in cur.fetchall()]
    if not news_images and news["image_path"]:
        news_images = [news["image_path"]]
    cur.execute(
        """
        SELECT c.id, c.content, c.created_at, u.username, u.name, c.user_id
        FROM comments c JOIN users u ON c.user_id = u.id AND u.tenant_id = c.tenant_id
        WHERE c.post_type='news' AND c.post_id=%s AND c.tenant_id=%s
        ORDER BY c.created_at ASC
        """,
        (news_id, tenant_id),
    )
    comments = [
        {"id": r[0], "content": r[1],
         "created_at": r[2].strftime("%Y-%m-%d %H:%M") if hasattr(r[2], "strftime") else str(r[2]),
         "username": r[3], "name": r[4], "user_id": r[5]}
        for r in cur.fetchall()
    ]
    cur.close()
    conn.close()
    user = get_current_user(request)
    return templates.TemplateResponse("news_detail.html", {
        "request": request, "news": news, "news_images": news_images,
        "comments": comments, "user": user, "is_admin": user and user.get("role") == "admin",
        "t": t, "lp": lp,
    })


@app.get("/news/{news_id}", response_class=HTMLResponse)
async def view_news(request: Request, news_id: int):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _view_news(request, news_id, "ko")


@app.get("/en/news/{news_id}", response_class=HTMLResponse)
async def view_news_en(request: Request, news_id: int):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _view_news(request, news_id, "en")


# ─── Auth ────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return templates.TemplateResponse("login.html", {"request": request, "t": get_t("ko"), "lp": ""})


@app.get("/en/login", response_class=HTMLResponse)
async def login_page_en(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return templates.TemplateResponse("login.html", {"request": request, "t": get_t("en"), "lp": "/en"})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return templates.TemplateResponse("register.html", {"request": request, "t": get_t("ko"), "lp": ""})


@app.get("/en/register", response_class=HTMLResponse)
async def register_page_en(request: Request):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return templates.TemplateResponse("register.html", {"request": request, "t": get_t("en"), "lp": "/en"})


async def _register_post(request: Request, lang: str, name: str, email: str):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    errors = []
    if len(name.strip()) < 2:
        errors.append(t["err_name_short"])
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        errors.append(t["err_email_invalid"])
    if errors:
        return templates.TemplateResponse("register.html", {
            "request": request, "errors": errors, "t": t, "lp": lp, "name": name, "email": email,
        })
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=%s AND tenant_id=%s", (email, tenant_id))
    if cur.fetchone():
        cur.close()
        conn.close()
        return templates.TemplateResponse("register.html", {
            "request": request, "errors": [t["err_email_taken"]], "t": t, "lp": lp, "name": name, "email": email,
        })
    temp_pw = secrets.token_urlsafe(8)
    cur.execute(
        "INSERT INTO users (tenant_id, username, password, role, name, email, created_at) VALUES (%s, %s, %s, 'user', %s, %s, NOW())",
        (tenant_id, email, hash_password(temp_pw), name.strip(), email),
    )
    conn.commit()
    cur.close()
    conn.close()
    if lang == "ko":
        msg = f"가입이 완료되었습니다. 임시 비밀번호: <b>{temp_pw}</b><br>로그인 후 비밀번호를 변경해 주세요."
    else:
        msg = f"Registration successful. Temporary password: <b>{temp_pw}</b><br>Please change your password after logging in."
    return templates.TemplateResponse("login.html", {"request": request, "t": t, "lp": lp, "success": msg})


@app.post("/register")
async def register(request: Request, name: str = Form(...), email: str = Form(...)):
    return await _register_post(request, "ko", name, email)


@app.post("/en/register")
async def register_en(request: Request, name: str = Form(...), email: str = Form(...)):
    return await _register_post(request, "en", name, email)


async def _login_post(request: Request, lang: str, username: str, password: str):
    tenant_id = request.state.tenant["id"]
    t = get_t(lang)
    lp = get_lang_prefix(lang)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, password, role FROM users WHERE username=%s AND tenant_id=%s",
        (username, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return templates.TemplateResponse("login.html", {"request": request, "error": t["login_error"], "t": t, "lp": lp})

    stored = row[2]
    valid = False
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        valid = verify_password(password, stored)
    elif is_sha256_hash(stored) and verify_sha256(password, stored):
        valid = True
        cur.execute("UPDATE users SET password=%s WHERE id=%s AND tenant_id=%s", (hash_password(password), row[0], tenant_id))
        conn.commit()
    if not valid:
        cur.close()
        conn.close()
        return templates.TemplateResponse("login.html", {"request": request, "error": t["login_error"], "t": t, "lp": lp})

    token = secrets.token_urlsafe(32)
    sessions[token] = {"id": row[0], "username": row[1], "role": row[3], "tenant_id": tenant_id}
    cur.close()
    conn.close()
    response = RedirectResponse(url="/admin" if row[3] == "admin" else f"{lp}/", status_code=303)
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return response


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _login_post(request, "ko", username, password)


@app.post("/en/login")
async def login_en(request: Request, username: str = Form(...), password: str = Form(...)):
    if not getattr(request.state, "tenant", None):
        raise HTTPException(404)
    return await _login_post(request, "en", username, password)


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token and token in sessions:
        del sessions[token]
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session_token")
    return resp


# ─── Comments ────────────────────────────────────────────────────────────────

@app.post("/news/{news_id}/comment")
async def create_news_comment(request: Request, news_id: int, content: str = Form(...)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "로그인이 필요합니다.")
    if not content.strip():
        return RedirectResponse(url=f"/news/{news_id}", status_code=303)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO comments (tenant_id, post_type, post_id, user_id, content, created_at) VALUES (%s, 'news', %s, %s, %s, NOW())",
        (user["tenant_id"], news_id, user["id"], content.strip()),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url=f"/news/{news_id}", status_code=303)


@app.post("/pastoral/{post_id}/comment")
async def create_pastoral_comment(request: Request, post_id: int, content: str = Form(...)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "로그인이 필요합니다.")
    if not content.strip():
        return RedirectResponse(url=f"/pastoral/{post_id}", status_code=303)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO comments (tenant_id, post_type, post_id, user_id, content, created_at) VALUES (%s, 'pastoral', %s, %s, %s, NOW())",
        (user["tenant_id"], post_id, user["id"], content.strip()),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url=f"/pastoral/{post_id}", status_code=303)


@app.post("/comment/{comment_id}/delete")
async def delete_comment(request: Request, comment_id: int, redirect: str = "/"):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "로그인이 필요합니다.")
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM comments WHERE id=%s AND tenant_id=%s", (comment_id, tenant_id))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(404, "댓글을 찾을 수 없습니다.")
    if row[0] != user["id"] and user["role"] != "admin":
        cur.close()
        conn.close()
        raise HTTPException(403, "삭제 권한이 없습니다.")
    cur.execute("DELETE FROM comments WHERE id=%s AND tenant_id=%s", (comment_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url=redirect, status_code=303)


# ─── Admin dashboard ─────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, title, youtube_url, date, author FROM visions WHERE tenant_id=%s ORDER BY date DESC", (tenant_id,))
    visions = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[2])
        visions.append({"id": r[0], "title": r[1], "youtube_url": r[2], "youtube_id": vid, "date": r[3], "author": r[4]})

    cur.execute("SELECT id, title, pastor, date, description, youtube_url FROM sermons WHERE tenant_id=%s ORDER BY date DESC", (tenant_id,))
    sermons = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[5]) if r[5] else None
        sermons.append({"id": r[0], "title": r[1], "pastor": r[2], "date": r[3], "description": r[4], "youtube_url": r[5], "youtube_id": vid})

    cur.execute("SELECT id, title, youtube_url, date, author FROM shorts WHERE tenant_id=%s ORDER BY date DESC", (tenant_id,))
    shorts = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[2])
        shorts.append({"id": r[0], "title": r[1], "youtube_url": r[2], "youtube_id": vid, "date": r[3], "author": r[4]})

    cur.execute("SELECT id, title, youtube_url, date, author FROM qtys WHERE tenant_id=%s ORDER BY date DESC", (tenant_id,))
    qtys = []
    for r in cur.fetchall():
        vid = extract_youtube_id(r[2])
        qtys.append({"id": r[0], "title": r[1], "youtube_url": r[2], "youtube_id": vid, "date": r[3], "author": r[4]})

    cur.execute("SELECT id, title, content, date, views, author, image_path FROM news WHERE tenant_id=%s ORDER BY date DESC", (tenant_id,))
    news_list = [{"id": r[0], "title": r[1], "content": r[2], "date": r[3], "views": r[4], "author": r[5], "image_path": r[6]} for r in cur.fetchall()]

    cur.execute("SELECT content FROM church_info WHERE tenant_id=%s", (tenant_id,))
    row = cur.fetchone()
    church_intro = row[0] if row else ""

    cur.execute("SELECT vision_title, vision_content, mission_content, pastoral_direction, serving_people FROM church_about WHERE tenant_id=%s", (tenant_id,))
    row = cur.fetchone()
    about = {
        "vision_title": row[0] if row else "", "vision_content": row[1] if row else "",
        "mission_content": row[2] if row else "", "pastoral_direction": row[3] if row else "",
        "serving_people": row[4] if row else "",
    }

    cur.execute("SELECT id, title, content, image_path, author, views, created_at FROM pastoral_posts WHERE tenant_id=%s ORDER BY created_at DESC", (tenant_id,))
    pastoral_posts = [{"id": r[0], "title": r[1], "content": r[2], "image_path": r[3], "author": r[4], "views": r[5], "created_at": r[6]} for r in cur.fetchall()]

    cur.execute("SELECT id, name, role, bio, photo_path, display_order FROM members WHERE tenant_id=%s ORDER BY display_order ASC, id ASC", (tenant_id,))
    members = [{"id": r[0], "name": r[1], "role": r[2], "bio": r[3], "photo_path": r[4], "display_order": r[5]} for r in cur.fetchall()]

    cur.close()
    conn.close()
    return templates.TemplateResponse("admin.html", {
        "request": request, "t": get_t("ko"), "lp": "", "user": user,
        "visions": visions, "sermons": sermons, "shorts": shorts, "qtys": qtys,
        "news_list": news_list, "church_intro": church_intro, "about": about,
        "pastoral_posts": pastoral_posts, "members": members,
    })


# ─── Admin: News ─────────────────────────────────────────────────────────────

@app.post("/admin/news/create")
async def create_news(
    request: Request,
    title: str = Form(...), content: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    upload_dir = get_upload_dir(tenant_id)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO news (tenant_id, title, content, date, views, author, image_path) VALUES (%s,%s,%s,%s,0,%s,%s) RETURNING id",
        (tenant_id, title, content, datetime.now().strftime("%Y-%m-%d"), user["username"], None),
    )
    news_id = cur.fetchone()[0]
    for i, img in enumerate(images):
        if img and img.filename:
            ext = Path(img.filename).suffix.lower()
            fname = f"news_{datetime.now().timestamp()}_{i}{ext}"
            with (upload_dir / fname).open("wb") as f:
                shutil.copyfileobj(img.file, f)
            cur.execute(
                "INSERT INTO news_images (tenant_id, news_id, image_path, sort_order) VALUES (%s,%s,%s,%s)",
                (tenant_id, news_id, f"/uploads/{tenant_id}/{fname}", i),
            )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/admin/news/edit/{news_id}", response_class=HTMLResponse)
async def edit_news_form(request: Request, news_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, content, date FROM news WHERE id=%s AND tenant_id=%s", (news_id, tenant_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(404)
    return templates.TemplateResponse("news_edit.html", {
        "request": request, "news": {"id": row[0], "title": row[1], "content": row[2], "date": row[3]}, "user": user,
    })


@app.post("/admin/news/update/{news_id}")
async def update_news(
    request: Request, news_id: int,
    title: str = Form(...), content: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    upload_dir = get_upload_dir(tenant_id)
    conn = get_conn()
    cur = conn.cursor()
    has_new = any(img and img.filename for img in images)
    if has_new:
        cur.execute("DELETE FROM news_images WHERE news_id=%s AND tenant_id=%s", (news_id, tenant_id))
        for i, img in enumerate(images):
            if img and img.filename:
                ext = Path(img.filename).suffix.lower()
                fname = f"news_{datetime.now().timestamp()}_{i}{ext}"
                with (upload_dir / fname).open("wb") as f:
                    shutil.copyfileobj(img.file, f)
                cur.execute(
                    "INSERT INTO news_images (tenant_id, news_id, image_path, sort_order) VALUES (%s,%s,%s,%s)",
                    (tenant_id, news_id, f"/uploads/{tenant_id}/{fname}", i),
                )
    cur.execute("UPDATE news SET title=%s, content=%s WHERE id=%s AND tenant_id=%s", (title, content, news_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url=f"/news/{news_id}", status_code=303)


@app.post("/admin/news/delete/{news_id}")
async def delete_news(news_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM news_images WHERE news_id=%s AND tenant_id=%s", (news_id, tenant_id))
    cur.execute("DELETE FROM news WHERE id=%s AND tenant_id=%s", (news_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: Church info / About ───────────────────────────────────────────────

@app.post("/admin/church-info/update")
async def update_church_info(content: str = Form(...), user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE church_info SET content=%s, updated_at=NOW() WHERE tenant_id=%s", (content, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/about/update")
async def update_about(
    vision_title: str = Form(...), vision_content: str = Form(...),
    mission_content: str = Form(...), pastoral_direction: str = Form(""),
    serving_people: str = Form(""), user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE church_about
           SET vision_title=%s, vision_content=%s, mission_content=%s,
               pastoral_direction=%s, serving_people=%s, updated_at=NOW()
           WHERE tenant_id=%s""",
        (vision_title, vision_content, mission_content, pastoral_direction, serving_people, tenant_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: Vision ────────────────────────────────────────────────────────────

@app.post("/admin/vision/create")
async def create_vision(title: str = Form(...), youtube_url: str = Form(...), user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO visions (tenant_id, title, youtube_url, date, author) VALUES (%s,%s,%s,%s,%s)",
        (tenant_id, title, youtube_url, datetime.now().strftime("%Y-%m-%d"), user["username"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/vision/delete/{vision_id}")
async def delete_vision(vision_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM visions WHERE id=%s AND tenant_id=%s", (vision_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: Sermons ───────────────────────────────────────────────────────────

@app.post("/admin/sermon/create")
async def create_sermon(
    title: str = Form(...), pastor: str = Form(...), description: str = Form(...),
    youtube_url: Optional[str] = Form(None), user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sermons (tenant_id, title, pastor, date, description, youtube_url) VALUES (%s,%s,%s,%s,%s,%s)",
        (tenant_id, title, pastor, datetime.now().strftime("%Y-%m-%d"), description, youtube_url),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/sermon/update/{sermon_id}")
async def update_sermon(
    sermon_id: int, title: str = Form(...), pastor: str = Form(...), date: str = Form(...),
    description: str = Form(...), youtube_url: Optional[str] = Form(None),
    user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sermons SET title=%s, pastor=%s, date=%s, description=%s, youtube_url=%s WHERE id=%s AND tenant_id=%s",
        (title, pastor, date, description, youtube_url, sermon_id, tenant_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/sermon/delete/{sermon_id}")
async def delete_sermon(sermon_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sermons WHERE id=%s AND tenant_id=%s", (sermon_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: Shorts ────────────────────────────────────────────────────────────

@app.post("/admin/shorts/create")
async def create_shorts(title: str = Form(...), youtube_url: str = Form(...), user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO shorts (tenant_id, title, youtube_url, date, author) VALUES (%s,%s,%s,%s,%s)",
        (tenant_id, title, youtube_url, datetime.now().strftime("%Y-%m-%d"), user["username"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/shorts/update/{shorts_id}")
async def update_shorts(
    shorts_id: int, title: str = Form(...), youtube_url: str = Form(...),
    date: str = Form(...), user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE shorts SET title=%s, youtube_url=%s, date=%s WHERE id=%s AND tenant_id=%s",
        (title, youtube_url, date, shorts_id, tenant_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/shorts/delete/{shorts_id}")
async def delete_shorts(shorts_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shorts WHERE id=%s AND tenant_id=%s", (shorts_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: QTY ───────────────────────────────────────────────────────────────

@app.post("/admin/qty/create")
async def create_qty(title: str = Form(...), youtube_url: str = Form(...), user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO qtys (tenant_id, title, youtube_url, date, author) VALUES (%s,%s,%s,%s,%s)",
        (tenant_id, title, youtube_url, datetime.now().strftime("%Y-%m-%d"), user["username"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/qty/update/{qty_id}")
async def update_qty(
    qty_id: int, title: str = Form(...), youtube_url: str = Form(...),
    date: str = Form(...), user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE qtys SET title=%s, youtube_url=%s, date=%s WHERE id=%s AND tenant_id=%s",
        (title, youtube_url, date, qty_id, tenant_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/qty/delete/{qty_id}")
async def delete_qty(qty_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM qtys WHERE id=%s AND tenant_id=%s", (qty_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: Members ───────────────────────────────────────────────────────────

@app.post("/admin/member/create")
async def create_member(
    request: Request, name: str = Form(...), role: str = Form(...),
    bio: str = Form(""), display_order: int = Form(0),
    photo: Optional[UploadFile] = File(None), user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    upload_dir = get_upload_dir(tenant_id)
    photo_path = None
    if photo and photo.filename:
        ext = Path(photo.filename).suffix
        fname = f"member_{datetime.now().timestamp()}{ext}"
        with (upload_dir / fname).open("wb") as f:
            shutil.copyfileobj(photo.file, f)
        photo_path = f"/uploads/{tenant_id}/{fname}"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO members (tenant_id, name, role, bio, photo_path, display_order) VALUES (%s,%s,%s,%s,%s,%s)",
        (tenant_id, name, role, bio, photo_path, display_order),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/member/delete/{member_id}")
async def delete_member(member_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM members WHERE id=%s AND tenant_id=%s", (member_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: Pastoral posts ────────────────────────────────────────────────────

@app.post("/admin/pastoral/create")
async def create_pastoral(
    request: Request, title: str = Form(...), content: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    upload_dir = get_upload_dir(tenant_id)
    image_path = extract_first_image_from_content(content) or "/static/images/logo.png"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pastoral_posts (tenant_id, title, content, image_path, author, views, created_at) VALUES (%s,%s,%s,%s,%s,0,%s) RETURNING id",
        (tenant_id, title, content, image_path, user["username"], datetime.now().strftime("%Y-%m-%d")),
    )
    pastoral_id = cur.fetchone()[0]
    for i, img in enumerate(images):
        if img and img.filename:
            ext = Path(img.filename).suffix.lower()
            fname = f"pastoral_{datetime.now().timestamp()}_{i}{ext}"
            with (upload_dir / fname).open("wb") as f:
                shutil.copyfileobj(img.file, f)
            url = f"/uploads/{tenant_id}/{fname}"
            cur.execute(
                "INSERT INTO pastoral_images (tenant_id, pastoral_id, image_path, sort_order) VALUES (%s,%s,%s,%s)",
                (tenant_id, pastoral_id, url, i),
            )
            if i == 0:
                cur.execute("UPDATE pastoral_posts SET image_path=%s WHERE id=%s AND tenant_id=%s", (url, pastoral_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/pastoral/update/{post_id}")
async def update_pastoral(
    request: Request, post_id: int,
    title: str = Form(...), content: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    upload_dir = get_upload_dir(tenant_id)
    conn = get_conn()
    cur = conn.cursor()
    has_new = any(img and img.filename for img in images)
    if has_new:
        cur.execute("DELETE FROM pastoral_images WHERE pastoral_id=%s AND tenant_id=%s", (post_id, tenant_id))
        first_url = None
        for i, img in enumerate(images):
            if img and img.filename:
                ext = Path(img.filename).suffix.lower()
                fname = f"pastoral_{datetime.now().timestamp()}_{i}{ext}"
                with (upload_dir / fname).open("wb") as f:
                    shutil.copyfileobj(img.file, f)
                url = f"/uploads/{tenant_id}/{fname}"
                cur.execute(
                    "INSERT INTO pastoral_images (tenant_id, pastoral_id, image_path, sort_order) VALUES (%s,%s,%s,%s)",
                    (tenant_id, post_id, url, i),
                )
                if first_url is None:
                    first_url = url
        cur.execute(
            "UPDATE pastoral_posts SET title=%s, content=%s, image_path=%s WHERE id=%s AND tenant_id=%s",
            (title, content, first_url, post_id, tenant_id),
        )
    else:
        first_img = extract_first_image_from_content(content)
        if first_img:
            cur.execute(
                "UPDATE pastoral_posts SET title=%s, content=%s, image_path=%s WHERE id=%s AND tenant_id=%s",
                (title, content, first_img, post_id, tenant_id),
            )
        else:
            cur.execute(
                "UPDATE pastoral_posts SET title=%s, content=%s WHERE id=%s AND tenant_id=%s",
                (title, content, post_id, tenant_id),
            )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/pastoral/delete/{post_id}")
async def delete_pastoral(post_id: int, user: dict = Depends(require_admin)):
    tenant_id = user["tenant_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM pastoral_images WHERE pastoral_id=%s AND tenant_id=%s", (post_id, tenant_id))
    cur.execute("DELETE FROM comments WHERE post_type='pastoral' AND post_id=%s AND tenant_id=%s", (post_id, tenant_id))
    cur.execute("DELETE FROM pastoral_posts WHERE id=%s AND tenant_id=%s", (post_id, tenant_id))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url="/admin", status_code=303)


# ─── Admin: image upload (rich editor) ───────────────────────────────────────

@app.post("/admin/upload-image")
async def upload_image(
    request: Request, image: UploadFile = File(...), user: dict = Depends(require_admin),
):
    tenant_id = user["tenant_id"]
    if not image.filename:
        return JSONResponse({"error": "No file"}, status_code=400)
    ext = Path(image.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return JSONResponse({"error": "지원하지 않는 파일 형식입니다."}, status_code=400)
    upload_dir = get_upload_dir(tenant_id)
    fname = f"content_{datetime.now().timestamp()}{ext}"
    with (upload_dir / fname).open("wb") as f:
        shutil.copyfileobj(image.file, f)
    return JSONResponse({"url": f"/uploads/{tenant_id}/{fname}"})


# ─── Platform Lounge ─────────────────────────────────────────────────────────

LOUNGE_LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>목회자 라운지 로그인</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#f1f5f9;min-height:100vh;display:flex;align-items:center;justify-content:center}
.wrap{width:100%;max-width:400px;padding:20px}
.logo{text-align:center;margin-bottom:32px}
.logo h1{font-size:1.5rem;color:#cbd5e1;font-weight:600}
.logo p{font-size:.85rem;color:#64748b;margin-top:4px}
.card{background:#1e293b;border-radius:16px;padding:32px;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.field{margin-bottom:16px}
label{display:block;font-size:.8rem;color:#94a3b8;margin-bottom:6px;font-weight:500}
input{width:100%;padding:10px 14px;background:#0f172a;border:1.5px solid #334155;border-radius:8px;color:#f1f5f9;font-size:.95rem;outline:none}
input:focus{border-color:#6366f1}
.btn{width:100%;padding:12px;background:#6366f1;color:#fff;border:none;border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer;margin-top:8px}
.btn:hover{background:#4f46e5}
.err{color:#f87171;font-size:.85rem;margin-top:12px;text-align:center;display:none}
.back{text-align:center;margin-top:16px;font-size:.82rem;color:#64748b}
.back a{color:#818cf8}
</style></head><body>
<div class="wrap">
  <div class="logo">
    <h1>✝ 목회자 라운지</h1>
    <p>교회 플랫폼 가입 교회 전용 공간</p>
  </div>
  <div class="card">
    <div class="field"><label>교회 slug</label><input id="slug" placeholder="sejong-church" autocomplete="off"></div>
    <div class="field"><label>관리자 아이디</label><input id="username" autocomplete="username"></div>
    <div class="field"><label>비밀번호</label><input id="password" type="password" autocomplete="current-password"></div>
    <button class="btn" onclick="doLogin()">입장하기</button>
    <div class="err" id="err"></div>
  </div>
  <div class="back"><a href="/">← 플랫폼 홈으로</a></div>
</div>
<script>
async function doLogin() {
  const err = document.getElementById('err');
  err.style.display = 'none';
  const res = await fetch('/api/platform/login', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      slug: document.getElementById('slug').value.trim(),
      username: document.getElementById('username').value.trim(),
      password: document.getElementById('password').value
    })
  });
  const data = await res.json();
  if (!res.ok) { err.textContent = data.detail || '로그인 실패'; err.style.display='block'; return; }
  location.href = '/platform/lounge';
}
document.addEventListener('keydown', e => { if(e.key==='Enter') doLogin(); });
</script>
</body></html>"""


LOUNGE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>목회자 라운지</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#f1f5f9;min-height:100vh}
header{background:#1e293b;border-bottom:1px solid #334155;padding:14px 24px;display:flex;align-items:center;justify-content:space-between}
header .logo{font-size:1rem;font-weight:700;color:#c7d2fe}
header .info{font-size:.82rem;color:#64748b}
header .info span{color:#94a3b8;margin-right:12px}
header a.out{color:#64748b;font-size:.8rem;text-decoration:none}
.main{max-width:860px;margin:0 auto;padding:32px 20px}
.search-wrap{display:flex;gap:8px;margin-bottom:28px}
.search-wrap input{flex:1;padding:11px 16px;background:#1e293b;border:1.5px solid #334155;border-radius:10px;color:#f1f5f9;font-size:.95rem;outline:none}
.search-wrap input:focus{border-color:#6366f1}
.search-wrap button{padding:11px 20px;background:#6366f1;color:#fff;border:none;border-radius:10px;cursor:pointer;font-weight:600}
.tag-row{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:24px}
.tag{padding:4px 12px;background:#1e293b;border:1px solid #334155;border-radius:20px;font-size:.78rem;color:#94a3b8;cursor:pointer}
.tag:hover,.tag.active{background:#6366f1;border-color:#6366f1;color:#fff}
.articles{display:grid;gap:16px}
.article-card{background:#1e293b;border-radius:12px;padding:24px;border:1px solid #334155;cursor:pointer;transition:border-color .2s}
.article-card:hover{border-color:#6366f1}
.article-card h3{font-size:1rem;color:#e2e8f0;margin-bottom:6px;line-height:1.5}
.article-card .summary{font-size:.85rem;color:#64748b;line-height:1.6;margin-bottom:12px}
.article-card .meta{display:flex;gap:12px;align-items:center}
.article-card .author{font-size:.78rem;color:#818cf8}
.article-card .date{font-size:.78rem;color:#475569}
.tags-list{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.tag-sm{padding:2px 8px;background:#0f172a;border-radius:10px;font-size:.72rem;color:#6366f1;border:1px solid #312e81}
.empty{text-align:center;padding:60px 0;color:#475569;font-size:.9rem}
.loading{text-align:center;padding:40px 0;color:#64748b}
</style></head><body>
<header>
  <div class="logo">✝ 목회자 라운지</div>
  <div class="info">
    <span id="church_name"></span>
    <a class="out" href="/api/platform/logout">로그아웃</a>
  </div>
</header>
<div class="main">
  <div class="search-wrap">
    <input id="q" placeholder="신학 주제, 키워드 검색..." onkeydown="if(event.key==='Enter')search()">
    <button onclick="search()">검색</button>
  </div>
  <div class="tag-row" id="tagRow"></div>
  <div class="articles" id="articles"><div class="loading">불러오는 중...</div></div>
</div>
<script>
let activeTag = null;

async function fetchMe() {
  const res = await fetch('/api/platform/me');
  if (!res.ok) { location.href='/platform/login'; return; }
  const d = await res.json();
  document.getElementById('church_name').textContent = d.church_name + ' · ' + d.username;
}

async function search(tag) {
  const q = document.getElementById('q').value.trim();
  if (tag !== undefined) {
    activeTag = activeTag === tag ? null : tag;
    document.querySelectorAll('.tag').forEach(t => t.classList.toggle('active', t.dataset.tag === activeTag));
    document.getElementById('q').value = '';
  }
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (activeTag) params.set('tag', activeTag);
  const res = await fetch('/api/platform/articles?' + params);
  const data = await res.json();
  renderArticles(data.articles);
  if (!q && !activeTag) renderTags(data.tags);
}

function renderArticles(articles) {
  const el = document.getElementById('articles');
  if (!articles.length) { el.innerHTML = '<div class="empty">아티클이 없습니다.</div>'; return; }
  el.innerHTML = articles.map(a => `
    <div class="article-card" onclick="location.href='/platform/article/${a.id}'">
      <h3>${a.title}</h3>
      <div class="summary">${a.summary || ''}</div>
      <div class="meta">
        <span class="author">${a.author}</span>
        <span class="date">${a.created_at?.substring(0,10) || ''}</span>
      </div>
      ${a.tags?.length ? '<div class="tags-list">' + a.tags.map(t=>`<span class="tag-sm">${t}</span>`).join('') + '</div>' : ''}
    </div>
  `).join('');
}

function renderTags(tags) {
  if (!tags?.length) return;
  const el = document.getElementById('tagRow');
  el.innerHTML = tags.map(t => `<span class="tag" data-tag="${t}" onclick="search('${t}')">${t}</span>`).join('');
}

fetchMe();
search();
</script>
</body></html>"""


ARTICLE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — 목회자 라운지</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#f1f5f9;min-height:100vh}
header{background:#1e293b;border-bottom:1px solid #334155;padding:14px 24px;display:flex;align-items:center;gap:16px}
header a{color:#818cf8;font-size:.85rem;text-decoration:none}
header .logo{font-size:1rem;font-weight:700;color:#c7d2fe}
.main{max-width:720px;margin:0 auto;padding:40px 20px}
h1{font-size:1.6rem;line-height:1.4;margin-bottom:12px}
.meta{display:flex;gap:12px;margin-bottom:24px;font-size:.82rem;color:#64748b}
.meta .author{{color:#818cf8}}
.tags-list{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:28px}
.tag-sm{padding:3px 10px;background:#1e293b;border-radius:10px;font-size:.78rem;color:#6366f1;border:1px solid #312e81}
.content{font-size:.95rem;line-height:1.9;color:#cbd5e1;white-space:pre-wrap;background:#1e293b;padding:28px;border-radius:12px;border:1px solid #334155}
</style></head><body>
<header>
  <div class="logo">✝</div>
  <a href="/platform/lounge">← 라운지로</a>
</header>
<div class="main">
  <h1>__TITLE__</h1>
  <div class="meta"><span class="author">__AUTHOR__</span><span>__DATE__</span></div>
  __TAGS__
  <div class="content">__CONTENT__</div>
</div>
</body></html>"""


def get_platform_user(request: Request):
    token = request.cookies.get("psession")
    if not token:
        return None
    return platform_sessions.get(token)


def require_platform_user(request: Request):
    user = get_platform_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/platform/login"})
    return user


class PlatformLoginRequest(BaseModel):
    slug: str
    username: str
    password: str


@app.get("/platform/login", response_class=HTMLResponse)
async def platform_login_page():
    return HTMLResponse(LOUNGE_LOGIN_HTML)


@app.post("/api/platform/login")
async def platform_login(data: PlatformLoginRequest, response: JSONResponse = None):
    from fastapi.responses import JSONResponse as JR
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, slug, church_name FROM tenants WHERE slug=%s AND status != 'suspended'", (data.slug,))
        tenant = cur.fetchone()
        if not tenant:
            raise HTTPException(400, "등록되지 않은 교회 slug입니다.")
        tenant_id, slug, church_name = tenant

        cur.execute(
            "SELECT id, password, role, name FROM users WHERE tenant_id=%s AND username=%s",
            (tenant_id, data.username),
        )
        user = cur.fetchone()
        if not user or not verify_password(data.password, user[1]):
            raise HTTPException(400, "아이디 또는 비밀번호가 올바르지 않습니다.")
        if user[2] not in ("admin", "owner"):
            raise HTTPException(403, "관리자 계정만 라운지에 입장할 수 있습니다.")

        token = secrets.token_hex(32)
        platform_sessions[token] = {
            "user_id": user[0],
            "tenant_id": tenant_id,
            "slug": slug,
            "church_name": church_name,
            "username": data.username,
            "name": user[3],
            "role": user[2],
        }
        resp = JR({"ok": True})
        resp.set_cookie("psession", token, httponly=True, samesite="lax", max_age=86400 * 7)
        return resp
    finally:
        cur.close()
        conn.close()


@app.get("/api/platform/logout")
async def platform_logout(request: Request):
    token = request.cookies.get("psession")
    if token:
        platform_sessions.pop(token, None)
    resp = RedirectResponse("/platform/login", status_code=302)
    resp.delete_cookie("psession")
    return resp


@app.get("/api/platform/me")
async def platform_me(request: Request):
    user = get_platform_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return {"church_name": user["church_name"], "username": user["username"], "slug": user["slug"]}


@app.get("/platform/lounge", response_class=HTMLResponse)
async def platform_lounge(request: Request):
    user = get_platform_user(request)
    if not user:
        return RedirectResponse("/platform/login", status_code=302)
    return HTMLResponse(LOUNGE_HTML_TEMPLATE)


@app.get("/api/platform/articles")
async def platform_articles(request: Request, q: str = "", tag: str = ""):
    user = get_platform_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    if q or tag:
        must = []
        if q:
            must.append({"multi_match": {"query": q, "fields": ["title^3", "content", "summary^2"], "type": "best_fields"}})
        if tag:
            must.append({"term": {"tags": tag}})
        body = {"query": {"bool": {"must": must}}, "size": 30, "sort": [{"created_at": "desc"}]}
    else:
        body = {"query": {"match_all": {}}, "size": 30, "sort": [{"created_at": "desc"}],
                "aggs": {"all_tags": {"terms": {"field": "tags", "size": 30}}}}

    result = es.search(index=ES_INDEX, body=body)
    hits = result["hits"]["hits"]
    articles = [{"id": h["_id"], **h["_source"]} for h in hits]
    tags = [b["key"] for b in result.get("aggregations", {}).get("all_tags", {}).get("buckets", [])]
    return {"articles": articles, "tags": tags}


@app.get("/platform/article/{article_id}", response_class=HTMLResponse)
async def platform_article_detail(article_id: str, request: Request):
    user = get_platform_user(request)
    if not user:
        return RedirectResponse("/platform/login", status_code=302)
    try:
        doc = es.get(index=ES_INDEX, id=article_id)
    except Exception:
        raise HTTPException(404, "아티클을 찾을 수 없습니다.")
    src = doc["_source"]
    tags_html = ""
    if src.get("tags"):
        tags_html = '<div class="tags-list">' + "".join(f'<span class="tag-sm">{t}</span>' for t in src["tags"]) + "</div>"
    html = (ARTICLE_HTML_TEMPLATE
        .replace("__TITLE__", src.get("title", ""))
        .replace("__AUTHOR__", src.get("author", ""))
        .replace("__DATE__", str(src.get("created_at", ""))[:10])
        .replace("__TAGS__", tags_html)
        .replace("__CONTENT__", src.get("content", ""))
    )
    return HTMLResponse(html)


# ─── Platform Admin: Article CRUD ────────────────────────────────────────────

class ArticleCreateRequest(BaseModel):
    title: str
    content: str
    summary: Optional[str] = ""
    author: Optional[str] = "운영자"
    tags: Optional[List[str]] = []


@app.post("/api/admin/articles")
async def create_article(data: ArticleCreateRequest, request: Request):
    require_platform_admin(request)
    doc = {
        "title": data.title,
        "content": data.content,
        "summary": data.summary,
        "author": data.author,
        "tags": data.tags,
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    result = es.index(index=ES_INDEX, document=doc)
    return {"id": result["_id"], "title": data.title}


@app.put("/api/admin/articles/{article_id}")
async def update_article(article_id: str, data: ArticleCreateRequest, request: Request):
    require_platform_admin(request)
    doc = {
        "title": data.title,
        "content": data.content,
        "summary": data.summary,
        "author": data.author,
        "tags": data.tags,
    }
    es.update(index=ES_INDEX, id=article_id, doc=doc)
    return {"ok": True}


@app.delete("/api/admin/articles/{article_id}")
async def delete_article(article_id: str, request: Request):
    require_platform_admin(request)
    es.delete(index=ES_INDEX, id=article_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
