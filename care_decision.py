"""목양 연락 우선순위: '이번 주 누구부터 연락할까'를 정한다.

결정은 교체 가능한 결정기(decider)가 한다.
- RuleDecider: 기본 규칙. 항상 동작한다.
- JevDecider: Jev 의사결정 모델. JEV_API_URL 이 설정되면 쓰고, 실패하면 기본 규칙으로 돌아간다.

결정기에는 이름·연락처를 보내지 않는다. 성도 ID와 숫자·플래그 특성만 보낸다.
상담 일지(E2EE)는 서버가 읽을 수 없으므로 여기서도 쓰지 않는다.
"""
import logging
import os
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
        recs = []
        for c in candidates:
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
            if score > 0:
                recs.append(CareRecommendation(c.member_id, round(score, 1), reasons))
        recs.sort(key=lambda r: r.score, reverse=True)
        return recs[:limit]


class JevDecider:
    """Jev 의사결정 모델 연동 자리. API 스펙을 받으면 _request 를 채운다."""

    name = "Jev"

    def __init__(self, url: str, api_key: str = "", timeout: float = 5.0):
        self.url = url
        self.api_key = api_key
        self.timeout = timeout

    def decide(self, candidates: list[CareCandidate], limit: int = DEFAULT_LIMIT) -> list[CareRecommendation]:
        known = {c.member_id for c in candidates}
        raw = self._request([c.features() for c in candidates], limit)
        recs = []
        for item in raw:
            mid = item.get("member_id")
            if mid not in known:  # 보낸 적 없는 ID는 무시 (다른 교회 데이터 노출 방지)
                continue
            recs.append(CareRecommendation(mid, float(item.get("score", 0)), list(item.get("reasons", []))))
        return recs[:limit]

    def _request(self, features: list[dict], limit: int) -> list[dict]:
        raise NotImplementedError("Jev API 스펙 반영 전")


def get_decider():
    url = os.getenv("JEV_API_URL", "").strip()
    if url:
        return JevDecider(url, os.getenv("JEV_API_KEY", ""))
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
