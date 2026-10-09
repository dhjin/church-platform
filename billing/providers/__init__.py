from billing import config
from billing.providers.base import (
    BillingMethod, BillingProvider, BillingProviderError, ChargeResult, Registration, RegistrationStart,
)
from billing.providers.kakaopay import KakaoPayBillingProvider
from billing.providers.toss import TossBillingProvider

PROVIDERS = {
    TossBillingProvider.name: TossBillingProvider,
    KakaoPayBillingProvider.name: KakaoPayBillingProvider,
}


def get_provider(name: str = "") -> BillingProvider:
    name = name or config.BILLING_PROVIDER
    if name not in PROVIDERS:
        raise BillingProviderError("UNKNOWN_PROVIDER", f"지원하지 않는 결제대행사: {name}")
    return PROVIDERS[name]()


def configured_providers() -> list:
    """키가 설정되어 구독 화면에 보여줄 결제대행사들."""
    return [p for p in (cls() for cls in PROVIDERS.values()) if p.is_configured()]


__all__ = [
    "BillingMethod", "BillingProvider", "BillingProviderError", "ChargeResult",
    "Registration", "RegistrationStart", "TossBillingProvider", "KakaoPayBillingProvider",
    "PROVIDERS", "get_provider", "configured_providers",
]
