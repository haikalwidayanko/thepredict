"""Shared exception type so callers can catch failures from any data provider."""


class MarketDataError(RuntimeError):
    """Raised when a market data provider cannot be reached or returns bad data."""
