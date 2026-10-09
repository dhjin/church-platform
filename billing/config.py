import os

from dotenv import load_dotenv

load_dotenv()

# 새 구독의 기본 결제대행사. 교회는 구독 화면에서 toss / kakaopay 중 선택할 수 있다(추후 cms 추가 예정)
BILLING_PROVIDER = os.getenv("BILLING_PROVIDER", "toss")

# 요금제. 기본(standard) 금액·이름은 기존 환경변수로도 바꿀 수 있다.
PLAN_CODE = os.getenv("BILLING_PLAN_CODE", "standard")
PLAN_NAME = os.getenv("BILLING_PLAN_NAME", "더처치플러스 월 구독")
PLAN_AMOUNT = int(os.getenv("BILLING_PLAN_AMOUNT", "19000"))

PLANS = {
    "standard": {
        "label": "스탠다드", "order_name": PLAN_NAME, "amount": PLAN_AMOUNT,
        "ai_designs_per_month": int(os.getenv("PLAN_STANDARD_AI_DESIGNS", "1")),
        "custom_requests": False,
        "features": ["교회 홈페이지 전체 기능", "테마 카탈로그·직접 디자인 수정", "AI 맞춤 디자인 월 1회 체험"],
    },
    "plus": {
        "label": "플러스", "order_name": "더처치플러스 플러스 월 구독",
        "amount": int(os.getenv("PLAN_PLUS_AMOUNT", "29000")),
        "ai_designs_per_month": int(os.getenv("PLAN_PLUS_AI_DESIGNS", "10")),
        "custom_requests": False,
        "features": ["스탠다드 전체", "AI 맞춤 디자인 월 10회(요구사항 인터뷰·수정 요청)"],
    },
    "premium": {
        "label": "프리미엄", "order_name": "더처치플러스 프리미엄 월 구독",
        "amount": int(os.getenv("PLAN_PREMIUM_AMOUNT", "49000")),
        "ai_designs_per_month": int(os.getenv("PLAN_PREMIUM_AI_DESIGNS", "30")),
        "custom_requests": True,
        "features": ["플러스 전체", "AI 맞춤 디자인 월 30회", "전문가 검수 맞춤 제작 요청"],
    },
}
PLAN_ORDER = ["standard", "plus", "premium"]

# AI 맞춤 제작 셋업(1회): 운영자가 요구사항 상담 후 AI 디자인안 적용과 기존 홈페이지 내용 이전까지 대행
SETUP_FEE_AMOUNT = int(os.getenv("SETUP_FEE_AMOUNT", "99000"))
SETUP_FEE_NAME = os.getenv("SETUP_FEE_NAME", "더처치플러스 AI 맞춤 제작 셋업")


def plan_info(plan: str) -> dict:
    return PLANS.get(plan) or PLANS["standard"]


# 결제 실패 시 재시도 간격(일). 모두 실패하면 구독은 unpaid 상태가 된다.
RETRY_DAYS = [int(d) for d in os.getenv("BILLING_RETRY_DAYS", "1,3,3").split(",") if d.strip()]

# 네트워크 오류 등 결과를 알 수 없는 경우 같은 주문번호로 다시 시도하기까지의 간격(분)
UNKNOWN_RETRY_MINUTES = int(os.getenv("BILLING_UNKNOWN_RETRY_MINUTES", "60"))

TOSS_CLIENT_KEY = os.getenv("TOSS_CLIENT_KEY", "")
TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")
TOSS_API_BASE = os.getenv("TOSS_API_BASE", "https://api.tosspayments.com")

# 카카오페이 정기결제. 테스트 CID: TCSUBSCRIP (가맹 계약 없이 개발 가능)
KAKAOPAY_SECRET_KEY = os.getenv("KAKAOPAY_SECRET_KEY", "")
KAKAOPAY_CID = os.getenv("KAKAOPAY_CID", "TCSUBSCRIP")
KAKAOPAY_API_BASE = os.getenv("KAKAOPAY_API_BASE", "https://open-api.kakaopay.com")
