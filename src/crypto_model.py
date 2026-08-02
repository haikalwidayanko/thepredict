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


# Price-action-only weights, used for both the multi-timeframe blend and the
# backtest (which can't see historical funding/order-book data -- see
# src/backtest.py). Derived from WEIGHTS' rsi:ema_cross:momentum ratio
# (0.25:0.30:0.20 = 5:6:4), renormalized so the three sum to 1.
PRICE_ACTION_WEIGHTS = {
    "rsi": 5 / 15,
    "ema_cross": 6 / 15,
    "momentum": 4 / 15,
}

# Higher timeframes are weighted more heavily because they carry less noise;
# this is a starting assumption, not a validated conclusion -- use the
# Backtest tab to check whether it actually beats equal-weighting before
# trusting it.
MTF_WEIGHTS = {"15m": 0.25, "1h": 0.40, "4h": 0.35}
MTF_INTERVALS = list(MTF_WEIGHTS.keys())


def timeframe_score(closes) -> dict:
    """Price-action-only score (RSI + EMA cross + momentum) for one timeframe.

    Deliberately excludes funding rate and order-book imbalance: those are
    account/market-microstructure snapshots, not timeframe-specific, so they
    are added once at the top level rather than recomputed per timeframe.

    Returns both the normalized signals (used by backtest.py to score each
    component standalone) and the blended score.
    """
    rsi_value = ind.rsi(closes)
    ema_signal = ind.ema_cross_signal(closes)
    momentum_value = ind.momentum(closes)
    rsi_signal = _rsi_signal(rsi_value)
    momentum_signal = float(np.tanh(momentum_value / 3))

    score = (
        rsi_signal * PRICE_ACTION_WEIGHTS["rsi"]
        + ema_signal * PRICE_ACTION_WEIGHTS["ema_cross"]
        + momentum_signal * PRICE_ACTION_WEIGHTS["momentum"]
    )
    return {
        "rsi": rsi_value,
        "rsi_signal": rsi_signal,
        "ema_signal": ema_signal,
        "momentum": momentum_value,
        "momentum_signal": momentum_signal,
        "score": float(np.clip(score, -1, 1)),
    }


def predict_mtf(symbol: str, klines_by_tf: dict, funding_rate: float, order_book: dict,
                tf_weights: dict | None = None) -> dict:
    """Multi-timeframe prediction: blends price-action across intervals, then
    adds funding rate and order-book imbalance once at the end.

    `klines_by_tf` maps interval string ("15m", "1h", "4h") to a klines
    DataFrame for that interval. Missing intervals are skipped and the
    remaining weights are renormalized, so a partial fetch degrades instead
    of crashing.
    """
    weights = tf_weights or MTF_WEIGHTS

    tf_results = {}
    for interval in MTF_INTERVALS:
        df = klines_by_tf.get(interval)
        if df is None or len(df) == 0:
            continue
        tf_results[interval] = timeframe_score(df["close"])

    if not tf_results:
        raise ValueError("Tidak ada data klines untuk timeframe manapun")

    used_weight_sum = sum(weights[tf] for tf in tf_results)
    price_action_score = sum(
        tf_results[tf]["score"] * weights[tf] / used_weight_sum for tf in tf_results
    )

    # Alignment: how many of the available timeframes agree with the blended
    # direction. Shown for transparency; not used to inflate confidence
    # beyond what the backtest actually supports.
    blended_direction = 1 if price_action_score >= 0 else -1
    agreeing = sum(
        1 for r in tf_results.values()
        if (1 if r["score"] >= 0 else -1) == blended_direction
    )

    ob_imbalance = ind.order_book_imbalance(order_book["bids"], order_book["asks"])
    funding_signal = _funding_signal(funding_rate)

    # price_action_score already sums the three PRICE_ACTION_WEIGHTS (=1) at
    # full strength; rescale it into the slice WEIGHTS reserves for those
    # three signals combined, so the overall blend still totals WEIGHTS.
    price_action_share = WEIGHTS["rsi"] + WEIGHTS["ema_cross"] + WEIGHTS["momentum"]
    score = (
        price_action_score * price_action_share
        + funding_signal * WEIGHTS["funding_rate"]
        + ob_imbalance * WEIGHTS["order_book"]
    )
    score = float(np.clip(score, -1, 1))

    direction = "NAIK" if score >= 0 else "TURUN"
    confidence = min(abs(score), 1.0) * MAX_CONFIDENCE

    any_tf = next(iter(tf_results))
    last_price = float(klines_by_tf[any_tf]["close"].iloc[-1])

    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "last_price": last_price,
        "funding_rate": funding_rate,
        "timeframes": tf_results,
        "alignment": (agreeing, len(tf_results)),
        "breakdown": [
            SignalBreakdown("Price Action (MTF)", price_action_score, price_action_score, price_action_share),
            SignalBreakdown("Funding Rate", funding_rate, funding_signal, WEIGHTS["funding_rate"]),
            SignalBreakdown("Order Book Imbalance", ob_imbalance, ob_imbalance, WEIGHTS["order_book"]),
        ],
    }


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
