from billing import config
from billing.providers.base import BillingMethod, BillingProvider, BillingProviderError, ChargeResult
from billing.providers.toss import TossBillingProvider

PROVIDERS = {
    TossBillingProvider.name: TossBillingProvider,
}


def get_provider(name: str = "") -> BillingProvider:
    name = name or config.BILLING_PROVIDER
    if name not in PROVIDERS:
        raise BillingProviderError("UNKNOWN_PROVIDER", f"지원하지 않는 결제대행사: {name}")
    return PROVIDERS[name]()


__all__ = [
    "BillingMethod", "BillingProvider", "BillingProviderError", "ChargeResult",
    "TossBillingProvider", "PROVIDERS", "get_provider",
]
