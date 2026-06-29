"""Юнит-тесты token-bucket лимитера (детерминированно, без реального сна)."""

from src.obs.ratelimit import Limiters, RateLimiter


def test_burst_then_throttle():
    """capacity=2, rate=2/с: два токена сразу, третий требует ~0.5 с ожидания."""
    now = [0.0]
    rl = RateLimiter(rate=2, capacity=2, clock=lambda: now[0])
    assert rl._take(now[0]) == 0.0  # 1-й токен
    assert rl._take(now[0]) == 0.0  # 2-й токен
    wait = rl._take(now[0])  # бакет пуст
    assert abs(wait - 0.5) < 1e-9


def test_refill_over_time():
    """Спустя 1 с при rate=2/с бакет пополняется и токен снова доступен."""
    now = [0.0]
    rl = RateLimiter(rate=2, capacity=2, clock=lambda: now[0])
    rl._take(now[0])
    rl._take(now[0])  # опустошили
    now[0] = 1.0
    assert rl._take(now[0]) == 0.0  # пополнился


def test_limiters_registry_reuses_host():
    lim = Limiters()
    a = lim.host("ncbi", 10)
    b = lim.host("ncbi", 10)
    assert a is b
