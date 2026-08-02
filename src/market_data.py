"""Provider-agnostic facade for perpetual futures market data.

Tries providers in order and pins the first reachable one for the rest of the
process. This keeps the app working on networks where a given exchange is
blocked (e.g. some ISPs block Binance) without changing any calling code.

Symbols are whatever the active provider uses natively (`BTCUSDT` on Binance,
`BTC_USDT` on Gate.io) -- the UI only ever offers symbols the active provider
returned, so no cross-exchange translation is needed.
"""
from __future__ import annotations

import pandas as pd

from . import binance_client, gateio_client
from .errors import MarketDataError

PROVIDERS = [binance_client, gateio_client]

_active = None  # pinned provider module


def _resolve():
    """Return the first reachable provider, remembering the choice."""
    global _active
    if _active is not None:
        return _active

    failures = []
    for provider in PROVIDERS:
        try:
            provider.ping()
        except MarketDataError as exc:
            failures.append(f"{provider.DISPLAY_NAME}: {exc}")
            continue
        _active = provider
        return _active

    raise MarketDataError(
        "Tidak ada sumber data yang bisa dihubungi.\n\n" + "\n\n".join(failures)
    )


def active_provider_name() -> str:
    return _resolve().DISPLAY_NAME


def reset() -> None:
    """Forget the pinned provider so the next call re-probes."""
    global _active
    _active = None


def get_top_volatile_symbols(n: int = 15, min_quote_volume: float = 20_000_000) -> pd.DataFrame:
    return _resolve().get_top_volatile_symbols(n=n, min_quote_volume=min_quote_volume)


def get_klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame:
    return _resolve().get_klines(symbol, interval=interval, limit=limit)


def get_funding_rate(symbol: str) -> float:
    return _resolve().get_funding_rate(symbol)


def get_order_book(symbol: str, limit: int = 50) -> dict:
    return _resolve().get_order_book(symbol, limit=limit)
