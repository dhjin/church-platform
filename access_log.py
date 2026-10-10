"""교회 사이트 접속 로그.

페이지 조회·로그인·로그인 실패·로그아웃을 교회(tenant)별로 access_logs 에 남기고,
관리자 화면에서 오늘 현황·회원별 마지막 접속·전체 기록을 조회한다.
기록 실패는 사이트 응답에 영향을 주지 않는다.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import get_conn

KST = timezone(timedelta(hours=9))
RETENTION_DAYS = 90
PER_PAGE = 100
EVENTS = {"page": "조회", "login": "로그인", "login_fail": "로그인 실패", "logout": "로그아웃"}
BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|facebookexternalhit|preview|monitor|curl|wget|python-requests|httpx|go-http", re.I
)
SKIP_PREFIXES = ("/static", "/uploads", "/favicon", "/robots.txt", "/sitemap", "/api/", "/admin/access-logs", "/logout")


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def client_ip(request) -> str:
    """프록시(Cloudflare, traefik) 뒤의 실제 접속 IP"""
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def is_bot(user_agent: str) -> bool:
    return not user_agent or bool(BOT_UA_RE.search(user_agent))


def should_log_page(method: str, path: str) -> bool:
    return method == "GET" and not path.startswith(SKIP_PREFIXES)


def record(request, event: str, user: Optional[dict] = None,
           status: Optional[int] = None, username: Optional[str] = None) -> None:
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        return
    try:
        user_agent = request.headers.get("user-agent", "")[:300]
        path = request.url.path + ("?" + request.url.query if request.url.query else "")
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO access_logs
                       (tenant_id, created_at, event, user_id, username, ip, method, path, status, user_agent, is_bot)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (tenant["id"], now_kst(), event,
                     user["id"] if user else None,
                     (username or (user["username"] if user else None) or None),
                     client_ip(request), request.method, path[:300], status, user_agent, is_bot(user_agent)),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"access log error: {e}")


def purge_old(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM access_logs WHERE created_at < %s", (now_kst() - timedelta(days=RETENTION_DAYS),))
    conn.commit()


def summary(conn, tenant_id: int) -> dict:
    today = now_kst().replace(hour=0, minute=0, second=0, microsecond=0)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE event = 'page' AND NOT is_bot),
                      COUNT(DISTINCT ip) FILTER (WHERE event = 'page' AND NOT is_bot),
                      COUNT(DISTINCT user_id) FILTER (WHERE event IN ('page', 'login')),
                      COUNT(*) FILTER (WHERE event = 'login_fail')
               FROM access_logs WHERE tenant_id = %s AND created_at >= %s""",
            (tenant_id, today),
        )
        views, visitors, members, login_fails = cur.fetchone()
    return {"views": views, "visitors": visitors, "members": members, "login_fails": login_fails}


def member_activity(conn, tenant_id: int) -> list:
    """가입한 모든 회원의 마지막 접속. 기록이 없는 회원도 포함해 맨 아래에 둔다."""
    now = now_kst()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT u.id, u.username, u.name, u.role, u.created_at,
                      MAX(l.created_at) AS last_seen,
                      COUNT(*) FILTER (WHERE l.event = 'login') AS logins,
                      COUNT(*) FILTER (WHERE l.event = 'page') AS views
               FROM users u
               LEFT JOIN access_logs l ON l.tenant_id = u.tenant_id AND l.user_id = u.id
               WHERE u.tenant_id = %s
               GROUP BY u.id
               ORDER BY last_seen DESC NULLS LAST, u.created_at""",
            (tenant_id,),
        )
        rows = cur.fetchall()
    return [{
        "id": r[0], "username": r[1], "name": r[2], "role": r[3], "created_at": r[4],
        "last_seen": r[5], "days_ago": (now - r[5]).days if r[5] else None,
        "logins": r[6], "views": r[7],
    } for r in rows]


def search(conn, tenant_id: int, event: str = "", q: str = "", members_only: bool = False,
           show_bots: bool = False, date: str = "", page: int = 1) -> dict:
    where, params = ["tenant_id = %s"], [tenant_id]
    if event in EVENTS:
        where.append("event = %s")
        params.append(event)
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(username ILIKE %s OR ip ILIKE %s OR path ILIKE %s)")
        params += [like, like, like]
    if members_only:
        where.append("user_id IS NOT NULL")
    if not show_bots:
        where.append("NOT is_bot")
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
            where.append("created_at >= %s AND created_at < %s")
            params += [day, day + timedelta(days=1)]
        except ValueError:
            pass
    where_sql = " AND ".join(where)
    page = max(page, 1)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM access_logs WHERE {where_sql}", params)
        total = cur.fetchone()[0]
        cur.execute(
            f"""SELECT created_at, event, username, ip, path, status, user_agent
                FROM access_logs WHERE {where_sql}
                ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
            params + [PER_PAGE, (page - 1) * PER_PAGE],
        )
        logs = [{"created_at": r[0], "event": r[1], "username": r[2], "ip": r[3], "path": r[4],
                 "status": r[5], "user_agent": r[6]} for r in cur.fetchall()]
    return {"logs": logs, "total": total, "page": page,
            "total_pages": max((total + PER_PAGE - 1) // PER_PAGE, 1)}
