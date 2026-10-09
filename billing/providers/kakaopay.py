"""카카오페이 정기결제 API.

문서: https://developers.kakaopay.com/docs/payment/online/subscription
- 등록: POST /online/v1/payment/ready (정기결제 CID) → 사용자가 카카오페이에서 승인
        → approval_url 로 pg_token 전달 → POST /online/v1/payment/approve (첫 결제 + SID 발급)
- 정기 결제: POST /online/v1/payment/subscription (SID)
- 해지: POST /online/v1/payment/manage/subscription/inactive
토스와 달리 카드만 등록하는 단계가 없어, 등록 시점에 첫 달 요금이 결제된다.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from billing import config
from billing.providers.base import (
    BillingMethod, BillingProvider, BillingProviderError, ChargeResult, Registration, RegistrationStart,
)

KST = timezone(timedelta(hours=9))


class KakaoPayBillingProvider(BillingProvider):
    name = "kakaopay"
    label = "카카오페이"
    client_side_registration = False
    idempotent_retry = False

    def __init__(
        self,
        secret_key: Optional[str] = None,
        cid: Optional[str] = None,
        api_base: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 30.0,
    ):
        self.secret_key = secret_key if secret_key is not None else config.KAKAOPAY_SECRET_KEY
        self.cid = cid or config.KAKAOPAY_CID
        self.api_base = (api_base or config.KAKAOPAY_API_BASE).rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.secret_key and self.cid)

    def _post(self, path: str, body: dict) -> httpx.Response:
        if not self.secret_key:
            raise BillingProviderError("NOT_CONFIGURED", "KAKAOPAY_SECRET_KEY 가 설정되지 않았습니다.")
        with httpx.Client(
            base_url=self.api_base,
            headers={"Authorization": f"SECRET_KEY {self.secret_key}", "Content-Type": "application/json"},
            transport=self._transport,
            timeout=self._timeout,
        ) as client:
            return client.post(path, json={"cid": self.cid, **body})

    def start_registration(
        self, customer_key, order_id, amount, order_name, approval_url, cancel_url, fail_url, mobile=False,
    ) -> RegistrationStart:
        try:
            resp = self._post("/online/v1/payment/ready", {
                "partner_order_id": order_id,
                "partner_user_id": customer_key,
                "item_name": order_name,
                "quantity": 1,
                "total_amount": amount,
                "tax_free_amount": 0,
                "approval_url": approval_url,
                "cancel_url": cancel_url,
                "fail_url": fail_url,
            })
        except httpx.HTTPError as e:
            raise BillingProviderError("NETWORK_ERROR", str(e)) from e
        data = _json(resp)
        if resp.status_code != 200:
            raise _error(resp, data)
        url = data.get("next_redirect_mobile_url") if mobile else data.get("next_redirect_pc_url")
        return RegistrationStart(redirect_url=url or data.get("next_redirect_pc_url", ""), token=data["tid"])

    def complete_registration(self, customer_key, auth_key, token="", order_id="") -> Registration:
        try:
            resp = self._post("/online/v1/payment/approve", {
                "tid": token,
                "partner_order_id": order_id,
                "partner_user_id": customer_key,
                "pg_token": auth_key,
            })
        except httpx.HTTPError as e:
            raise BillingProviderError("NETWORK_ERROR", str(e)) from e
        data = _json(resp)
        if resp.status_code != 200:
            raise _error(resp, data)
        if not data.get("sid"):
            raise BillingProviderError("NO_SID", "정기결제 SID 가 발급되지 않았습니다. 정기결제용 CID 인지 확인해주세요.")
        return Registration(
            method=BillingMethod(billing_key=data["sid"], method=_method(data), display_name=_display(data), raw=data),
            initial_charge=ChargeResult(
                success=True, payment_key=data.get("tid"), approved_at=_parse_dt(data.get("approved_at")), raw=data,
            ),
        )

    def charge(
        self, billing_key, customer_key, order_id, amount, order_name, customer_email="", customer_name="",
    ) -> ChargeResult:
        try:
            resp = self._post("/online/v1/payment/subscription", {
                "sid": billing_key,
                "partner_order_id": order_id,
                "partner_user_id": customer_key,
                "item_name": order_name,
                "quantity": 1,
                "total_amount": amount,
                "tax_free_amount": 0,
            })
        except httpx.HTTPError as e:
            return ChargeResult(success=False, retryable=True, failure_code="NETWORK_ERROR", failure_message=str(e))
        data = _json(resp)
        if resp.status_code == 200 and data.get("tid"):
            return ChargeResult(
                success=True, payment_key=data["tid"], approved_at=_parse_dt(data.get("approved_at")), raw=data,
            )
        err = _error(resp, data)
        return ChargeResult(
            success=False, retryable=resp.status_code >= 500,
            failure_code=err.code, failure_message=err.message, raw=data,
        )

    def deactivate(self, billing_key: str) -> None:
        try:
            self._post("/online/v1/payment/manage/subscription/inactive", {"sid": billing_key})
        except (httpx.HTTPError, BillingProviderError):
            pass  # 해지는 우리 DB 기준으로 이미 처리됨. SID 비활성화는 최선의 노력


def _json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _error(resp: httpx.Response, data: dict) -> BillingProviderError:
    extras = data.get("extras") or {}
    code = extras.get("method_result_code") or str(data.get("error_code") or f"HTTP_{resp.status_code}")
    message = extras.get("method_result_message") or data.get("error_message") or ""
    return BillingProviderError(code, message)


def _method(data: dict) -> str:
    return "money" if data.get("payment_method_type") == "MONEY" else "card"


def _display(data: dict) -> str:
    if data.get("payment_method_type") == "MONEY":
        return "카카오페이머니"
    card = data.get("card_info") or {}
    issuer = card.get("kakaopay_issuer_corp") or card.get("issuer_corp") or ""
    return f"카카오페이 {issuer}".strip()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=KST)  # 카카오페이 응답 시각은 KST
