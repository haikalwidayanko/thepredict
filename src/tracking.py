"""Lightweight local prediction log so the crypto model's track record is
measurable instead of just claimed. No scheduler/notifications: pending
predictions are simply re-checked the next time the app is opened.

Storage is a JSON file on local disk. On Streamlit Community Cloud this
resets whenever the app restarts/redeploys -- fine for a rolling v1 track
record, not a permanent database.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Callable

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "predictions_log.json"
DEFAULT_HORIZON_HOURS = 4


def _load() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(records: list[dict]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")


def log_prediction(symbol: str, direction: str, price: float, confidence: float,
                    horizon_hours: float = DEFAULT_HORIZON_HOURS) -> None:
    records = _load()
    records.append({
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "direction": direction,
        "price_at_prediction": price,
        "confidence": confidence,
        "timestamp": time.time(),
        "horizon_hours": horizon_hours,
        "resolved": False,
        "correct": None,
        "price_at_resolution": None,
    })
    _save(records)


def evaluate_pending(get_current_price: Callable[[str], float]) -> None:
    """Resolve any predictions whose horizon has elapsed."""
    records = _load()
    now = time.time()
    changed = False
    for rec in records:
        if rec["resolved"]:
            continue
        elapsed_hours = (now - rec["timestamp"]) / 3600
        if elapsed_hours < rec["horizon_hours"]:
            continue
        try:
            current_price = get_current_price(rec["symbol"])
        except Exception:
            continue
        went_up = current_price > rec["price_at_prediction"]
        predicted_up = rec["direction"] == "NAIK"
        rec["correct"] = went_up == predicted_up
        rec["price_at_resolution"] = current_price
        rec["resolved"] = True
        changed = True
    if changed:
        _save(records)


def get_accuracy_stats() -> dict:
    records = [r for r in _load() if r["resolved"]]
    total = len(records)
    if total == 0:
        return {"total": 0, "correct": 0, "hit_rate": None}
    correct = sum(1 for r in records if r["correct"])
    return {"total": total, "correct": correct, "hit_rate": correct / total}
