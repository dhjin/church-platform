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


def test_jev_failure_falls_back_to_rules():
    recs, source = cd.recommend([member(1, last_contact_date=None)], TODAY, decider=cd.JevDecider("http://jev"))
    assert source == "기본 규칙"
    assert [r.member_id for r in recs] == [1]


def test_jev_results_limited_to_sent_members():
    class FakeJev(cd.JevDecider):
        def _request(self, features, limit):
            assert all("name" not in f and "phone" not in f for f in features)
            return [{"member_id": 999, "score": 9}, {"member_id": 1, "score": 5, "reasons": ["Jev 판단"]}]

    recs, source = cd.recommend([member(1)], TODAY, decider=FakeJev("http://jev"))
    assert source == "Jev"
    assert [(r.member_id, r.reasons) for r in recs] == [(1, ["Jev 판단"])]


def test_get_decider_env(monkeypatch):
    monkeypatch.delenv("JEV_API_URL", raising=False)
    assert isinstance(cd.get_decider(), cd.RuleDecider)
    monkeypatch.setenv("JEV_API_URL", "https://jev.example")
    assert isinstance(cd.get_decider(), cd.JevDecider)
