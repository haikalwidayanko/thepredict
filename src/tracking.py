"""Lightweight local prediction log so the model's track record is
measurable instead of just claimed. No scheduler/notifications: pending
predictions are simply re-checked the next time the app is opened.

Predictions are resolved by comparing the price after a fixed horizon.

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

DEFAULT_HORIZON_HOURS = 4


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


def get_crypto_history(limit: int = 50) -> list[dict]:
    """Most recent crypto predictions first, resolved and pending alike."""
    records = _load(CRYPTO_LOG)
    return sorted(records, key=lambda r: r["timestamp"], reverse=True)[:limit]
