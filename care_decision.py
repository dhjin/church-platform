"""목양 연락 우선순위: '이번 주 누구부터 연락할까'를 정한다.

결정은 교체 가능한 결정기(decider)가 한다.
- RuleDecider: 기본 규칙. 항상 동작한다.
- JevDecider: TypeSafe Jev 의사결정 모델(https://docs.typesafe.ai/api). TYPESAFE_API_KEY 가 있으면 쓰고,
  실패하면 기본 규칙으로 돌아간다. API 키는 k8s secret church-platform-secret 에서 주입된다.
  주소는 모든 사용자 공통 고정값이라 TYPESAFE_API_URL 로 바꿀 수만 있게 둔다.

결정기에는 이름·연락처를 보내지 않는다. 성도 ID와 숫자·플래그 특성만 보낸다.
상담 일지(E2EE)는 서버가 읽을 수 없으므로 여기서도 쓰지 않는다.
"""
import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import date

log = logging.getLogger(__name__)

NO_CONTACT_DAYS = 9999      # 연락 기록이 없는 경우
NEW_MEMBER_DAYS = 180       # 등록 후 이 기간 안이면 새가족
UPCOMING_DAYS = 7           # 생일·기념일이 이 기간 안에 오면 표시
DEFAULT_LIMIT = 5


@dataclass
class CareCandidate:
    member_id: int
    days_since_contact: int
    is_new_member: bool = False
    days_to_birthday: int | None = None
    days_to_join_anniversary: int | None = None
    days_to_baptism_anniversary: int | None = None
    cell_group_missing: bool = False

    def features(self) -> dict:
        return {
            "member_id": self.member_id,
            "days_since_contact": self.days_since_contact,
            "is_new_member": self.is_new_member,
            "days_to_birthday": self.days_to_birthday,
            "days_to_join_anniversary": self.days_to_join_anniversary,
            "days_to_baptism_anniversary": self.days_to_baptism_anniversary,
            "cell_group_missing": self.cell_group_missing,
        }


@dataclass
class CareRecommendation:
    member_id: int
    score: float
    reasons: list[str] = field(default_factory=list)


def _days_to_next(d: date | None, today: date) -> int | None:
    """올해(또는 내년) 같은 월·일까지 남은 일수. 2월 29일은 평년엔 2월 28일로 본다."""
    if d is None:
        return None
    for year in (today.year, today.year + 1):
        try:
            nxt = d.replace(year=year)
        except ValueError:
            nxt = date(year, 2, 28)
        if nxt >= today:
            return (nxt - today).days
    return None


def build_candidates(members: list[dict], today: date) -> list[CareCandidate]:
    """활성 성도만 후보로 만든다. members 행은 congregation_members 컬럼 이름을 키로 쓴다."""
    out = []
    for m in members:
        if m.get("status") != "active":
            continue
        lcd = m.get("last_contact_date")
        join = m.get("join_date")
        out.append(CareCandidate(
            member_id=m["id"],
            days_since_contact=(today - lcd).days if lcd else NO_CONTACT_DAYS,
            is_new_member=bool(join and 0 <= (today - join).days <= NEW_MEMBER_DAYS),
            days_to_birthday=_days_to_next(m.get("birth_date"), today),
            days_to_join_anniversary=_days_to_next(join, today) if join and join.year < today.year else None,
            days_to_baptism_anniversary=(
                _days_to_next(m.get("baptism_date"), today)
                if m.get("baptism_date") and m["baptism_date"].year < today.year else None
            ),
            cell_group_missing=not (m.get("cell_group") or "").strip(),
        ))
    return out


def _upcoming(days: int | None) -> bool:
    return days is not None and days <= UPCOMING_DAYS


class RuleDecider:
    name = "기본 규칙"

    def decide(self, candidates: list[CareCandidate], limit: int = DEFAULT_LIMIT) -> list[CareRecommendation]:
        recs = [r for r in (self.evaluate(c) for c in candidates) if r.score > 0]
        recs.sort(key=lambda r: r.score, reverse=True)
        return recs[:limit]

    @staticmethod
    def evaluate(c: CareCandidate) -> CareRecommendation:
        """규칙 점수와 사람이 읽을 이유."""
        score = 0.0
        reasons = []
        if c.days_since_contact >= NO_CONTACT_DAYS:
            score += 50
            reasons.append("연락 기록 없음")
        elif c.days_since_contact >= 30:
            # 30일부터 점수가 붙고, 기존 알림 기준(90일)이면 확실히 위로 온다.
            score += min(c.days_since_contact, 365) / 3
            reasons.append(f"{c.days_since_contact}일 연락 없음")
        if c.is_new_member and c.days_since_contact >= 14:
            score += 40
            reasons.append("새가족 (등록 6개월 이내)")
        if _upcoming(c.days_to_birthday):
            score += 25
            reasons.append("생일 오늘" if c.days_to_birthday == 0 else f"생일 {c.days_to_birthday}일 후")
        if _upcoming(c.days_to_join_anniversary):
            score += 10
            reasons.append("등록 기념일 임박")
        if _upcoming(c.days_to_baptism_anniversary):
            score += 10
            reasons.append("세례 기념일 임박")
        if c.cell_group_missing and c.is_new_member:
            score += 10
            reasons.append("구역 미배정")
        return CareRecommendation(c.member_id, round(score, 1), reasons)


DEFAULT_JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_LEVELS = [
    "이번 주에는 따로 연락하지 않아도 된다",
    "여유가 있으면 연락하면 좋다",
    "이번 주에 연락하는 것이 좋다",
    "이번 주에 꼭 먼저 연락해야 한다",
]
JEV_INSTRUCTIONS = (
    "한국 교회 담임목사가 이번 주에 어떤 성도에게 먼저 안부 연락을 해야 할지 정하려 한다. "
    "state.members 에서 member_id 가 {mid} 인 성도를 보고, 이번 주 연락이 얼마나 필요한지 판단하라. "
    "days_since_contact 는 마지막 연락 후 지난 날수(9999는 연락 기록 없음), is_new_member 는 등록 6개월 이내, "
    "days_to_* 는 생일·등록·세례 기념일까지 남은 날수(null은 해당 없음)다."
)
MAX_JEV_CANDIDATES = 60     # 한 번에 판단 받을 최대 인원 (비용·응답 크기 제한)
CACHE_TTL_SECONDS = 6 * 3600


class JevDecider:
    """TypeSafe Jev 로 연락 우선순위를 정한다.

    규칙 점수가 있는 성도만 후보로 보내고(최대 MAX_JEV_CANDIDATES명), 성도마다 'score' 질문 하나를 묻는다.
    순서는 Jev 점수로 정하고, 화면에 보일 이유는 규칙이 만든 설명을 그대로 쓴다.
    같은 후보 목록이면 몇 시간 동안 결과를 재사용해 대시보드를 열 때마다 호출하지 않는다.
    """

    name = "Jev"
    _cache: dict = {}
    _lock = threading.Lock()

    def __init__(self, url: str, api_key: str, model: str = "jev-latest", timeout: float = 15.0):
        self.url = url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def decide(self, candidates: list[CareCandidate], limit: int = DEFAULT_LIMIT) -> list[CareRecommendation]:
        rules = {c.member_id: RuleDecider.evaluate(c) for c in candidates}
        pool = sorted((c for c in candidates if rules[c.member_id].score > 0),
                      key=lambda c: rules[c.member_id].score, reverse=True)[:MAX_JEV_CANDIDATES]
        if not pool:
            return []
        scores = self._scores(pool)
        known = {c.member_id for c in pool}
        recs = [
            CareRecommendation(mid, round(score, 3), rules[mid].reasons)
            for mid, score in scores.items() if mid in known  # 보낸 적 없는 ID는 무시
        ]
        recs.sort(key=lambda r: (r.score, rules[r.member_id].score), reverse=True)
        return recs[:limit]

    def _scores(self, pool: list[CareCandidate]) -> dict[int, float]:
        import time
        features = [c.features() for c in pool]
        key = hashlib.sha256(json.dumps([self.model, features], sort_keys=True).encode()).hexdigest()
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < CACHE_TTL_SECONDS:
                return hit[1]
        scores = self._request(features)
        with self._lock:
            if len(self._cache) > 500:
                self._cache.clear()
            self._cache[key] = (now, scores)
        return scores

    def _request(self, features: list[dict]) -> dict[int, float]:
        import httpx
        body = {
            "model": self.model,
            "state": {"members": features},
            "questions": {
                f"m{f['member_id']}": {
                    "type": "score",
                    "instructions": JEV_INSTRUCTIONS.format(mid=f["member_id"]),
                    "criteria": JEV_LEVELS,
                }
                for f in features
            },
        }
        resp = httpx.post(
            self.url, json=body, timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        resp.raise_for_status()
        answers = resp.json()["answers"]
        out = {}
        for f in features:
            a = answers.get(f"m{f['member_id']}")
            if a and isinstance(a.get("score"), (int, float)):
                out[f["member_id"]] = float(a["score"])
        if not out:
            raise ValueError("Jev 응답에 점수가 없습니다")
        return out


def get_decider():
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if api_key:
        url = os.getenv("TYPESAFE_API_URL", "").strip() or DEFAULT_JEV_URL
        model = os.getenv("TYPESAFE_JEV_MODEL", "").strip() or "jev-latest"
        return JevDecider(url, api_key, model)
    return RuleDecider()


def recommend(members: list[dict], today: date, limit: int = DEFAULT_LIMIT, decider=None) -> tuple[list[CareRecommendation], str]:
    """추천 목록과 실제로 결정한 결정기 이름을 돌려준다. Jev가 실패하면 기본 규칙으로 대체한다."""
    candidates = build_candidates(members, today)
    decider = decider or get_decider()
    if not isinstance(decider, RuleDecider):
        try:
            return decider.decide(candidates, limit), decider.name
        except Exception:
            log.warning("care decider %s failed; falling back to rules", decider.name, exc_info=True)
    rules = RuleDecider()
    return rules.decide(candidates, limit), rules.name
