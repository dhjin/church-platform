from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class BillingProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class BillingMethod:
    """빌링키 발급 결과. billing_key 는 서버에만 보관하고 화면에 노출하지 않는다."""
    billing_key: str
    method: str = "card"
    display_name: str = ""  # 예: "신한카드 4330****"
    raw: dict = field(default_factory=dict)


@dataclass
class ChargeResult:
    success: bool
    # success=False 이고 retryable=True 이면 결제 여부를 알 수 없는 상태(네트워크 오류, 5xx).
    # 같은 주문번호(멱등키)로 다시 시도해야 이중결제가 나지 않는다.
    retryable: bool = False
    payment_key: Optional[str] = None
    approved_at: Optional[datetime] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class RegistrationStart:
    """서버에서 결제수단 등록을 시작하는 결제대행사(카카오페이 등)의 결과."""
    redirect_url: str
    token: str  # 승인 단계에 다시 넘겨야 하는 값 (카카오페이 tid)


@dataclass
class Registration:
    method: BillingMethod
    # 등록하면서 첫 결제가 함께 이뤄지는 결제대행사(카카오페이)는 그 결과를 돌려준다
    initial_charge: Optional[ChargeResult] = None


class BillingProvider:
    """결제대행사 빌링 API 공통 인터페이스.

    새 결제수단(금융결제원 CMS 자동이체, 카카오페이 정기결제 등)은 이 클래스를 구현해
    providers/__init__.py 의 PROVIDERS 에 등록하면 된다.
    """

    name: str = ""
    label: str = ""
    # True: 브라우저 SDK 로 등록(토스). False: 서버가 start_registration 으로 결제창 URL 을 받아 이동(카카오페이)
    client_side_registration: bool = True
    # True: 결과 미확인 결제를 같은 주문번호로 재시도해도 한 번만 승인된다(멱등키 지원).
    # False 면 자동 재시도하지 않고 수동 확인이 필요한 상태로 둔다.
    idempotent_retry: bool = True

    def is_configured(self) -> bool:
        raise NotImplementedError

    def start_registration(
        self, customer_key: str, order_id: str, amount: int, order_name: str,
        approval_url: str, cancel_url: str, fail_url: str, mobile: bool = False,
    ) -> RegistrationStart:
        raise NotImplementedError

    def complete_registration(
        self, customer_key: str, auth_key: str, token: str = "", order_id: str = "",
    ) -> Registration:
        return Registration(method=self.issue_billing_key(auth_key, customer_key))

    def deactivate(self, billing_key: str) -> None:
        """자동결제 키를 결제대행사에서도 비활성화한다(지원하는 경우)."""
        return None

    def issue_billing_key(self, auth_key: str, customer_key: str) -> BillingMethod:
        """고객 인증(카드 등록, 출금 동의 등) 후 받은 값으로 자동결제용 키를 발급한다."""
        raise NotImplementedError

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
        """발급된 키로 결제를 승인한다. order_id 는 같은 청구에 대해 항상 같아야 한다(멱등키)."""
        raise NotImplementedError
