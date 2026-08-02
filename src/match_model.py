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
    outcome: str        # display label, e.g. "Cameron Norrie"
    probability: float  # 0-1
    raw_outcome: str = ""  # label as Polymarket reports it, e.g. "Yes"

    def __post_init__(self):
        if not self.raw_outcome:
            self.raw_outcome = self.outcome


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
    "o/u", "over/under", "over ", "under ", "handicap", "spread",
    "straight sets", "correct score", "double fault", "aces", "ace ",
)

# Outcome labels that prove a market is a totals bet rather than a winner
# market. Checking outcomes is more reliable than keyword-matching the title:
# "... : Match O/U 21.5" can dodge a keyword list, but its Over/Under outcomes
# give it away every time.
_TOTALS_OUTCOMES = {"over", "under"}


# A real head-to-head match is always titled "... A vs B". Season-long props
# and tournament outrights ("2026 US Open Winner", "win more Grand Slams")
# never are, so requiring the separator is the cleanest discriminator.
_VS_SEPARATORS = (" vs ", " vs. ", " v. ", " v ")


def is_match_event(title: str) -> bool:
    """True if the event is an actual head-to-head match, not a futures market."""
    if not title:
        return False
    return any(sep in f" {title.lower()} " for sep in _VS_SEPARATORS)


def is_finished(end_date: str | None, grace_hours: int = 6) -> bool:
    """True if the scheduled end is comfortably in the past.

    Polymarket sometimes keeps settled events flagged active, which would
    otherwise push stale matches to the top of a schedule-ordered list.
    """
    end_dt = parse_iso(end_date)
    if end_dt is None:
        return False
    return datetime.now(timezone.utc) > end_dt + timedelta(hours=grace_hours)


def is_match_winner_market(question: str, outcomes: list[str] | None = None) -> bool:
    """True if the market is about who wins the match overall.

    Combines an inspectable keyword blocklist with a check on the outcome
    labels, because a totals market can dodge the keywords in its title but
    never hides its Over/Under outcomes.
    """
    if not question:
        return False

    if outcomes:
        labels = {str(o).strip().lower() for o in outcomes}
        if labels & _TOTALS_OUTCOMES:
            return False

    q = f" {question.lower()} "
    return not any(kw in q for kw in _SUB_MARKET_KEYWORDS)


def players_from_title(title: str) -> list[str]:
    """Pull the two sides out of 'Tournament: A vs B' -> ['A', 'B'].

    Handles doubles ('Duncan/Ribero vs Bianchi/Sheehy') since the split is on
    the vs separator, not on individual names. Returns [] if it cannot parse.
    """
    if not title:
        return []

    # Drop a leading tournament label ("Geneva Open: ...") but keep names that
    # legitimately contain a colon-free slash, as doubles pairs do.
    body = title.split(":", 1)[1] if ":" in title else title

    lowered = body.lower()
    for sep in _VS_SEPARATORS:
        idx = lowered.find(sep)
        if idx != -1:
            left = body[:idx].strip()
            right = body[idx + len(sep):].strip()
            if left and right:
                return [left, right]
    return []


def label_outcomes(question: str, outcomes: list[str], event_title: str) -> list[str]:
    """Replace generic Yes/No labels with the player they actually refer to.

    Polymarket phrases winner markets as "Will <player> win?" with Yes/No
    outcomes. Showing "Yes 80%" tells the user nothing, so map Yes to the
    player named in the question and No to their opponent. Anything we cannot
    resolve confidently is returned untouched.
    """
    labels = [str(o).strip() for o in outcomes]
    if {l.lower() for l in labels} != {"yes", "no"}:
        return labels  # already real names

    players = players_from_title(event_title)
    if len(players) != 2:
        return labels

    q = (question or "").lower()
    subject = next((p for p in players if p.lower() in q), None)
    if subject is None:
        # Fall back to matching on surname, e.g. "Will Norrie win?" against
        # an event titled "... Cameron Norrie vs ...".
        for p in players:
            if any(part and part.lower() in q for part in p.replace("/", " ").split()):
                subject = p
                break
    if subject is None:
        return labels

    opponent = players[1] if players[0] == subject else players[0]
    return [subject if l.lower() == "yes" else opponent for l in labels]


def analyze_market(market: dict, event_title: str = "") -> dict:
    labels = label_outcomes(market["question"], market["outcomes"], event_title)
    outcomes = [
        OutcomeProbability(outcome=label, probability=p, raw_outcome=raw)
        for label, raw, p in zip(labels, market["outcomes"], market["prices"])
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
