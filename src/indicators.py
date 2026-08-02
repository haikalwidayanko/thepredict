"""Standalone technical indicator helpers (no ta-lib dependency)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(closes: pd.Series, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def ema(closes: pd.Series, period: int) -> pd.Series:
    return closes.ewm(span=period, adjust=False).mean()


def ema_cross_signal(closes: pd.Series, fast: int = 9, slow: int = 21) -> float:
    """Returns signed strength in [-1, 1]: positive = fast EMA above slow EMA."""
    if len(closes) < slow:
        return 0.0
    ema_fast = ema(closes, fast).iloc[-1]
    ema_slow = ema(closes, slow).iloc[-1]
    if ema_slow == 0:
        return 0.0
    spread_pct = (ema_fast - ema_slow) / ema_slow * 100
    return float(np.tanh(spread_pct / 1.5))


def momentum(closes: pd.Series, lookback: int = 10) -> float:
    """% change over lookback bars."""
    if len(closes) <= lookback:
        return 0.0
    past = closes.iloc[-lookback - 1]
    if past == 0:
        return 0.0
    return float((closes.iloc[-1] - past) / past * 100)


def order_book_imbalance(bids: list[tuple[float, float]], asks: list[tuple[float, float]], depth: int = 20) -> float:
    """Returns value in [-1, 1]: positive = more bid volume (buy pressure) near top of book."""
    bid_vol = sum(q for _, q in bids[:depth])
    ask_vol = sum(q for _, q in asks[:depth])
    total = bid_vol + ask_vol
    if total == 0:
        return 0.0
    return (bid_vol - ask_vol) / total
