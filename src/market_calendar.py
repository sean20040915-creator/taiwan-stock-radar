"""Verified non-trading weekdays for TWSE and TPEx historical *stock* OHLCV.

Explicit dates only: a missing/malformed upstream payload is never proof of
market closure. Sources:
- 2025 TPEx revised market holiday timetable:
  https://www.tpex.org.tw/storage/eb_data/11407/114030173911-1.pdf
- TPEx New Year's Day notice:
  https://www.tpex.org.tw/storage/eb_data/11312/11303031631.html
- TWSE holiday calendar (select historical year):
  https://www.twse.com.tw/zh/trading/holiday.html
- TWSE 2025 Lunar New Year notice:
  https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d6942a222b019463ddc9ae0113.pdf

Extraordinary typhoon closures are listed explicitly and must be confirmed
against exchange announcements; do not infer them from empty responses.
"""
from datetime import date

# Both TWSE and TPEx stock markets have no regular stock trades on these dates.
# Include days reserved for settlement only (no stock trading), not just holidays.
CLOSED_STOCK_MARKET_DAYS = frozenset({
    # 2024 extraordinary closures inside the archive lookback range.
    date(2024, 10, 31),  # Typhoon Kong-rey

    # 2025 revised holiday / settlement-only calendar.
    date(2025, 1, 1),
    date(2025, 1, 23),  # No trading; settlement only
    date(2025, 1, 24),  # No trading; settlement only
    date(2025, 1, 27),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 1, 30),
    date(2025, 1, 31),
    date(2025, 2, 28),
    date(2025, 4, 3),
    date(2025, 4, 4),
    date(2025, 5, 1),
    date(2025, 5, 30),
    date(2025, 9, 29),  # Teacher's Day observed
    date(2025, 10, 6),
    date(2025, 10, 10),
    date(2025, 10, 24),  # Taiwan Retrocession Day observed
    date(2025, 12, 25),

    # 2026 official calendar + separately confirmed extraordinary closures.
    date(2026, 1, 1),
    date(2026, 2, 12),  # Settlement only
    date(2026, 2, 13),  # Settlement only
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 27),
    date(2026, 4, 3),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 6, 19),
    date(2026, 7, 10),  # Extraordinary typhoon closure
    date(2026, 9, 25),
    date(2026, 9, 28),
    date(2026, 10, 9),
    date(2026, 10, 23),  # Extraordinary typhoon closure
    date(2026, 10, 26),
    date(2026, 12, 25),
})


def is_known_market_closure(market: str, trading_day: date) -> bool:
    """Explicit stock-market closures only; does NOT guess from missing data."""
    if market not in ("TWSE", "TPEX"):
        raise ValueError(f"Unexpected market: {market}")
    return trading_day in CLOSED_STOCK_MARKET_DAYS
