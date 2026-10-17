import signup_guard


def test_blocked_domain_includes_subdomains_and_env(monkeypatch):
    monkeypatch.delenv("BLOCKED_EMAIL_DOMAINS", raising=False)
    assert signup_guard.is_blocked_email("spam@immenseignite.info")
    assert signup_guard.is_blocked_email("spam@MAIL.ImmenseIgnite.info")
    assert not signup_guard.is_blocked_email("member@gmail.com")
    assert not signup_guard.is_blocked_email("x@notimmenseignite.info")
    monkeypatch.setenv("BLOCKED_EMAIL_DOMAINS", "bad.example, worse.example")
    assert signup_guard.is_blocked_email("a@worse.example")


def test_honeypot():
    assert not signup_guard.is_honeypot_filled("")
    assert not signup_guard.is_honeypot_filled(None)
    assert signup_guard.is_honeypot_filled("http://spam")


def test_rate_limiter_window():
    rl = signup_guard.RateLimiter(limit=2, window=60)
    assert rl.allow("ip", now=0)
    assert rl.allow("ip", now=1)
    assert not rl.allow("ip", now=2)
    assert rl.allow("other", now=2)
    assert rl.allow("ip", now=61)
