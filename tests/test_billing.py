import json
from datetime import datetime, timedelta

import httpx
import pytest

from billing import config
from billing.providers import BillingMethod, BillingProvider, BillingProviderError, ChargeResult, TossBillingProvider
from billing.service import (
    add_month, cancel_subscription, ensure_subscription, get_subscription, list_payments,
    register_payment_method, run_due,
)

NOW = datetime(2026, 10, 9, 10, 0, 0)


# ─── add_month ────────────────────────────────────────────────────────────────

def test_add_month_keeps_anchor_day_across_short_months():
    jan31 = datetime(2026, 1, 31, 10)
    feb = add_month(jan31, 31)
    assert feb == datetime(2026, 2, 28, 10)
    assert add_month(feb, 31) == datetime(2026, 3, 31, 10)
    assert add_month(datetime(2026, 12, 15), 15) == datetime(2027, 1, 15)


# ─── Toss provider (HTTP mocked) ─────────────────────────────────────────────

def _toss(handler):
    return TossBillingProvider(secret_key="test_sk_dummy", transport=httpx.MockTransport(handler))


def test_toss_issue_billing_key_sends_basic_auth_and_parses_card():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["Authorization"]
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            "customerKey": "cus_1", "billingKey": "bk_1", "cardCompany": "신한", "cardNumber": "4330****",
        })

    method = _toss(handler).issue_billing_key("auth_1", "cus_1")
    assert seen["path"] == "/v1/billing/authorizations/issue"
    assert seen["body"] == {"authKey": "auth_1", "customerKey": "cus_1"}
    assert seen["auth"] == "Basic dGVzdF9za19kdW1teTo="  # base64("test_sk_dummy:")
    assert method.billing_key == "bk_1"
    assert method.display_name == "신한 4330****"


def test_toss_issue_billing_key_error_raises():
    handler = lambda req: httpx.Response(400, json={"code": "INVALID_AUTH_KEY", "message": "잘못된 인증키"})
    with pytest.raises(BillingProviderError) as e:
        _toss(handler).issue_billing_key("x", "cus_1")
    assert e.value.code == "INVALID_AUTH_KEY"


def test_toss_charge_success_uses_idempotency_key():
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["idem"] = req.headers.get("Idempotency-Key")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"status": "DONE", "paymentKey": "pk_1", "approvedAt": "2026-10-09T10:00:05+09:00"})

    r = _toss(handler).charge("bk_1", "cus_1", "sub1-20261009-1", 19000, "월 구독")
    assert r.success and r.payment_key == "pk_1"
    assert seen["path"] == "/v1/billing/bk_1"
    assert seen["idem"] == "sub1-20261009-1"
    assert seen["body"]["amount"] == 19000 and seen["body"]["orderId"] == "sub1-20261009-1"


def test_toss_charge_decline_is_not_retryable_but_5xx_and_network_are():
    decline = _toss(lambda req: httpx.Response(400, json={"code": "REJECT_CARD_COMPANY", "message": "한도초과"}))
    r = decline.charge("bk", "cus", "order-1", 19000, "x")
    assert not r.success and not r.retryable and r.failure_code == "REJECT_CARD_COMPANY"

    r = _toss(lambda req: httpx.Response(500, json={})).charge("bk", "cus", "order-1", 19000, "x")
    assert not r.success and r.retryable

    def boom(req):
        raise httpx.ConnectError("down")
    r = _toss(boom).charge("bk", "cus", "order-1", 19000, "x")
    assert not r.success and r.retryable


# ─── Subscription lifecycle (needs Postgres) ─────────────────────────────────

class FakeProvider(BillingProvider):
    name = "toss"

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.charges = []

    def issue_billing_key(self, auth_key, customer_key):
        return BillingMethod(billing_key=f"bk_{auth_key}", display_name="테스트카드 1234****")

    def charge(self, billing_key, customer_key, order_id, amount, order_name, customer_email="", customer_name=""):
        self.charges.append(order_id)
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if outcome == "ok":
            return ChargeResult(success=True, payment_key=f"pk_{order_id}")
        if outcome == "network":
            return ChargeResult(success=False, retryable=True, failure_code="NETWORK_ERROR")
        return ChargeResult(success=False, failure_code="REJECT_CARD_COMPANY", failure_message="한도초과")


def _tenant(db, trial_ends_at):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (slug, church_name, trial_ends_at) VALUES ('t1', '테스트교회', %s) RETURNING id",
            (trial_ends_at,),
        )
        tid = cur.fetchone()[0]
    db.commit()
    return tid


def _register(db, tid, provider, now=NOW):
    sub = ensure_subscription(db, tid)
    return register_payment_method(db, tid, "auth", sub["customer_key"], now=now, provider=provider)


def test_register_during_trial_defers_first_charge_to_trial_end(db):
    trial_end = NOW + timedelta(days=10)
    tid = _tenant(db, trial_end)
    p = FakeProvider()
    sub = _register(db, tid, p)
    assert sub["status"] == "trialing"
    assert sub["next_billing_at"] == trial_end
    assert p.charges == []

    # 체험 종료 전에는 청구하지 않음
    assert run_due(db, now=NOW + timedelta(days=5), provider_factory=lambda n: p)["done"] == 0
    # 종료일에 첫 결제, 다음 결제일은 한 달 뒤
    assert run_due(db, now=trial_end, provider_factory=lambda n: p)["done"] == 1
    sub = get_subscription(db, tid)
    assert sub["status"] == "active"
    assert sub["current_period_start"] == trial_end
    assert sub["next_billing_at"] == add_month(trial_end, trial_end.day)
    with db.cursor() as cur:
        cur.execute("SELECT status FROM tenants WHERE id=%s", (tid,))
        assert cur.fetchone()[0] == "active"


def test_register_after_trial_charges_immediately(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    p = FakeProvider()
    sub = _register(db, tid, p)
    assert sub["status"] == "active" and len(p.charges) == 1
    assert [x["status"] for x in list_payments(db, tid)] == ["done"]


def test_register_rejects_wrong_customer_key(db):
    tid = _tenant(db, NOW)
    ensure_subscription(db, tid)
    with pytest.raises(Exception):
        register_payment_method(db, tid, "auth", "cus_other", now=NOW, provider=FakeProvider())


def test_failures_retry_then_unpaid(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    p = FakeProvider(["decline"] * (len(config.RETRY_DAYS) + 1))
    sub = _register(db, tid, p)
    assert sub["status"] == "past_due" and sub["failed_attempts"] == 1

    now = NOW
    for _ in config.RETRY_DAYS:
        now = get_subscription(db, tid)["next_billing_at"]
        run_due(db, now=now, provider_factory=lambda n: p)
    sub = get_subscription(db, tid)
    assert sub["status"] == "unpaid" and sub["next_billing_at"] is None
    assert len(set(p.charges)) == len(p.charges) == len(config.RETRY_DAYS) + 1  # 시도마다 새 주문번호

    # 카드 교체 → 즉시 재결제 성공
    p.outcomes = ["ok"]
    sub = register_payment_method(db, tid, "auth2", sub["customer_key"], now=now, provider=p)
    assert sub["status"] == "active" and sub["failed_attempts"] == 0


def test_network_error_retries_with_same_order_id(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    p = FakeProvider(["network", "ok"])
    sub = _register(db, tid, p)
    assert sub["failed_attempts"] == 0
    run_due(db, now=sub["next_billing_at"], provider_factory=lambda n: p)
    assert p.charges[0] == p.charges[1]
    payments = list_payments(db, tid)
    assert len(payments) == 1 and payments[0]["status"] == "done"


def test_cancel_stops_charges_but_keeps_paid_period(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    p = FakeProvider()
    sub = _register(db, tid, p)
    paid_until = sub["current_period_end"]
    sub = cancel_subscription(db, tid, now=NOW + timedelta(days=3))
    assert sub["status"] == "canceled" and sub["billing_key"] is None
    assert sub["current_period_end"] == paid_until
    assert run_due(db, now=paid_until + timedelta(days=1), provider_factory=lambda n: p)["done"] == 0

    # 재가입 시 이미 낸 기간이 끝나는 날부터 청구
    sub = register_payment_method(db, tid, "auth3", sub["customer_key"], now=NOW + timedelta(days=5), provider=p)
    assert sub["status"] == "trialing" and sub["next_billing_at"] == paid_until
    assert len(p.charges) == 1
