"""Тесты числовых распределений (plan §8): t-квантиль для HKSJ — без scipy."""

from src.stats.distributions import t_quantile


def test_t_quantile_matches_textbook_values():
    """Двусторонний 95% t-критический против табличных значений (df → t)."""
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 10: 2.228, 30: 2.042}
    for df, expected in table.items():
        assert abs(t_quantile(df) - expected) < 0.01


def test_t_quantile_approaches_normal_for_large_df():
    """При большом df t-квантиль → нормальный 1.96 (Z95)."""
    assert abs(t_quantile(1000) - 1.962) < 0.005
