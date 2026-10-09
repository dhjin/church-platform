from datetime import timedelta

import pytest

from billing import config
from billing.providers import BillingProviderError
from billing.service import (
    change_plan, charge_setup_fee, current_plan, ensure_subscription, get_subscription, list_one_time_payments, run_due,
)
from tests.test_billing import NOW, FakeProvider, _register, _tenant


class AmountProvider(FakeProvider):
    def __init__(self, outcomes=None):
        super().__init__(outcomes)
        self.amounts = []

    def charge(self, billing_key, customer_key, order_id, amount, order_name, customer_email="", customer_name=""):
        self.amounts.append((amount, order_name))
        return super().charge(billing_key, customer_key, order_id, amount, order_name, customer_email, customer_name)


def test_default_plan_is_standard(db):
    tid = _tenant(db, NOW)
    assert current_plan(db, tid) == "standard"
    assert ensure_subscription(db, tid)["amount"] == config.PLANS["standard"]["amount"]


def test_upgrade_is_immediate_and_next_charge_uses_new_amount(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    p = AmountProvider()
    sub = _register(db, tid, p)
    assert p.amounts == [(config.PLANS["standard"]["amount"], config.PLANS["standard"]["order_name"])]

    sub = change_plan(db, tid, "plus")
    assert sub["plan"] == "plus" and sub["amount"] == config.PLANS["plus"]["amount"]
    assert current_plan(db, tid) == "plus"
    run_due(db, now=sub["next_billing_at"], provider_factory=lambda n: p)
    assert p.amounts[-1] == (config.PLANS["plus"]["amount"], config.PLANS["plus"]["order_name"])
    with db.cursor() as cur:
        cur.execute("SELECT plan FROM tenants WHERE id=%s", (tid,))
        assert cur.fetchone()[0] == "plus"


def test_downgrade_waits_for_next_billing(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    p = AmountProvider()
    _register(db, tid, p)
    change_plan(db, tid, "premium")
    sub = change_plan(db, tid, "standard")
    assert sub["plan"] == "premium" and sub["scheduled_plan"] == "standard"
    assert current_plan(db, tid) == "premium"

    run_due(db, now=sub["next_billing_at"], provider_factory=lambda n: p)
    sub = get_subscription(db, tid)
    assert sub["plan"] == "standard" and sub["scheduled_plan"] is None
    assert p.amounts[-1][0] == config.PLANS["standard"]["amount"]


def test_choosing_current_plan_cancels_scheduled_downgrade(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    _register(db, tid, AmountProvider())
    change_plan(db, tid, "plus")
    change_plan(db, tid, "standard")
    sub = change_plan(db, tid, "plus")
    assert sub["plan"] == "plus" and sub["scheduled_plan"] is None


def test_plan_change_before_registration_sets_contract_amount(db):
    tid = _tenant(db, NOW - timedelta(days=1))
    ensure_subscription(db, tid)
    change_plan(db, tid, "premium")
    p = AmountProvider()
    _register(db, tid, p)
    assert p.amounts == [(config.PLANS["premium"]["amount"], config.PLANS["premium"]["order_name"])]


def test_setup_fee_requires_payment_method(db):
    tid = _tenant(db, NOW)
    ensure_subscription(db, tid)
    with pytest.raises(BillingProviderError):
        charge_setup_fee(db, tid, now=NOW, provider=AmountProvider())


def test_setup_fee_charged_once(db):
    tid = _tenant(db, NOW + timedelta(days=10))
    p = AmountProvider()
    _register(db, tid, p)
    assert p.amounts == []  # 체험 중이라 구독 결제는 아직 없음
    row = charge_setup_fee(db, tid, now=NOW, provider=p)
    assert row["status"] == "done" and row["amount"] == config.SETUP_FEE_AMOUNT
    again = charge_setup_fee(db, tid, now=NOW + timedelta(minutes=1), provider=p)
    assert again["order_id"] == row["order_id"]
    assert p.amounts == [(config.SETUP_FEE_AMOUNT, config.SETUP_FEE_NAME)]


def test_setup_fee_failure_can_retry_but_unknown_does_not(db):
    tid = _tenant(db, NOW + timedelta(days=10))
    p = AmountProvider(outcomes=["decline", "network"])
    _register(db, tid, p)
    assert charge_setup_fee(db, tid, now=NOW, provider=p)["status"] == "failed"
    assert charge_setup_fee(db, tid, now=NOW + timedelta(minutes=1), provider=p)["status"] == "unknown"
    assert charge_setup_fee(db, tid, now=NOW + timedelta(minutes=2), provider=p)["status"] == "unknown"
    assert len(p.amounts) == 2
    assert [r["status"] for r in list_one_time_payments(db, tid)] == ["unknown", "failed"]
