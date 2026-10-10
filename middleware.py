from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
from database import get_conn
import re

_OLD_UPLOAD = re.compile(r"^/uploads/(?!\d+/)[A-Za-z0-9_.-]+$")


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0].lower()
        parts = host.split(".")
        # 교회 자체 도메인(tenant_domains) → 해당 교회
        # slug.our-church.kr  → 3+ parts, first part is slug
        # our-church.kr / localhost / IP → no tenant
        tenant = _lookup_tenant(host, parts[0] if len(parts) >= 3 else None) if host else None

        request.state.tenant = tenant
        # 다른 사이트에서 옮겨 온 교회의 예전 업로드 주소(/uploads/x.jpg)를 교회 폴더(/uploads/<id>/x.jpg)로 보낸다
        path = request.url.path
        if tenant and _OLD_UPLOAD.match(path):
            return RedirectResponse(f"/uploads/{tenant['id']}/{path[len('/uploads/'):]}", status_code=301)
        return await call_next(request)


def _lookup_tenant(host: str, slug):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT t.id, t.slug, t.church_name, t.pastor_name, t.plan, t.status, t.phone, t.address
               FROM tenants t
               LEFT JOIN tenant_domains d ON d.tenant_id = t.id AND d.domain = %s
               WHERE t.status != 'suspended' AND (d.domain IS NOT NULL OR t.slug = %s)
               ORDER BY d.domain IS NULL
               LIMIT 1""",
            (host, slug),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "slug": row[1],
            "church_name": row[2],
            "pastor_name": row[3],
            "plan": row[4],
            "status": row[5],
            "phone": row[6] or "",
            "address": row[7] or "",
        }
    except Exception:
        return None
