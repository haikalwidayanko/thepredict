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


REQUIRED_TICKER_COLS = ("symbol", "weightedAvgPrice", "highPrice", "lowPrice", "quoteVolume")


def get_futures_24h_tickers() -> pd.DataFrame:
    """All USDT-M perpetual symbols with 24h stats."""
    raw = _get("/fapi/v1/ticker/24hr")
    if not isinstance(raw, list):
        # An error payload ({"code": ..., "msg": ...}) rather than the ticker
        # array -- surface it as a readable error instead of a KeyError later.
        raise BinanceError(f"Respons ticker Binance tidak seperti yang diharapkan: {raw}")

    df = pd.DataFrame(raw)
    if df.empty:
        return df

    missing = [c for c in REQUIRED_TICKER_COLS if c not in df.columns]
    if missing:
        raise BinanceError(
            "Respons ticker Binance tidak punya kolom yang dibutuhkan: "
            f"{', '.join(missing)}. Kolom yang ada: {', '.join(df.columns)}"
        )

    numeric_cols = [
        "priceChange", "priceChangePercent", "weightedAvgPrice", "lastPrice",
        "volume", "quoteVolume", "highPrice", "lowPrice",
    ]
    for col in numeric_cols:
        # .get() so an absent optional column becomes NaN instead of KeyError.
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

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
    if not isinstance(raw, list):
        raise BinanceError(f"Respons klines Binance tidak seperti yang diharapkan: {raw}")

    cols = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


def get_funding_rate(symbol: str) -> float:
    raw = _get("/fapi/v1/premiumIndex", {"symbol": symbol})
    # Binance returns a list when the symbol param is dropped/invalid; take the
    # first entry so a shape surprise doesn't become a TypeError downstream.
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict) or "lastFundingRate" not in raw:
        raise BinanceError(
            f"Respons funding rate Binance untuk {symbol} tidak berisi "
            f"'lastFundingRate': {raw}"
        )
    return float(raw["lastFundingRate"])


def get_order_book(symbol: str, limit: int = 50) -> dict:
    raw = _get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})
    if not isinstance(raw, dict) or "bids" not in raw or "asks" not in raw:
        raise BinanceError(
            f"Respons order book Binance untuk {symbol} tidak berisi bids/asks: {raw}"
        )
    return {
        "bids": [(float(p), float(q)) for p, q in raw.get("bids", [])],
        "asks": [(float(p), float(q)) for p, q in raw.get("asks", [])],
    }
