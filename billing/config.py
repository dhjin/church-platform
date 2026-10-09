import os

from dotenv import load_dotenv

load_dotenv()

# 새 구독의 기본 결제대행사. 교회는 구독 화면에서 toss / kakaopay 중 선택할 수 있다(추후 cms 추가 예정)
BILLING_PROVIDER = os.getenv("BILLING_PROVIDER", "toss")

# 요금제: 교회당 월 19,000원
PLAN_CODE = os.getenv("BILLING_PLAN_CODE", "standard")
PLAN_NAME = os.getenv("BILLING_PLAN_NAME", "더처치플러스 월 구독")
PLAN_AMOUNT = int(os.getenv("BILLING_PLAN_AMOUNT", "19000"))

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
