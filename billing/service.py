"""구독/결제 DB 처리.

흐름
1. 관리자가 구독 페이지를 열면 ensure_subscription() 으로 customer_key 를 가진 구독 행을 만든다.
2. 카드 등록(토스 결제창) 성공 → register_payment_method() 가 빌링키를 발급받아 저장한다.
   무료체험이 남아 있으면 체험 종료일에, 아니면 즉시 첫 결제를 한다.
3. 이후 매달 run_due() (CronJob) 가 next_billing_at 이 지난 구독을 결제한다.
   실패하면 config.RETRY_DAYS 간격으로 재시도하고, 모두 실패하면 unpaid 로 바꾼다.
"""
import calendar
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional

import psycopg2.extras

from billing import config
from billing.providers import BillingProvider, BillingProviderError, get_provider

BILLABLE_STATUSES = ("trialing", "active", "past_due")


class BillingError(Exception):
    pass


def add_month(dt: datetime, anchor_day: int) -> datetime:
    """다음 달 같은 날짜. 31일처럼 없는 날은 그 달 말일로 맞추되, anchor_day 를 기억해 다시 늘어난다."""
    year = dt.year + dt.month // 12
    month = dt.month % 12 + 1
    day = min(anchor_day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def order_id_for(sub: dict, period_start: datetime) -> str:
    # 같은 청구(기간+시도 회차)는 항상 같은 주문번호 → 토스 멱등키로도 사용
    return f"sub{sub['id']}-{period_start:%Y%m%d}-{sub['failed_attempts'] + 1}"


def _dict_cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def get_subscription(conn, tenant_id: int, for_update: bool = False) -> Optional[dict]:
    with _dict_cur(conn) as cur:
        cur.execute(
            "SELECT * FROM subscriptions WHERE tenant_id=%s" + (" FOR UPDATE" if for_update else ""),
            (tenant_id,),
        )
        return cur.fetchone()


def ensure_subscription(conn, tenant_id: int) -> dict:
    sub = get_subscription(conn, tenant_id)
    if sub:
        return sub
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO subscriptions (tenant_id, provider, plan, amount, customer_key)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id) DO NOTHING
            """,
            (tenant_id, config.BILLING_PROVIDER, config.PLAN_CODE, config.PLAN_AMOUNT,
             f"cus_{uuid.uuid4().hex}"),
        )
    conn.commit()
    return get_subscription(conn, tenant_id)


def list_payments(conn, tenant_id: int, limit: int = 24) -> list:
    with _dict_cur(conn) as cur:
        cur.execute(
            """
            SELECT order_id, amount, status, period_start, period_end, failure_message, approved_at, created_at
            FROM subscription_payments WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s
            """,
            (tenant_id, limit),
        )
        return cur.fetchall()


def register_payment_method(
    conn,
    tenant_id: int,
    auth_key: str,
    customer_key: str,
    customer_email: str = "",
    customer_name: str = "",
    now: Optional[datetime] = None,
    provider: Optional[BillingProvider] = None,
) -> dict:
    """카드 등록 성공 후 빌링키를 발급·저장하고, 결제일이 됐으면 바로 결제한다. 커밋까지 수행."""
    now = now or datetime.now()
    try:
        sub = get_subscription(conn, tenant_id, for_update=True)
        if not sub or sub["customer_key"] != customer_key:
            raise BillingError("구독 정보가 일치하지 않습니다. 구독 페이지에서 다시 시도해주세요.")
        provider = provider or get_provider(sub["provider"])
        method = provider.issue_billing_key(auth_key, customer_key)

        with conn.cursor() as cur:
            cur.execute("SELECT trial_ends_at FROM tenants WHERE id=%s", (tenant_id,))
            trial_ends_at = cur.fetchone()[0]

        status = sub["status"]
        period_end = sub["current_period_end"]
        next_billing_at = sub["next_billing_at"]
        failed_attempts = sub["failed_attempts"]
        amount = sub["amount"]
        if status in ("incomplete", "canceled"):
            # 새로 시작: 이미 낸 기간(해지 후 재가입) 또는 무료체험이 끝나는 날부터 청구
            amount = config.PLAN_AMOUNT
            failed_attempts = 0
            start = period_end if period_end and period_end > now else max(now, trial_ends_at or now)
            period_end = start
            next_billing_at = start
            status = "trialing" if start > now else "active"
        elif status in ("past_due", "unpaid"):
            # 카드를 바꿨으니 밀린 결제를 즉시 다시 시도
            failed_attempts = 0
            next_billing_at = now
            status = "past_due"

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscriptions SET billing_key=%s, payment_method=%s, customer_email=%s, customer_name=%s,
                    status=%s, amount=%s, current_period_end=%s, next_billing_at=%s, failed_attempts=%s,
                    canceled_at=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (method.billing_key, method.display_name, customer_email, customer_name,
                 status, amount, period_end, next_billing_at, failed_attempts, sub["id"]),
            )
        sub = get_subscription(conn, tenant_id, for_update=True)
        if sub["next_billing_at"] <= now:
            charge_subscription(conn, sub, provider, now)
        conn.commit()
        return get_subscription(conn, tenant_id)
    except Exception:
        conn.rollback()
        raise


def charge_subscription(conn, sub: dict, provider: BillingProvider, now: datetime):
    """구독 1건을 결제하고 결과를 기록한다. 호출자가 sub 행을 잠그고 커밋한다."""
    period_start = sub["current_period_end"] or now
    anchor_day = sub["anchor_day"] or period_start.day
    period_end = add_month(period_start, anchor_day)
    order_id = order_id_for(sub, period_start)

    result = provider.charge(
        billing_key=sub["billing_key"],
        customer_key=sub["customer_key"],
        order_id=order_id,
        amount=sub["amount"],
        order_name=config.PLAN_NAME,
        customer_email=sub["customer_email"] or "",
        customer_name=sub["customer_name"] or "",
    )
    pay_status = "done" if result.success else ("unknown" if result.retryable else "failed")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO subscription_payments
                (tenant_id, subscription_id, provider, order_id, amount, status, period_start, period_end,
                 payment_key, failure_code, failure_message, approved_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (order_id) DO UPDATE SET status=EXCLUDED.status, payment_key=EXCLUDED.payment_key,
                failure_code=EXCLUDED.failure_code, failure_message=EXCLUDED.failure_message,
                approved_at=EXCLUDED.approved_at, updated_at=NOW()
            """,
            (sub["tenant_id"], sub["id"], provider.name, order_id, sub["amount"], pay_status,
             period_start, period_end, result.payment_key, result.failure_code, result.failure_message,
             _to_local_naive(result.approved_at)),
        )

        if result.success:
            cur.execute(
                """
                UPDATE subscriptions SET status='active', current_period_start=%s, current_period_end=%s,
                    next_billing_at=%s, anchor_day=%s, failed_attempts=0, updated_at=NOW()
                WHERE id=%s
                """,
                (period_start, period_end, period_end, anchor_day, sub["id"]),
            )
            cur.execute(
                "UPDATE tenants SET status='active' WHERE id=%s AND status != 'suspended'",
                (sub["tenant_id"],),
            )
        elif result.retryable:
            # 결과 미확인: 회차를 올리지 않아 같은 주문번호로 재시도된다
            cur.execute(
                "UPDATE subscriptions SET next_billing_at=%s, updated_at=NOW() WHERE id=%s",
                (now + timedelta(minutes=config.UNKNOWN_RETRY_MINUTES), sub["id"]),
            )
        else:
            failed = sub["failed_attempts"] + 1
            if failed > len(config.RETRY_DAYS):
                status, next_at = "unpaid", None
            else:
                status, next_at = "past_due", now + timedelta(days=config.RETRY_DAYS[failed - 1])
            cur.execute(
                "UPDATE subscriptions SET status=%s, failed_attempts=%s, next_billing_at=%s, updated_at=NOW() WHERE id=%s",
                (status, failed, next_at, sub["id"]),
            )
    return result


def _to_local_naive(dt: Optional[datetime]) -> Optional[datetime]:
    # DB 의 TIMESTAMP 컬럼은 서버 로컬 시각(naive) 기준
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)


def cancel_subscription(conn, tenant_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """자동결제를 해지한다. 이미 결제한 기간(current_period_end)까지는 계속 이용할 수 있다."""
    now = now or datetime.now()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE subscriptions SET status='canceled', billing_key=NULL, next_billing_at=NULL,
                canceled_at=%s, updated_at=NOW()
            WHERE tenant_id=%s AND status != 'canceled'
            """,
            (now, tenant_id),
        )
    conn.commit()
    return get_subscription(conn, tenant_id)


def run_due(
    conn,
    now: Optional[datetime] = None,
    provider_factory: Callable[[str], BillingProvider] = get_provider,
    limit: int = 500,
) -> dict:
    """결제일이 지난 구독을 한 건씩 잠그고 결제한다. 여러 개가 동시에 돌아도 같은 구독을 두 번 잡지 않는다."""
    now = now or datetime.now()
    counts = {"done": 0, "failed": 0, "unknown": 0, "error": 0}
    seen = set()
    for _ in range(limit):
        with _dict_cur(conn) as cur:
            cur.execute(
                """
                SELECT * FROM subscriptions
                WHERE billing_key IS NOT NULL AND next_billing_at <= %s AND status = ANY(%s)
                    AND NOT (id = ANY(%s))
                ORDER BY next_billing_at LIMIT 1 FOR UPDATE SKIP LOCKED
                """,
                (now, list(BILLABLE_STATUSES), list(seen) or [0]),
            )
            sub = cur.fetchone()
        if not sub:
            break
        seen.add(sub["id"])
        try:
            result = charge_subscription(conn, sub, provider_factory(sub["provider"]), now)
            conn.commit()
            counts["done" if result.success else ("unknown" if result.retryable else "failed")] += 1
        except BillingProviderError:
            conn.rollback()
            counts["error"] += 1
    return counts


def list_all_subscriptions(conn) -> list:
    with _dict_cur(conn) as cur:
        cur.execute(
            """
            SELECT t.slug, t.church_name, t.status AS tenant_status, t.trial_ends_at,
                   s.status, s.amount, s.payment_method, s.current_period_end, s.next_billing_at,
                   s.failed_attempts, s.canceled_at
            FROM tenants t LEFT JOIN subscriptions s ON s.tenant_id = t.id
            ORDER BY t.id
            """
        )
        return cur.fetchall()
