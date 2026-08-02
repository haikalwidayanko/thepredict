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
from . import indicators as ind

MIN_BARS_FOR_SIGNAL = 25  # EMA-21 needs ~21 bars to stabilize; a bit of margin
DEFAULT_HORIZON_BARS = 16  # 16 * 15m = 4h, matching tracking.DEFAULT_HORIZON_HOURS
DEFAULT_TP_SL_WATCH_BARS = 64  # 16h at 15m -- how far forward to watch for TP/SL


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


def _tp_sl_outcome(df: pd.DataFrame, start_idx: int, predicted_up: bool,
                   levels: dict, max_watch_bars: int) -> str:
    """Scan forward bar-by-bar for whether TP or SL is touched first.

    Uses each bar's high/low (not just its close), since a level can be hit
    intrabar without the close reflecting it. If a single bar's range touches
    both TP and SL (a wide/gappy candle), we cannot tell which came first
    from OHLC data alone -- SL is assumed to win that tie, the conservative
    (not-optimistic) convention standard in backtesting.

    Returns "TP", "SL", or "TIMEOUT" (neither touched within the window).
    """
    end_idx = min(start_idx + 1 + max_watch_bars, len(df))
    for j in range(start_idx + 1, end_idx):
        bar = df.iloc[j]
        if predicted_up:
            tp_hit = bar["high"] >= levels["take_profit"]
            sl_hit = bar["low"] <= levels["stop_loss"]
        else:
            tp_hit = bar["low"] <= levels["take_profit"]
            sl_hit = bar["high"] >= levels["stop_loss"]
        if sl_hit:
            return "SL"
        if tp_hit:
            return "TP"
    return "TIMEOUT"


def run_price_action_backtest(klines_15m: pd.DataFrame, horizon_bars: int = DEFAULT_HORIZON_BARS,
                               mtf_weights: dict | None = None,
                               tp_sl_watch_bars: int = DEFAULT_TP_SL_WATCH_BARS) -> dict:
    """Simulate the MTF price-action model bar-by-bar over historical data.

    Returns overall hit-rate/Brier stats, a confidence-bucket breakdown (a
    well-calibrated model should do better on its high-confidence calls than
    its low-confidence ones), standalone hit rates for each individual signal
    per timeframe, and a TP/SL section testing whether crypto_model's
    ATR-based stop-loss/take-profit levels would actually have paid off.
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
    tp_sl_outcomes: list[str] = []

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

        # TP/SL check: ATR computed causally (only bars up to and including
        # i), exactly like the score above.
        atr_value = ind.atr(df.iloc[: i + 1], cm.ATR_PERIOD)
        levels = cm.compute_levels("NAIK" if predicted_up else "TURUN", current_close, atr_value)
        if levels is not None:
            outcome = _tp_sl_outcome(df, i, predicted_up, levels, tp_sl_watch_bars)
            tp_sl_outcomes.append(outcome)

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

    tp_count = tp_sl_outcomes.count("TP")
    sl_count = tp_sl_outcomes.count("SL")
    timeout_count = tp_sl_outcomes.count("TIMEOUT")
    resolved = tp_count + sl_count  # excludes timeouts: neither a win nor a loss
    tp_sl_stats = {
        "total": len(tp_sl_outcomes),
        "tp": tp_count,
        "sl": sl_count,
        "timeout": timeout_count,
        "tp_rate": (tp_count / resolved) if resolved else None,
        # Expectancy in R-multiples (1R = the SL distance): a positive number
        # means the ATR-based TP/SL scheme would have made money historically
        # net of its win rate, given the current risk:reward ratio -- not
        # just "R:R looks fine on paper". Timeouts are excluded since they
        # are neither a realized win nor a realized loss.
        "expectancy_r": (
            (tp_count / resolved) * (cm.TP_ATR_MULT / cm.SL_ATR_MULT) - (sl_count / resolved)
            if resolved else None
        ),
    }

    return {
        "total": total,
        "correct": correct_count,
        "hit_rate": correct_count / total,
        "brier": brier,
        "confidence_buckets": bucket_stats,
        "signal_hit_rates": signal_stats,
        "tp_sl": tp_sl_stats,
        "horizon_bars": horizon_bars,
        "date_range": (df["open_time"].iloc[MIN_BARS_FOR_SIGNAL], df["open_time"].iloc[n - horizon_bars - 1]),
    }
