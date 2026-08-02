"""Thin client for Polymarket's public Gamma API (no API key needed).

Gamma catalogs events/markets; prices in `outcomePrices` are the market's own
implied probabilities (last traded / midpoint), which is what we surface as-is.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

# Sort key for events with an unparseable/missing start date -- they go last.
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
TIMEOUT = 10

TENNIS_TAG_ID = 864


class PolymarketError(RuntimeError):
    pass


def _get(path: str, params: dict | None = None):
    try:
        resp = requests.get(f"{GAMMA_BASE_URL}{path}", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise PolymarketError(f"Gagal menghubungi Polymarket API ({path}): {exc}") from exc


def _parse_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _extract_markets(event: dict) -> list[dict]:
    parsed = []
    for market in event.get("markets", []) or []:
        outcomes = _parse_json_field(market.get("outcomes"), [])
        prices = _parse_json_field(market.get("outcomePrices"), [])
        if not outcomes or not prices or len(outcomes) != len(prices):
            continue
        try:
            prices_f = [float(p) for p in prices]
        except (TypeError, ValueError):
            continue
        parsed.append({
            "question": market.get("question") or event.get("title"),
            "outcomes": outcomes,
            "prices": prices_f,
            "volume": float(market.get("volume") or 0),
            "liquidity": float(market.get("liquidity") or 0),
            "end_date": market.get("endDate") or event.get("endDate"),
            "slug": market.get("slug") or event.get("slug"),
        })
    return parsed


def get_market_by_slug(slug: str) -> dict | None:
    """Fetch a single market, used to check whether a match has settled.

    Returns a dict with `outcomes`, `prices` and `closed`, or None if the
    market cannot be found or parsed.
    """
    raw = _get("/markets", {"slug": slug})
    if not isinstance(raw, list) or not raw:
        return None

    market = raw[0]
    outcomes = _parse_json_field(market.get("outcomes"), [])
    prices = _parse_json_field(market.get("outcomePrices"), [])
    if not outcomes or len(outcomes) != len(prices):
        return None
    try:
        prices_f = [float(p) for p in prices]
    except (TypeError, ValueError):
        return None

    return {
        "outcomes": outcomes,
        "prices": prices_f,
        "closed": bool(market.get("closed")),
        "question": market.get("question"),
    }


def get_tennis_events(limit: int = 200, include_finished: bool = False) -> list[dict]:
    """Return active tennis *matches*, soonest first.

    Only head-to-head matches are returned -- tournament outrights ("2026 US
    Open Winner") and season-long props ("win more Grand Slams") are dropped,
    as are matches whose schedule has clearly passed unless asked for.
    """
    from . import match_model  # local import: avoids a circular import at module load

    raw = _get("/events", {
        "tag_id": TENNIS_TAG_ID,
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "startDate",
        "ascending": "true",
    })
    if not isinstance(raw, list):
        return []

    events = []
    for event in raw:
        title = event.get("title")
        if not match_model.is_match_event(title):
            continue

        end_date = event.get("endDate")
        if not include_finished and match_model.is_finished(end_date):
            continue

        markets = _extract_markets(event)
        if not markets:
            continue

        events.append({
            "title": title,
            "slug": event.get("slug"),
            "volume24hr": float(event.get("volume24hr") or 0),
            "start_date": event.get("startDate"),
            "end_date": end_date,
            "markets": markets,
        })

    # The API orders by startDate, but re-sort defensively: dropped events and
    # missing dates would otherwise leave gaps in an assumed ordering.
    events.sort(key=lambda e: match_model.parse_iso(e["start_date"]) or _FAR_FUTURE)
    return events
