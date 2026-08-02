"""Turns a Polymarket market into an implied-probability view with a liquidity
confidence label. This deliberately reports the market's own price as-is
instead of pretending to have an independent edge over it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

LIQUIDITY_HIGH = 50_000
LIQUIDITY_MEDIUM = 5_000

# Times are shown in WIB (Waktu Indonesia Barat, UTC+7).
WIB = timezone(timedelta(hours=7))

_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
          "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def parse_iso(value: str | None) -> datetime | None:
    """Parse Polymarket's ISO 8601 timestamps (which end in 'Z')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def format_wib(value: str | None) -> str:
    """Render an ISO timestamp as e.g. 'Sab, 2 Agu 2026 · 19:00 WIB'."""
    dt = parse_iso(value)
    if dt is None:
        return "tanggal tidak tersedia"
    local = dt.astimezone(WIB)
    return (
        f"{_HARI[local.weekday()]}, {local.day} {_BULAN[local.month - 1]} "
        f"{local.year} · {local:%H:%M} WIB"
    )


def match_status(start: str | None, end: str | None) -> str:
    """Label derived purely from the schedule, not from any prediction."""
    now = datetime.now(timezone.utc)
    start_dt = parse_iso(start)
    end_dt = parse_iso(end)

    if start_dt and now < start_dt:
        delta = start_dt - now
        # Round to nearest unit -- flooring would show "29 menit" for a match
        # starting in 30 minutes, which reads as wrong.
        if delta < timedelta(hours=1):
            return f"⏳ Mulai dalam {round(delta.total_seconds() / 60)} menit"
        if delta < timedelta(days=1):
            return f"⏳ Mulai dalam {round(delta.total_seconds() / 3600)} jam"
        return f"📅 {round(delta.total_seconds() / 86400)} hari lagi"

    if end_dt and now > end_dt:
        return "✅ Sudah lewat jadwal"

    return "🔴 Berlangsung / menunggu hasil"


@dataclass
class OutcomeProbability:
    outcome: str
    probability: float  # 0-1


def liquidity_confidence(liquidity: float) -> str:
    if liquidity >= LIQUIDITY_HIGH:
        return "Tinggi"
    if liquidity >= LIQUIDITY_MEDIUM:
        return "Sedang"
    return "Rendah"


# Sub-markets we deliberately hide: the user wants the overall match result,
# not per-set / total-games side bets.
_SUB_MARKET_KEYWORDS = (
    "set ", " set", "1st set", "2nd set", "3rd set", "first set", "second set",
    "tiebreak", "tie-break", "tie break",
    "total games", "total game", "games won", "number of games",
    "over ", "under ", "handicap", "spread",
    "straight sets", "correct score", "double fault", "aces", "ace ",
)


def is_match_winner_market(question: str) -> bool:
    """True if the market is about who wins the match overall.

    Uses an explicit keyword blocklist so the filtering is inspectable rather
    than a black box. Anything mentioning sets, totals, or prop bets is out.
    """
    if not question:
        return False
    q = f" {question.lower()} "
    return not any(kw in q for kw in _SUB_MARKET_KEYWORDS)


def analyze_market(market: dict) -> dict:
    outcomes = [
        OutcomeProbability(outcome=o, probability=p)
        for o, p in zip(market["outcomes"], market["prices"])
    ]
    outcomes.sort(key=lambda x: x.probability, reverse=True)
    favorite = outcomes[0] if outcomes else None

    return {
        "question": market["question"],
        "outcomes": outcomes,
        "favorite": favorite,
        "liquidity": market["liquidity"],
        "volume": market["volume"],
        "confidence_label": liquidity_confidence(market["liquidity"]),
        "end_date": market["end_date"],
        "slug": market["slug"],
    }
