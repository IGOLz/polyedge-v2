"""Binance 1-second market-data helpers for live collection and backfills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from shared.config import BINANCE_CONFIG

QUOTE_SUFFIXES = (
    "USDT",
    "FDUSD",
    "USDC",
    "BUSD",
    "TUSD",
    "USD",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "TRY",
)


@dataclass(frozen=True)
class CryptoPriceBar:
    symbol: str
    asset: str
    quote_asset: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float
    source: str

    def as_record(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset": self.asset,
            "quote_asset": self.quote_asset,
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "trade_count": self.trade_count,
            "taker_buy_base_volume": self.taker_buy_base_volume,
            "taker_buy_quote_volume": self.taker_buy_quote_volume,
            "source": self.source,
        }


def split_symbol(symbol: str) -> tuple[str, str]:
    for suffix in QUOTE_SUFFIXES:
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[: -len(suffix)], suffix
    return symbol, ""


def current_bar_open_time(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0)


def build_combined_kline_stream_url(symbols: list[str]) -> str:
    streams = "/".join(f"{symbol.lower()}@kline_1s" for symbol in symbols)
    return f"{BINANCE_CONFIG['ws_base_url'].rstrip('/')}/stream?streams={streams}"


def parse_ws_kline_message(
    message: dict[str, Any],
    *,
    tracked_symbols: set[str] | None = None,
    source: str = "binance_live_ws",
) -> CryptoPriceBar | None:
    payload = message.get("data", message)
    if not isinstance(payload, dict):
        return None

    if payload.get("e") != "kline":
        return None

    kline = payload.get("k")
    if not isinstance(kline, dict):
        return None

    if not bool(kline.get("x")):
        return None

    symbol = str(kline.get("s") or payload.get("s") or "").upper()
    if not symbol:
        return None
    if tracked_symbols is not None and symbol not in tracked_symbols:
        return None

    return _build_bar_from_kline(symbol, kline, source=source)


def parse_rest_kline_row(
    symbol: str,
    row: list[Any],
    *,
    source: str = "binance_live_backfill",
) -> CryptoPriceBar:
    return CryptoPriceBar(
        symbol=symbol.upper(),
        asset=split_symbol(symbol.upper())[0],
        quote_asset=split_symbol(symbol.upper())[1],
        time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        quote_volume=float(row[7]),
        trade_count=int(row[8]),
        taker_buy_base_volume=float(row[9]),
        taker_buy_quote_volume=float(row[10]),
        source=source,
    )


async def fetch_rest_klines(
    client: httpx.AsyncClient,
    *,
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    source: str = "binance_live_backfill",
) -> list[CryptoPriceBar]:
    params = {
        "symbol": symbol.upper(),
        "interval": "1s",
        "startTime": int(start_time.timestamp() * 1000),
        # Binance filters by bar open time; +999ms keeps the final second inclusive.
        "endTime": int(end_time.timestamp() * 1000) + 999,
        "limit": 1000,
    }
    response = await client.get(
        f"{BINANCE_CONFIG['rest_base_url'].rstrip('/')}/api/v3/klines",
        params=params,
        timeout=15.0,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        return []
    return [parse_rest_kline_row(symbol.upper(), row, source=source) for row in rows]


def synthesize_bar(
    symbol: str,
    *,
    time: datetime,
    close: float,
    source: str = "binance_live_synth",
) -> CryptoPriceBar:
    asset, quote_asset = split_symbol(symbol.upper())
    return CryptoPriceBar(
        symbol=symbol.upper(),
        asset=asset,
        quote_asset=quote_asset,
        time=time,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
        quote_volume=0.0,
        trade_count=0,
        taker_buy_base_volume=0.0,
        taker_buy_quote_volume=0.0,
        source=source,
    )


def fill_missing_bars(
    symbol: str,
    bars: list[CryptoPriceBar],
    *,
    start_time: datetime,
    end_time: datetime,
    source: str = "binance_live_synth",
    seed_close: float | None = None,
) -> list[CryptoPriceBar]:
    if end_time < start_time:
        return []

    actual_by_time: dict[datetime, CryptoPriceBar] = {}
    previous_close = seed_close
    for bar in sorted(bars, key=lambda item: item.time):
        actual_by_time[bar.time] = bar
        if bar.time < start_time:
            previous_close = bar.close

    filled: list[CryptoPriceBar] = []
    current = start_time
    while current <= end_time:
        actual = actual_by_time.get(current)
        if actual is not None:
            filled.append(actual)
            previous_close = actual.close
        elif previous_close is not None:
            filled.append(
                synthesize_bar(symbol.upper(), time=current, close=previous_close, source=source)
            )
        current += timedelta(seconds=1)

    return filled


def _build_bar_from_kline(
    symbol: str,
    kline: dict[str, Any],
    *,
    source: str,
) -> CryptoPriceBar:
    asset, quote_asset = split_symbol(symbol.upper())
    return CryptoPriceBar(
        symbol=symbol.upper(),
        asset=asset,
        quote_asset=quote_asset,
        time=datetime.fromtimestamp(int(kline["t"]) / 1000, tz=timezone.utc),
        open=float(kline["o"]),
        high=float(kline["h"]),
        low=float(kline["l"]),
        close=float(kline["c"]),
        volume=float(kline["v"]),
        quote_volume=float(kline["q"]),
        trade_count=int(kline["n"]),
        taker_buy_base_volume=float(kline["V"]),
        taker_buy_quote_volume=float(kline["Q"]),
        source=source,
    )
