"""Thin client for Polymarket's public Gamma API (no API key needed).

Gamma catalogs events/markets; prices in `outcomePrices` are the market's own
implied probabilities (last traded / midpoint), which is what we surface as-is.
"""
from __future__ import annotations

import json

import requests

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
TIMEOUT = 10

TAG_IDS = {
    "Sepakbola": 1059,
    "Tennis": 864,
}


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


def get_active_events(category: str, limit: int = 30) -> list[dict]:
    """Return active, unresolved events for a sport category, each with parsed markets."""
    tag_id = TAG_IDS.get(category)
    if tag_id is None:
        raise ValueError(f"Kategori tidak dikenal: {category}")

    raw = _get("/events", {
        "tag_id": tag_id,
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "volume24hr",
        "ascending": "false",
    })
    if not isinstance(raw, list):
        return []

    events = []
    for event in raw:
        markets = _extract_markets(event)
        if not markets:
            continue
        events.append({
            "title": event.get("title"),
            "slug": event.get("slug"),
            "volume24hr": float(event.get("volume24hr") or 0),
            "start_date": event.get("startDate"),
            "end_date": event.get("endDate"),
            "markets": markets,
        })
    return events
