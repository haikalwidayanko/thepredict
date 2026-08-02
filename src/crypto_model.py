"""Rule-based ensemble model for short-term direction of a crypto perpetual.

Not financial advice. Combines several transparent signals into a single
weighted score so the reasoning is inspectable instead of a black box.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import indicators as ind

WEIGHTS = {
    "rsi": 0.25,
    "ema_cross": 0.30,
    "momentum": 0.20,
    "funding_rate": 0.10,
    "order_book": 0.15,
}

MAX_CONFIDENCE = 0.85  # never claim near-certainty


@dataclass
class SignalBreakdown:
    name: str
    raw_value: float
    signal: float  # normalized to [-1, 1]
    weight: float

    @property
    def contribution(self) -> float:
        return self.signal * self.weight


def _rsi_signal(rsi_value: float) -> float:
    # Center at 50; clamp extremes at +-1 around 20/80
    return float(np.clip((50 - rsi_value) / 30, -1, 1))


def _funding_signal(funding_rate: float) -> float:
    # Contrarian: very positive funding (longs paying) -> mild bearish tilt, and vice versa.
    # Typical funding rates are small (~0.0001-0.001 per 8h); scale accordingly.
    return float(np.clip(-funding_rate / 0.001, -1, 1))


def predict(symbol: str, klines_df, funding_rate: float, order_book: dict) -> dict:
    closes = klines_df["close"]

    rsi_value = ind.rsi(closes)
    ema_signal = ind.ema_cross_signal(closes)
    momentum_value = ind.momentum(closes)
    ob_imbalance = ind.order_book_imbalance(order_book["bids"], order_book["asks"])

    breakdown = [
        SignalBreakdown("RSI (14)", rsi_value, _rsi_signal(rsi_value), WEIGHTS["rsi"]),
        SignalBreakdown("EMA 9/21 Cross", ema_signal, ema_signal, WEIGHTS["ema_cross"]),
        SignalBreakdown("Momentum (10 bar)", momentum_value, float(np.tanh(momentum_value / 3)), WEIGHTS["momentum"]),
        SignalBreakdown("Funding Rate", funding_rate, _funding_signal(funding_rate), WEIGHTS["funding_rate"]),
        SignalBreakdown("Order Book Imbalance", ob_imbalance, ob_imbalance, WEIGHTS["order_book"]),
    ]

    score = sum(s.contribution for s in breakdown)  # already in roughly [-1, 1]
    score = float(np.clip(score, -1, 1))

    direction = "NAIK" if score >= 0 else "TURUN"
    confidence = min(abs(score), 1.0) * MAX_CONFIDENCE

    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "breakdown": breakdown,
        "last_price": float(closes.iloc[-1]),
        "rsi": rsi_value,
        "funding_rate": funding_rate,
    }
