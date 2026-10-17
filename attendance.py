"""출석 기록 도우미: 예배 종류, 기본 날짜, 장기 결석 판단."""
from datetime import date, timedelta

SERVICE_TYPES = ["주일예배", "수요예배", "금요기도회", "새벽기도", "기타"]
ABSENCE_STREAK = 3  # 최근 기록된 예배 몇 번을 연속으로 빠지면 알릴지


def default_service_date(today: date) -> date:
    """오늘이 일요일이면 오늘, 아니면 지난 일요일."""
    return today - timedelta(days=(today.weekday() + 1) % 7)


def parse_service_type(value: str | None) -> str:
    return value if value in SERVICE_TYPES else SERVICE_TYPES[0]


def long_absences(members: list[dict], last_attended: dict[int, date], recent_attendees: set[int],
                  recorded_dates: list[date], streak: int = ABSENCE_STREAK) -> list[dict]:
    """최근 기록된 예배 `streak`번을 모두 빠진 활성 성도.

    recorded_dates: 교회가 출석을 기록한 날짜(최신순). 기록이 streak번보다 적으면 판단하지 않는다.
    last_attended: 성도 ID → 마지막 출석일. recent_attendees: 최근 streak번 중 한 번이라도 나온 성도 ID.
    한 번도 출석 기록이 없는 성도는 출석 체크를 아직 안 했을 수 있어 제외한다.
    """
    if len(recorded_dates[:streak]) < streak:
        return []
    out = []
    for m in members:
        if m.get("status") != "active" or m["id"] in recent_attendees:
            continue
        last = last_attended.get(m["id"])
        if last is None:
            continue
        out.append({**m, "missed": streak, "last_attended": last})
    out.sort(key=lambda m: m["last_attended"])
    return out
