import pytest
from datetime import date, timedelta

import care_decision as cd

TODAY = date(2026, 10, 19)


def member(id, **kw):
    base = {"id": id, "name": f"성도{id}", "status": "active", "cell_group": "1구역",
            "last_contact_date": TODAY - timedelta(days=5), "birth_date": None,
            "join_date": date(2020, 1, 1), "baptism_date": None}
    base.update(kw)
    return base


def test_rules_rank_by_need_and_explain():
    members = [
        member(1),  # 최근 연락, 추천 없음
        member(2, last_contact_date=TODAY - timedelta(days=120)),
        member(3, last_contact_date=None),
        member(4, join_date=TODAY - timedelta(days=30), last_contact_date=TODAY - timedelta(days=20), cell_group=""),
        member(5, birth_date=date(1980, 10, 22)),
        member(6, status="inactive", last_contact_date=None),
    ]
    recs, source = cd.recommend(members, TODAY, decider=cd.RuleDecider())
    ids = [r.member_id for r in recs]
    assert source == "기본 규칙"
    assert 1 not in ids and 6 not in ids
    assert ids[0] == 4 or ids[0] == 3
    assert set(ids) == {2, 3, 4, 5}
    by = {r.member_id: r.reasons for r in recs}
    assert "120일 연락 없음" in by[2]
    assert "연락 기록 없음" in by[3]
    assert "새가족 (등록 6개월 이내)" in by[4] and "구역 미배정" in by[4]
    assert "생일 3일 후" in by[5]


def test_limit():
    members = [member(i, last_contact_date=None) for i in range(10)]
    recs, _ = cd.recommend(members, TODAY, limit=3, decider=cd.RuleDecider())
    assert len(recs) == 3


def test_leap_day_birthday():
    assert cd._days_to_next(date(2000, 2, 29), date(2027, 2, 27)) == 1


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _clear_cache():
    cd.JevDecider._cache.clear()


def _jev_members():
    return [
        member(1, last_contact_date=None),                       # 규칙 1등
        member(2, last_contact_date=TODAY - timedelta(days=60)),
        member(3, birth_date=date(1990, 10, 20)),
        member(4),                                                # 규칙 점수 0 → 보내지 않음
    ]


def test_jev_request_shape_and_ranking(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout, headers):
        sent.update(url=url, body=json, headers=headers)
        return _Resp(200, {"model": "jev-1", "answers": {
            "m1": {"type": "score", "score": 1.2}, "m2": {"type": "score", "score": 2.9},
            "m3": {"type": "score", "score": 2.1}, "m999": {"type": "score", "score": 3.0},
        }, "usage": {}})

    monkeypatch.setattr("httpx.post", fake_post)
    jev = cd.JevDecider(cd.DEFAULT_JEV_URL, "k")
    recs, source = cd.recommend(_jev_members(), TODAY, decider=jev)

    assert source == "Jev"
    assert [r.member_id for r in recs] == [2, 3, 1]          # Jev 점수 순
    assert recs[0].reasons == ["60일 연락 없음"]              # 이유는 규칙 설명
    assert sent["url"] == "https://api.typesafe.ai/v1/systemone"
    assert sent["headers"]["Authorization"] == "Bearer k"
    body = sent["body"]
    assert body["model"] == "jev-latest"
    assert set(body["questions"]) == {"m1", "m2", "m3"}       # 점수 0인 4번은 안 보냄
    q = body["questions"]["m2"]
    assert q["type"] == "score" and len(q["criteria"]) == 4 and "member_id 가 2" in q["instructions"]
    dumped = str(body)
    assert "성도" in dumped and "성도1" not in dumped and "010" not in dumped  # 이름·연락처 미전송


def test_jev_result_is_cached(monkeypatch):
    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append(1)
        return _Resp(200, {"answers": {k: {"score": 1.0} for k in json["questions"]}})

    monkeypatch.setattr("httpx.post", fake_post)
    jev = cd.JevDecider(cd.DEFAULT_JEV_URL, "k")
    cd.recommend(_jev_members(), TODAY, decider=jev)
    cd.recommend(_jev_members(), TODAY, decider=jev)
    assert len(calls) == 1


def test_jev_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(529, {}))
    recs, source = cd.recommend(_jev_members(), TODAY, decider=cd.JevDecider(cd.DEFAULT_JEV_URL, "k"))
    assert source == "기본 규칙"
    assert recs[0].member_id == 1


def test_jev_empty_answers_falls_back(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(200, {"answers": {}}))
    _, source = cd.recommend(_jev_members(), TODAY, decider=cd.JevDecider(cd.DEFAULT_JEV_URL, "k"))
    assert source == "기본 규칙"


def test_get_decider_env(monkeypatch):
    for k in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL", "TYPESAFE_JEV_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(cd.get_decider(), cd.RuleDecider)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    d = cd.get_decider()
    assert isinstance(d, cd.JevDecider) and d.api_key == "test-key" and d.url == cd.DEFAULT_JEV_URL
    monkeypatch.setenv("TYPESAFE_API_URL", "https://other.example/v1")
    assert cd.get_decider().url == "https://other.example/v1"
