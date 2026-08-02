"""Thin client for Binance USDT-M Futures public REST API (no API key needed)."""
from __future__ import annotations

import pandas as pd
import requests

from .errors import MarketDataError

BASE_URL = "https://fapi.binance.com"
TIMEOUT = 10

DISPLAY_NAME = "Binance Futures"


class BinanceError(MarketDataError):
    pass


def _get(path: str, params: dict | None = None, timeout: int = TIMEOUT):
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise BinanceError(f"Gagal menghubungi Binance API ({path}): {exc}") from exc


def ping(timeout: int = 4) -> None:
    """Cheap reachability probe used by the provider selector."""
    _get("/fapi/v1/ping", timeout=timeout)


def get_futures_24h_tickers() -> pd.DataFrame:
    """All USDT-M perpetual symbols with 24h stats."""
    raw = _get("/fapi/v1/ticker/24hr")
    df = pd.DataFrame(raw)
    if df.empty:
        return df
    numeric_cols = [
        "priceChange", "priceChangePercent", "weightedAvgPrice", "lastPrice",
        "volume", "quoteVolume", "highPrice", "lowPrice",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["symbol"].str.endswith("USDT")].copy()
    df["dayRangePct"] = ((df["highPrice"] - df["lowPrice"]) / df["weightedAvgPrice"]) * 100
    return df


def get_top_volatile_symbols(n: int = 15, min_quote_volume: float = 20_000_000) -> pd.DataFrame:
    """Rank liquid USDT perpetuals by intraday range % to surface volatile coins."""
    df = get_futures_24h_tickers()
    if df.empty:
        return df
    liquid = df[df["quoteVolume"] >= min_quote_volume].copy()
    if liquid.empty:
        liquid = df.copy()
    liquid = liquid.sort_values("dayRangePct", ascending=False).head(n)
    return liquid[[
        "symbol", "lastPrice", "priceChangePercent", "dayRangePct", "quoteVolume",
    ]].reset_index(drop=True)


def get_klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame:
    raw = _get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    cols = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


def get_funding_rate(symbol: str) -> float:
    raw = _get("/fapi/v1/premiumIndex", {"symbol": symbol})
    return float(raw["lastFundingRate"])


def get_order_book(symbol: str, limit: int = 50) -> dict:
    raw = _get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})
    return {
        "bids": [(float(p), float(q)) for p, q in raw["bids"]],
        "asks": [(float(p), float(q)) for p, q in raw["asks"]],
    }
