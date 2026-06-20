from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from database import get_conn


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        parts = host.split(".")
        # slug.our-church.kr  → 3+ parts, first part is slug
        # our-church.kr / localhost / IP → no tenant
        if len(parts) >= 3:
            slug = parts[0]
            tenant = _lookup_tenant(slug)
        else:
            tenant = None

        request.state.tenant = tenant
        return await call_next(request)


def _lookup_tenant(slug: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, slug, church_name, pastor_name, plan, status FROM tenants WHERE slug=%s AND status != 'suspended'",
            (slug,),
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
        }
    except Exception:
        return None
