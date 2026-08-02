"""Walk-forward backtest for the price-action ensemble (RSI + EMA cross +
momentum, blended across 15m/1h/4h).

Scope, stated plainly: this backtests the *price-action* portion of the model
only. Funding rate and order-book imbalance are excluded because neither
Binance nor Gate.io serve historical order-book depth (only a live snapshot
exists), and mixing in historical funding while leaving out order-book would
test an ensemble that never actually runs live. So what you see here is a
lower bound on the full model's real performance, not the whole story.

The loop never looks ahead: at each simulated point in time, only klines
whose timestamp is <= that point are used, exactly mirroring what the live
page can see when it makes a prediction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import crypto_model as cm

MIN_BARS_FOR_SIGNAL = 25  # EMA-21 needs ~21 bars to stabilize; a bit of margin
DEFAULT_HORIZON_BARS = 16  # 16 * 15m = 4h, matching tracking.DEFAULT_HORIZON_HOURS


def resample_closes(klines_15m: pd.DataFrame, rule: str) -> pd.Series:
    """Aggregate a 15m close-price series into a coarser timeframe.

    label='right', closed='left': a bin covering [T, T+rule) is labeled T+rule
    and only exists once fully formed -- so filtering `series.index <= t`
    later can never pull in a still-forming (leaking) bar.
    """
    indexed = klines_15m.set_index("open_time")["close"]
    return indexed.resample(rule, label="right", closed="left").last().dropna()


def _signal_direction(value: float) -> int:
    return 1 if value >= 0 else -1


def run_price_action_backtest(klines_15m: pd.DataFrame, horizon_bars: int = DEFAULT_HORIZON_BARS,
                               mtf_weights: dict | None = None) -> dict:
    """Simulate the MTF price-action model bar-by-bar over historical data.

    Returns overall hit-rate/Brier stats, a confidence-bucket breakdown (a
    well-calibrated model should do better on its high-confidence calls than
    its low-confidence ones), and standalone hit rates for each individual
    signal per timeframe -- so you can see which components are actually
    pulling their weight instead of assuming the current weights are right.
    """
    weights = mtf_weights or cm.MTF_WEIGHTS
    df = klines_15m.reset_index(drop=True)
    n = len(df)

    closes_1h = resample_closes(df, "1h")
    closes_4h = resample_closes(df, "4h")

    if n <= MIN_BARS_FOR_SIGNAL + horizon_bars:
        raise ValueError(
            f"Data terlalu sedikit untuk backtest: butuh > "
            f"{MIN_BARS_FOR_SIGNAL + horizon_bars} candle 15m, cuma ada {n}."
        )

    trials = []
    signal_hits: dict[str, list[bool]] = {}

    for i in range(MIN_BARS_FOR_SIGNAL, n - horizon_bars):
        current_time = df["open_time"].iloc[i]
        current_close = float(df["close"].iloc[i])
        future_close = float(df["close"].iloc[i + horizon_bars])
        actual_up = future_close > current_close

        tf_series = {
            "15m": df["close"].iloc[: i + 1],
            "1h": closes_1h[closes_1h.index <= current_time],
            "4h": closes_4h[closes_4h.index <= current_time],
        }

        tf_scores = {}
        for tf, series in tf_series.items():
            if len(series) < MIN_BARS_FOR_SIGNAL:
                continue
            tf_scores[tf] = cm.timeframe_score(series)

        if not tf_scores:
            continue

        used_weight_sum = sum(weights[tf] for tf in tf_scores)
        blended_score = sum(
            tf_scores[tf]["score"] * weights[tf] / used_weight_sum for tf in tf_scores
        )
        predicted_up = blended_score >= 0
        confidence = min(abs(blended_score), 1.0) * cm.MAX_CONFIDENCE
        probability = 0.5 + confidence / 2  # same convention as tracking.py
        correct = predicted_up == actual_up

        trials.append({
            "time": current_time,
            "score": blended_score,
            "confidence": confidence,
            "probability": probability,
            "correct": correct,
        })

        for tf, s in tf_scores.items():
            for sig_name in ("rsi_signal", "ema_signal", "momentum_signal"):
                key = f"{sig_name} @ {tf}"
                predicted_sig_up = _signal_direction(s[sig_name]) == 1
                signal_hits.setdefault(key, []).append(predicted_sig_up == actual_up)

    if not trials:
        raise ValueError("Tidak ada trial yang bisa dihitung -- data historis kurang panjang.")

    total = len(trials)
    correct_count = sum(1 for t in trials if t["correct"])
    brier = sum((t["probability"] - (1.0 if t["correct"] else 0.0)) ** 2 for t in trials) / total

    # Confidence-bucket breakdown: sanity check for calibration. If the model
    # means anything, higher-confidence calls should hit more often.
    buckets = {"Rendah (<33%)": [], "Sedang (33-66%)": [], "Tinggi (>66%)": []}
    for t in trials:
        frac = t["confidence"] / cm.MAX_CONFIDENCE if cm.MAX_CONFIDENCE else 0
        bucket = "Rendah (<33%)" if frac < 1/3 else "Sedang (33-66%)" if frac < 2/3 else "Tinggi (>66%)"
        buckets[bucket].append(t["correct"])
    bucket_stats = {
        name: {"total": len(vals), "hit_rate": (sum(vals) / len(vals)) if vals else None}
        for name, vals in buckets.items()
    }

    signal_stats = {
        name: {"total": len(hits), "hit_rate": sum(hits) / len(hits)}
        for name, hits in signal_hits.items()
    }

    return {
        "total": total,
        "correct": correct_count,
        "hit_rate": correct_count / total,
        "brier": brier,
        "confidence_buckets": bucket_stats,
        "signal_hit_rates": signal_stats,
        "horizon_bars": horizon_bars,
        "date_range": (df["open_time"].iloc[MIN_BARS_FOR_SIGNAL], df["open_time"].iloc[n - horizon_bars - 1]),
    }
