"""Turns a Polymarket market into an implied-probability view with a liquidity
confidence label. This deliberately reports the market's own price as-is
instead of pretending to have an independent edge over it.
"""
from __future__ import annotations

from dataclasses import dataclass

LIQUIDITY_HIGH = 50_000
LIQUIDITY_MEDIUM = 5_000


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
