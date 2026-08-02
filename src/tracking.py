"""Lightweight local prediction log so the models' track records are
measurable instead of just claimed. No scheduler/notifications: pending
predictions are simply re-checked the next time the app is opened.

Two independent logs:
- crypto: resolved by comparing price after a fixed horizon
- tennis: resolved by re-reading the Polymarket market once it settles

Storage is JSON on local disk. On Streamlit Community Cloud this resets
whenever the app restarts/redeploys -- fine for a rolling track record,
not a permanent database.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Callable

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CRYPTO_LOG = DATA_DIR / "predictions_log.json"
MATCH_LOG = DATA_DIR / "match_predictions_log.json"

DEFAULT_HORIZON_HOURS = 4

# A settled Polymarket outcome trades at ~1.0 (won) or ~0.0 (lost).
SETTLED_THRESHOLD = 0.95


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _hit_rate(records: list[dict]) -> dict:
    resolved = [r for r in records if r.get("resolved")]
    total = len(resolved)
    if total == 0:
        return {"total": 0, "correct": 0, "hit_rate": None, "brier": None}
    correct = sum(1 for r in resolved if r.get("correct"))
    briers = [
        (r["probability"] - (1.0 if r["correct"] else 0.0)) ** 2
        for r in resolved
        if isinstance(r.get("probability"), (int, float))
    ]
    return {
        "total": total,
        "correct": correct,
        "hit_rate": correct / total,
        "brier": sum(briers) / len(briers) if briers else None,
    }


# --------------------------------------------------------------------------
# Crypto
# --------------------------------------------------------------------------

def log_prediction(symbol: str, direction: str, price: float, confidence: float,
                   horizon_hours: float = DEFAULT_HORIZON_HOURS) -> None:
    records = _load(CRYPTO_LOG)
    records.append({
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "direction": direction,
        "price_at_prediction": price,
        "confidence": confidence,
        "probability": 0.5 + confidence / 2,  # confidence -> implied probability
        "timestamp": time.time(),
        "horizon_hours": horizon_hours,
        "resolved": False,
        "correct": None,
        "price_at_resolution": None,
    })
    _save(CRYPTO_LOG, records)


def evaluate_pending(get_current_price: Callable[[str], float]) -> None:
    """Resolve crypto predictions whose horizon has elapsed."""
    records = _load(CRYPTO_LOG)
    now = time.time()
    changed = False
    for rec in records:
        if rec["resolved"]:
            continue
        if (now - rec["timestamp"]) / 3600 < rec["horizon_hours"]:
            continue
        try:
            current_price = get_current_price(rec["symbol"])
        except Exception:
            continue
        went_up = current_price > rec["price_at_prediction"]
        rec["correct"] = went_up == (rec["direction"] == "NAIK")
        rec["price_at_resolution"] = current_price
        rec["resolved"] = True
        changed = True
    if changed:
        _save(CRYPTO_LOG, records)


def get_accuracy_stats() -> dict:
    return _hit_rate(_load(CRYPTO_LOG))


# --------------------------------------------------------------------------
# Tennis matches
# --------------------------------------------------------------------------

def log_match_prediction(event_title: str, slug: str, question: str,
                         predicted_outcome: str, probability: float,
                         start_date: str | None = None,
                         raw_outcome: str | None = None) -> None:
    """Log a projection.

    `predicted_outcome` is the human label shown in the UI (a player name);
    `raw_outcome` is what Polymarket calls it ("Yes"/"No"). Resolution compares
    the raw value, since that is what the settled market reports back.
    """
    records = _load(MATCH_LOG)
    records.append({
        "id": str(uuid.uuid4()),
        "event_title": event_title,
        "slug": slug,
        "question": question,
        "predicted_outcome": predicted_outcome,
        "raw_outcome": raw_outcome or predicted_outcome,
        "probability": probability,
        "start_date": start_date,
        "timestamp": time.time(),
        "resolved": False,
        "correct": None,
        "actual_outcome": None,
    })
    _save(MATCH_LOG, records)


def already_logged(slug: str, question: str) -> bool:
    """Avoid double-logging the same market."""
    return any(
        r["slug"] == slug and r["question"] == question and not r["resolved"]
        for r in _load(MATCH_LOG)
    )


def evaluate_pending_matches(fetch_market: Callable[[str], dict | None]) -> None:
    """Resolve tennis predictions whose Polymarket market has settled.

    `fetch_market(slug)` should return a dict with `outcomes`, `prices` and
    `closed`, or None if it cannot be fetched.
    """
    records = _load(MATCH_LOG)
    changed = False
    for rec in records:
        if rec["resolved"]:
            continue
        try:
            market = fetch_market(rec["slug"])
        except Exception:
            continue
        if not market:
            continue

        outcomes = market.get("outcomes") or []
        prices = market.get("prices") or []
        if len(outcomes) != len(prices) or not outcomes:
            continue

        winners = [o for o, p in zip(outcomes, prices) if p >= SETTLED_THRESHOLD]
        if len(winners) != 1:
            continue  # not settled yet (or ambiguous) -- leave pending

        # Compare against the raw Polymarket label; older records predate the
        # raw_outcome field and stored the raw value in predicted_outcome.
        predicted_raw = rec.get("raw_outcome") or rec["predicted_outcome"]
        rec["actual_outcome"] = winners[0]
        rec["correct"] = winners[0] == predicted_raw
        rec["resolved"] = True
        changed = True
    if changed:
        _save(MATCH_LOG, records)


def get_match_accuracy_stats() -> dict:
    return _hit_rate(_load(MATCH_LOG))


def get_match_history(limit: int = 50) -> list[dict]:
    """Most recent predictions first, resolved and pending alike."""
    records = _load(MATCH_LOG)
    return sorted(records, key=lambda r: r["timestamp"], reverse=True)[:limit]
