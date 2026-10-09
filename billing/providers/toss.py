"""토스페이먼츠 자동결제(빌링) API.

문서: https://docs.tosspayments.com/guides/v2/billing/integration
- 카드 등록: 브라우저에서 SDK v2 requestBillingAuth → successUrl 로 authKey, customerKey 전달
- 빌링키 발급: POST /v1/billing/authorizations/issue
- 결제 승인: POST /v1/billing/{billingKey}
"""
import base64
from datetime import datetime
from typing import Optional

import httpx

from billing import config
from billing.providers.base import BillingMethod, BillingProvider, BillingProviderError, ChargeResult


class TossBillingProvider(BillingProvider):
    name = "toss"
    label = "카드 (토스페이먼츠)"

    def is_configured(self) -> bool:
        return bool(self.secret_key and config.TOSS_CLIENT_KEY)

    def __init__(
        self,
        secret_key: Optional[str] = None,
        api_base: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 30.0,
    ):
        self.secret_key = secret_key if secret_key is not None else config.TOSS_SECRET_KEY
        self.api_base = (api_base or config.TOSS_API_BASE).rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        if not self.secret_key:
            raise BillingProviderError("NOT_CONFIGURED", "TOSS_SECRET_KEY 가 설정되지 않았습니다.")
        token = base64.b64encode(f"{self.secret_key}:".encode()).decode()
        return httpx.Client(
            base_url=self.api_base,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            transport=self._transport,
            timeout=self._timeout,
        )

    def issue_billing_key(self, auth_key: str, customer_key: str) -> BillingMethod:
        with self._client() as client:
            try:
                resp = client.post(
                    "/v1/billing/authorizations/issue",
                    json={"authKey": auth_key, "customerKey": customer_key},
                )
            except httpx.HTTPError as e:
                raise BillingProviderError("NETWORK_ERROR", str(e)) from e
        data = _json(resp)
        if resp.status_code != 200:
            raise BillingProviderError(data.get("code", f"HTTP_{resp.status_code}"), data.get("message", ""))
        if data.get("customerKey") and data["customerKey"] != customer_key:
            raise BillingProviderError("CUSTOMER_KEY_MISMATCH", "customerKey 가 일치하지 않습니다.")
        card = data.get("card") or {}
        company = data.get("cardCompany") or card.get("issuerCode") or ""
        number = data.get("cardNumber") or card.get("number") or ""
        return BillingMethod(
            billing_key=data["billingKey"],
            method="card",
            display_name=" ".join(p for p in (company, number) if p),
            raw=data,
        )

    def charge(
        self,
        billing_key: str,
        customer_key: str,
        order_id: str,
        amount: int,
        order_name: str,
        customer_email: str = "",
        customer_name: str = "",
    ) -> ChargeResult:
        body = {
            "customerKey": customer_key,
            "amount": amount,
            "orderId": order_id,
            "orderName": order_name,
        }
        if customer_email:
            body["customerEmail"] = customer_email
        if customer_name:
            body["customerName"] = customer_name
        with self._client() as client:
            try:
                # 같은 주문번호로 재시도해도 한 번만 승인되도록 멱등키를 함께 보낸다.
                resp = client.post(f"/v1/billing/{billing_key}", json=body, headers={"Idempotency-Key": order_id})
            except httpx.HTTPError as e:
                return ChargeResult(success=False, retryable=True, failure_code="NETWORK_ERROR", failure_message=str(e))
        data = _json(resp)
        if resp.status_code == 200 and data.get("status") == "DONE":
            return ChargeResult(
                success=True,
                payment_key=data.get("paymentKey"),
                approved_at=_parse_dt(data.get("approvedAt")),
                raw=data,
            )
        if resp.status_code >= 500:
            return ChargeResult(
                success=False, retryable=True,
                failure_code=data.get("code", f"HTTP_{resp.status_code}"),
                failure_message=data.get("message", ""), raw=data,
            )
        return ChargeResult(
            success=False,
            failure_code=data.get("code", data.get("status") or f"HTTP_{resp.status_code}"),
            failure_message=data.get("message", ""),
            raw=data,
        )


def _json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
