"""구독/결제 DB 처리.

흐름
1. 관리자가 구독 페이지를 열면 ensure_subscription() 으로 customer_key 를 가진 구독 행을 만든다.
2. 결제수단 등록 성공 → register_payment_method() 가 빌링키(토스) / SID(카카오페이)를 저장한다.
   토스는 무료체험이 남아 있으면 체험 종료일에, 아니면 즉시 첫 결제를 한다.
   카카오페이는 등록 승인 자체가 첫 결제라서(start_registration → 승인) 그 결제를 다음 이용 기간 요금으로 기록한다.
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
            (tenant_id, config.BILLING_PROVIDER, config.PLAN_CODE, config.plan_info(config.PLAN_CODE)["amount"],
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


def _new_contract(sub: dict) -> bool:
    return sub["status"] in ("incomplete", "canceled")


def registration_order_id(sub: dict, now: datetime) -> str:
    return f"sub{sub['id']}-reg{now:%Y%m%d%H%M%S}"


def start_registration(
    conn,
    tenant_id: int,
    provider_name: str,
    approval_url: str,
    cancel_url: str,
    fail_url: str,
    mobile: bool = False,
    now: Optional[datetime] = None,
    provider: Optional[BillingProvider] = None,
) -> str:
    """서버에서 등록을 시작하는 결제대행사(카카오페이)의 결제창 URL 을 받는다. 커밋까지 수행."""
    now = now or datetime.now()
    provider = provider or get_provider(provider_name)
    sub = ensure_subscription(conn, tenant_id)
    amount = config.plan_info(sub["plan"])["amount"] if _new_contract(sub) else sub["amount"]
    order_id = registration_order_id(sub, now)
    start = provider.start_registration(
        sub["customer_key"], order_id, amount, config.plan_info(sub["plan"])["order_name"],
        approval_url, cancel_url, fail_url, mobile=mobile,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE subscriptions SET pending_provider=%s, pending_token=%s, pending_order_id=%s, updated_at=NOW()
            WHERE id=%s
            """,
            (provider.name, start.token, order_id, sub["id"]),
        )
    conn.commit()
    return start.redirect_url


def register_payment_method(
    conn,
    tenant_id: int,
    auth_key: str,
    customer_key: str = "",
    customer_email: str = "",
    customer_name: str = "",
    now: Optional[datetime] = None,
    provider: Optional[BillingProvider] = None,
    provider_name: str = "",
) -> dict:
    """결제수단 등록을 마무리한다. 커밋까지 수행.

    - 토스: 브라우저에서 받은 authKey 로 빌링키를 발급하고, 결제일이 됐으면 바로 결제한다.
    - 카카오페이: pg_token 으로 승인하면 첫 결제와 함께 SID 가 발급된다. 그 결제는 다음 이용 기간
      (무료체험 중이면 체험 종료일부터 한 달)의 요금으로 기록한다.
    """
    now = now or datetime.now()
    old_key = old_provider = None
    try:
        sub = get_subscription(conn, tenant_id, for_update=True)
        if not sub:
            raise BillingError("구독 정보가 없습니다. 구독 페이지에서 다시 시도해주세요.")
        provider = provider or get_provider(provider_name or sub["provider"])
        if provider.client_side_registration:
            if sub["customer_key"] != customer_key:
                raise BillingError("구독 정보가 일치하지 않습니다. 구독 페이지에서 다시 시도해주세요.")
            token = order_id = ""
        else:
            if sub["pending_provider"] != provider.name or not sub["pending_token"]:
                raise BillingError("진행 중인 결제수단 등록이 없습니다. 구독 페이지에서 다시 시도해주세요.")
            token, order_id = sub["pending_token"], sub["pending_order_id"]
        registration = provider.complete_registration(sub["customer_key"], auth_key, token, order_id)
        method = registration.method
        old_key, old_provider = sub["billing_key"], sub["provider"]

        with conn.cursor() as cur:
            cur.execute("SELECT trial_ends_at FROM tenants WHERE id=%s", (tenant_id,))
            trial_ends_at = cur.fetchone()[0]

        status = sub["status"]
        period_end = sub["current_period_end"]
        next_billing_at = sub["next_billing_at"]
        failed_attempts = sub["failed_attempts"]
        amount = sub["amount"]
        if _new_contract(sub):
            # 새로 시작: 이미 낸 기간(해지 후 재가입) 또는 무료체험이 끝나는 날부터 청구
            amount = config.plan_info(sub["plan"])["amount"]
            failed_attempts = 0
            start = period_end if period_end and period_end > now else max(now, trial_ends_at or now)
            period_end = start
            next_billing_at = start
            status = "trialing" if start > now else "active"
        elif status in ("past_due", "unpaid"):
            # 결제수단을 바꿨으니 밀린 결제를 즉시 다시 시도
            failed_attempts = 0
            next_billing_at = now
            status = "past_due"

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscriptions SET provider=%s, billing_key=%s, payment_method=%s,
                    customer_email=%s, customer_name=%s, status=%s, amount=%s, current_period_end=%s,
                    next_billing_at=%s, failed_attempts=%s, canceled_at=NULL,
                    pending_provider=NULL, pending_token=NULL, pending_order_id=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (provider.name, method.billing_key, method.display_name, customer_email, customer_name,
                 status, amount, period_end, next_billing_at, failed_attempts, sub["id"]),
            )
        sub = get_subscription(conn, tenant_id, for_update=True)
        if registration.initial_charge is not None:
            _record_charge(conn, sub, provider, order_id, registration.initial_charge, now)
        elif sub["next_billing_at"] <= now:
            charge_subscription(conn, sub, provider, now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if old_key and old_key != method.billing_key:
        _deactivate(old_provider, old_key)
    return get_subscription(conn, tenant_id)


def charge_subscription(conn, sub: dict, provider: BillingProvider, now: datetime):
    """구독 1건을 결제하고 결과를 기록한다. 호출자가 sub 행을 잠그고 커밋한다."""
    sub = _apply_scheduled_plan(conn, sub)
    period_start = sub["current_period_end"] or now
    order_id = order_id_for(sub, period_start)
    result = provider.charge(
        billing_key=sub["billing_key"],
        customer_key=sub["customer_key"],
        order_id=order_id,
        amount=sub["amount"],
        order_name=config.plan_info(sub["plan"])["order_name"],
        customer_email=sub["customer_email"] or "",
        customer_name=sub["customer_name"] or "",
    )
    _record_charge(conn, sub, provider, order_id, result, now)
    return result


def _record_charge(conn, sub: dict, provider: BillingProvider, order_id: str, result, now: datetime):
    """결제 1건의 결과를 결제 내역과 구독 상태에 반영한다."""
    period_start = sub["current_period_end"] or now
    anchor_day = sub["anchor_day"] or period_start.day
    period_end = add_month(period_start, anchor_day)
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
            # 결과 미확인. 멱등키를 지원하면 회차를 올리지 않아 같은 주문번호로 재시도되고,
            # 지원하지 않으면(카카오페이) 이중결제를 막기 위해 자동 청구를 멈추고 수동 확인을 기다린다.
            next_at = now + timedelta(minutes=config.UNKNOWN_RETRY_MINUTES) if provider.idempotent_retry else None
            cur.execute(
                "UPDATE subscriptions SET next_billing_at=%s, updated_at=NOW() WHERE id=%s",
                (next_at, sub["id"]),
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


def _deactivate(provider_name: str, billing_key: str):
    try:
        get_provider(provider_name).deactivate(billing_key)
    except BillingProviderError:
        pass


def _to_local_naive(dt: Optional[datetime]) -> Optional[datetime]:
    # DB 의 TIMESTAMP 컬럼은 서버 로컬 시각(naive) 기준
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)


def cancel_subscription(conn, tenant_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """자동결제를 해지한다. 이미 결제한 기간(current_period_end)까지는 계속 이용할 수 있다."""
    now = now or datetime.now()
    sub = get_subscription(conn, tenant_id)
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
    if sub and sub["billing_key"]:
        _deactivate(sub["provider"], sub["billing_key"])
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
                   s.status, s.provider, s.amount, s.payment_method, s.current_period_end, s.next_billing_at,
                   s.failed_attempts, s.canceled_at,
                   EXISTS (SELECT 1 FROM subscription_payments p
                           WHERE p.subscription_id = s.id AND p.status = 'unknown') AS needs_review
            FROM tenants t LEFT JOIN subscriptions s ON s.tenant_id = t.id
            ORDER BY t.id
            """
        )
        return cur.fetchall()


# ─── 요금제 변경 · 1회 결제 ──────────────────────────────────────────────────

def current_plan(conn, tenant_id: int) -> str:
    """교회가 지금 쓸 수 있는 요금제. 구독 행이 없거나 알 수 없는 값이면 standard."""
    with conn.cursor() as cur:
        cur.execute("SELECT plan FROM subscriptions WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()
    return row[0] if row and row[0] in config.PLANS else config.PLAN_CODE


def change_plan(conn, tenant_id: int, plan: str) -> dict:
    """요금제를 바꾼다. 올리면 바로 적용되고(다음 결제일부터 새 금액 청구), 내리면 다음 결제일에 적용된다.
    결제수단이 없거나 해지된 구독은 새 계약 금액이 등록 시점에 정해지므로 바로 바꾼다. 커밋까지 수행."""
    if plan not in config.PLANS:
        raise ValueError(f"unknown plan: {plan}")
    try:
        ensure_subscription(conn, tenant_id)
        sub = get_subscription(conn, tenant_id, for_update=True)
        current = sub["plan"] if sub["plan"] in config.PLANS else config.PLAN_CODE
        upgrade = config.PLAN_ORDER.index(plan) > config.PLAN_ORDER.index(current)
        with conn.cursor() as cur:
            if plan == current:
                cur.execute("UPDATE subscriptions SET scheduled_plan=NULL, updated_at=NOW() WHERE id=%s", (sub["id"],))
            elif upgrade or _new_contract(sub):
                cur.execute(
                    "UPDATE subscriptions SET plan=%s, amount=%s, scheduled_plan=NULL, updated_at=NOW() WHERE id=%s",
                    (plan, config.PLANS[plan]["amount"], sub["id"]),
                )
                cur.execute("UPDATE tenants SET plan=%s WHERE id=%s", (plan, tenant_id))
            else:
                cur.execute("UPDATE subscriptions SET scheduled_plan=%s, updated_at=NOW() WHERE id=%s", (plan, sub["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_subscription(conn, tenant_id)


def _apply_scheduled_plan(conn, sub: dict) -> dict:
    """예약된 요금제 내림을 결제 직전에 반영한다. 결과 미확인 재시도(같은 주문번호)에는 금액을 바꾸지 않는다."""
    plan = sub.get("scheduled_plan")
    if not plan or plan not in config.PLANS:
        return sub
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM subscription_payments WHERE order_id=%s AND status='unknown'",
            (order_id_for(sub, sub["current_period_end"] or datetime.now()),),
        )
        if cur.fetchone():
            return sub
        cur.execute(
            "UPDATE subscriptions SET plan=%s, amount=%s, scheduled_plan=NULL, updated_at=NOW() WHERE id=%s",
            (plan, config.PLANS[plan]["amount"], sub["id"]),
        )
        cur.execute("UPDATE tenants SET plan=%s WHERE id=%s", (plan, sub["tenant_id"]))
    return {**sub, "plan": plan, "amount": config.PLANS[plan]["amount"], "scheduled_plan": None}


def list_one_time_payments(conn, tenant_id: int) -> list:
    with _dict_cur(conn) as cur:
        cur.execute(
            """SELECT kind, order_id, amount, status, failure_message, approved_at, created_at
               FROM one_time_payments WHERE tenant_id=%s ORDER BY created_at DESC""",
            (tenant_id,),
        )
        return cur.fetchall()


def charge_setup_fee(conn, tenant_id: int, now: Optional[datetime] = None,
                     provider: Optional[BillingProvider] = None) -> dict:
    """등록된 자동결제 수단으로 AI 맞춤 제작 셋업비를 1회 결제한다. 이미 결제했거나 확인 중이면 다시 청구하지 않는다.
    결과를 알 수 없으면 이중결제를 막기 위해 자동 재시도하지 않고 unknown 으로 남긴다. 커밋까지 수행."""
    now = now or datetime.now()
    try:
        sub = get_subscription(conn, tenant_id, for_update=True)
        if not sub or not sub["billing_key"] or sub["status"] == "canceled":
            raise BillingProviderError("NO_PAYMENT_METHOD", "먼저 구독 결제수단을 등록해 주세요.")
        with _dict_cur(conn) as cur:
            cur.execute(
                "SELECT * FROM one_time_payments WHERE tenant_id=%s AND kind='setup' AND status IN ('done', 'unknown')",
                (tenant_id,),
            )
            existing = cur.fetchone()
        if existing:
            conn.rollback()
            return existing
        provider = provider or get_provider(sub["provider"])
        order_id = f"sub{sub['id']}-setup{now:%Y%m%d%H%M%S}"
        result = provider.charge(
            billing_key=sub["billing_key"], customer_key=sub["customer_key"], order_id=order_id,
            amount=config.SETUP_FEE_AMOUNT, order_name=config.SETUP_FEE_NAME,
            customer_email=sub["customer_email"] or "", customer_name=sub["customer_name"] or "",
        )
        status = "done" if result.success else ("unknown" if result.retryable else "failed")
        with _dict_cur(conn) as cur:
            cur.execute(
                """INSERT INTO one_time_payments (tenant_id, kind, provider, order_id, amount, status,
                       payment_key, failure_code, failure_message, approved_at)
                   VALUES (%s, 'setup', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (tenant_id, provider.name, order_id, config.SETUP_FEE_AMOUNT, status, result.payment_key,
                 result.failure_code, result.failure_message, _to_local_naive(result.approved_at)),
            )
            row = cur.fetchone()
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
