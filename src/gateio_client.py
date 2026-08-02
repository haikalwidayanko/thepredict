"""Client for Gate.io USDT-settled perpetual futures public API (no API key needed).

Mirrors the interface of `binance_client` so the two are interchangeable behind
`market_data`. Used as a fallback because some networks/ISPs block Binance.

Gate.io quirks handled here:
- Contracts are named `BTC_USDT` (underscore), not `BTCUSDT`.
- Candlestick timestamps (`t`) are in seconds, not milliseconds.
- Order book sizes (`s`) are in contracts, not base units -- fine for the
  bid/ask ratio we compute, since both sides use the same unit.
- Funding rate ships inside the ticker, so no extra request is needed.
"""
from __future__ import annotations

import pandas as pd
import requests

from .errors import MarketDataError

BASE_URL = "https://api.gateio.ws/api/v4"
SETTLE = "usdt"
TIMEOUT = 10

DISPLAY_NAME = "Gate.io Futures"


class GateIOError(MarketDataError):
    pass


def _get(path: str, params: dict | None = None, timeout: int = TIMEOUT):
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise GateIOError(f"Gagal menghubungi Gate.io API ({path}): {exc}") from exc


def ping(timeout: int = 4) -> None:
    """Cheap reachability probe used by the provider selector."""
    _get(f"/futures/{SETTLE}/tickers", {"contract": "BTC_USDT"}, timeout=timeout)


def get_top_volatile_symbols(n: int = 15, min_quote_volume: float = 20_000_000) -> pd.DataFrame:
    """Rank liquid USDT perpetuals by 24h range % to surface volatile coins."""
    raw = _get(f"/futures/{SETTLE}/tickers")
    df = pd.DataFrame(raw)
    if df.empty:
        return df

    for col in ["last", "low_24h", "high_24h", "change_percentage", "volume_24h_quote"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    df = df.dropna(subset=["last", "low_24h", "high_24h", "volume_24h_quote"])
    df = df[df["last"] > 0]
    if df.empty:
        return pd.DataFrame()

    df = df.rename(columns={
        "contract": "symbol",
        "last": "lastPrice",
        "change_percentage": "priceChangePercent",
        "volume_24h_quote": "quoteVolume",
    })
    df["dayRangePct"] = (df["high_24h"] - df["low_24h"]) / df["lastPrice"] * 100

    liquid = df[df["quoteVolume"] >= min_quote_volume].copy()
    if liquid.empty:
        liquid = df.copy()

    liquid = liquid.sort_values("dayRangePct", ascending=False).head(n)
    return liquid[[
        "symbol", "lastPrice", "priceChangePercent", "dayRangePct", "quoteVolume",
    ]].reset_index(drop=True)


def get_klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame:
    raw = _get(f"/futures/{SETTLE}/candlesticks", {
        "contract": symbol,
        "interval": interval,
        "limit": limit,
    })
    if not raw:
        raise GateIOError(f"Tidak ada data candlestick untuk {symbol}")

    df = pd.DataFrame(raw)
    df = df.rename(columns={
        "t": "open_time", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    })
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(pd.to_numeric(df["open_time"]), unit="s")
    return df.sort_values("open_time").reset_index(drop=True)


def get_funding_rate(symbol: str) -> float:
    raw = _get(f"/futures/{SETTLE}/tickers", {"contract": symbol})
    if not raw:
        raise GateIOError(f"Tidak ada data ticker untuk {symbol}")
    return float(raw[0].get("funding_rate") or 0.0)


def get_order_book(symbol: str, limit: int = 50) -> dict:
    raw = _get(f"/futures/{SETTLE}/order_book", {"contract": symbol, "limit": limit})
    return {
        "bids": [(float(lvl["p"]), float(lvl["s"])) for lvl in raw.get("bids", [])],
        "asks": [(float(lvl["p"]), float(lvl["s"])) for lvl in raw.get("asks", [])],
    }
