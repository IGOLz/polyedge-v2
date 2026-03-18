"""Import Binance 1-second kline files into PostgreSQL.

Expected filenames:
    BTCUSDT-1s-2026-03-17.csv
    ETHUSDT-1s-2026-03-17.zip

Usage:
    cd src
    PYTHONPATH=. python -m scripts.import_binance_1s --input-dir ..\\data\\binance_1s
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import asyncpg

from shared.config import DB_CONFIG

FILENAME_RE = re.compile(
    r"^(?P<symbol>[A-Z0-9]+)-1s-(?P<trading_day>\d{4}-\d{2}-\d{2})\.(?P<ext>csv|zip)$"
)

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

BAR_COLUMNS = [
    "symbol",
    "asset",
    "quote_asset",
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "source",
]

IMPORT_COLUMNS = [
    "file_name",
    "symbol",
    "asset",
    "quote_asset",
    "trading_day",
    "source_path",
    "rows_loaded",
    "zero_trade_rows",
    "imported_at",
]


@dataclass(frozen=True)
class SourceFile:
    path: Path
    file_name: str
    symbol: str
    asset: str
    quote_asset: str
    trading_day: date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts.import_binance_1s",
        description="Import Binance 1-second kline CSV/ZIP files into PostgreSQL.",
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Folder containing Binance 1-second files.",
    )
    parser.add_argument(
        "--source",
        default="binance",
        help="Source label stored in the database (default: binance).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Rows per COPY batch into the staging table (default: 10000).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-import files even if they are already recorded in the import log.",
    )
    parser.add_argument(
        "--skip-zero-trade-seconds",
        action="store_true",
        help="Skip rows where trade_count = 0. Default keeps the full 1-second grid.",
    )
    return parser.parse_args()


def split_symbol(symbol: str) -> tuple[str, str]:
    for suffix in QUOTE_SUFFIXES:
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            return symbol[: -len(suffix)], suffix
    return symbol, ""


def discover_files(input_dir: Path) -> list[SourceFile]:
    sources: list[SourceFile] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        match = FILENAME_RE.match(path.name)
        if match is None:
            continue
        symbol = match.group("symbol")
        asset, quote_asset = split_symbol(symbol)
        trading_day = date.fromisoformat(match.group("trading_day"))
        sources.append(
            SourceFile(
                path=path,
                file_name=path.name,
                symbol=symbol,
                asset=asset,
                quote_asset=quote_asset,
                trading_day=trading_day,
            )
        )
    return sources


def open_csv_rows(path: Path) -> Iterable[list[str]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise RuntimeError(f"{path.name}: expected exactly one CSV inside ZIP.")
            with zf.open(csv_names[0], "r") as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                yield from csv.reader(text)
        return

    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.reader(handle)


def batched(records: Iterable[tuple], batch_size: int) -> Iterable[list[tuple]]:
    batch: list[tuple] = []
    for record in records:
        batch.append(record)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_records(
    source_file: SourceFile,
    source_name: str,
    skip_zero_trade_seconds: bool,
) -> tuple[Iterable[tuple], dict[str, int]]:
    counters = {
        "rows_seen": 0,
        "rows_loaded": 0,
        "zero_trade_rows": 0,
    }

    def _iter() -> Iterable[tuple]:
        for row in open_csv_rows(source_file.path):
            if len(row) < 12:
                raise RuntimeError(
                    f"{source_file.file_name}: expected 12 columns, got {len(row)}."
                )

            counters["rows_seen"] += 1

            open_time_us = int(row[0])
            trade_count = int(row[8])
            if trade_count == 0:
                counters["zero_trade_rows"] += 1
                if skip_zero_trade_seconds:
                    continue

            open_time = datetime.fromtimestamp(open_time_us / 1_000_000, tz=timezone.utc)

            counters["rows_loaded"] += 1
            yield (
                source_file.symbol,
                source_file.asset,
                source_file.quote_asset,
                open_time,
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
                float(row[7]),
                trade_count,
                float(row[9]),
                float(row[10]),
                source_name,
            )

    return _iter(), counters


async def create_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_price_1s (
            symbol              TEXT            NOT NULL,
            asset               TEXT            NOT NULL,
            quote_asset         TEXT            NOT NULL DEFAULT '',
            time                TIMESTAMPTZ     NOT NULL,
            open                DOUBLE PRECISION NOT NULL,
            high                DOUBLE PRECISION NOT NULL,
            low                 DOUBLE PRECISION NOT NULL,
            close               DOUBLE PRECISION NOT NULL,
            volume              DOUBLE PRECISION NOT NULL,
            quote_volume        DOUBLE PRECISION NOT NULL,
            trade_count         INTEGER         NOT NULL,
            taker_buy_base_volume   DOUBLE PRECISION NOT NULL,
            taker_buy_quote_volume  DOUBLE PRECISION NOT NULL,
            source              TEXT            NOT NULL DEFAULT 'binance',
            PRIMARY KEY (symbol, time)
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_price_1s_imports (
            file_name        TEXT            PRIMARY KEY,
            symbol           TEXT            NOT NULL,
            asset            TEXT            NOT NULL,
            quote_asset      TEXT            NOT NULL DEFAULT '',
            trading_day      DATE            NOT NULL,
            source_path      TEXT            NOT NULL,
            rows_loaded      INTEGER         NOT NULL,
            zero_trade_rows  INTEGER         NOT NULL,
            imported_at      TIMESTAMPTZ     NOT NULL
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_crypto_price_1s_asset_time
        ON crypto_price_1s (asset, time);
        """
    )

    try:
        await conn.execute(
            """
            SELECT create_hypertable('crypto_price_1s', 'time', if_not_exists => TRUE);
            """
        )
        await conn.execute(
            """
            ALTER TABLE crypto_price_1s SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'symbol'
            );
            """
        )
        await conn.execute(
            """
            SELECT add_compression_policy('crypto_price_1s', INTERVAL '7 days', if_not_exists => TRUE);
            """
        )
    except Exception:
        pass


async def already_imported(conn: asyncpg.Connection, file_name: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM crypto_price_1s_imports WHERE file_name = $1;",
        file_name,
    )
    return row is not None


async def import_file(
    conn: asyncpg.Connection,
    source_file: SourceFile,
    source_name: str,
    batch_size: int,
    force: bool,
    skip_zero_trade_seconds: bool,
) -> tuple[str, int]:
    if not force and await already_imported(conn, source_file.file_name):
        print(f"[skip] {source_file.file_name} already recorded in import log")
        return ("skipped", 0)

    print(f"[import] {source_file.file_name}")

    await conn.execute("DROP TABLE IF EXISTS crypto_price_1s_stage;")
    await conn.execute(
        """
        CREATE TEMP TABLE crypto_price_1s_stage (
            symbol              TEXT,
            asset               TEXT,
            quote_asset         TEXT,
            time                TIMESTAMPTZ,
            open                DOUBLE PRECISION,
            high                DOUBLE PRECISION,
            low                 DOUBLE PRECISION,
            close               DOUBLE PRECISION,
            volume              DOUBLE PRECISION,
            quote_volume        DOUBLE PRECISION,
            trade_count         INTEGER,
            taker_buy_base_volume   DOUBLE PRECISION,
            taker_buy_quote_volume  DOUBLE PRECISION,
            source              TEXT
        ) ON COMMIT DROP;
        """
    )

    records, counters = build_records(
        source_file=source_file,
        source_name=source_name,
        skip_zero_trade_seconds=skip_zero_trade_seconds,
    )

    for batch in batched(records, batch_size):
        await conn.copy_records_to_table(
            "crypto_price_1s_stage",
            records=batch,
            columns=BAR_COLUMNS,
        )

    await conn.execute(
        """
        INSERT INTO crypto_price_1s (
            symbol,
            asset,
            quote_asset,
            time,
            open,
            high,
            low,
            close,
            volume,
            quote_volume,
            trade_count,
            taker_buy_base_volume,
            taker_buy_quote_volume,
            source
        )
        SELECT
            symbol,
            asset,
            quote_asset,
            time,
            open,
            high,
            low,
            close,
            volume,
            quote_volume,
            trade_count,
            taker_buy_base_volume,
            taker_buy_quote_volume,
            source
        FROM crypto_price_1s_stage
        ON CONFLICT (symbol, time) DO UPDATE SET
            asset              = EXCLUDED.asset,
            quote_asset        = EXCLUDED.quote_asset,
            open               = EXCLUDED.open,
            high               = EXCLUDED.high,
            low                = EXCLUDED.low,
            close              = EXCLUDED.close,
            volume             = EXCLUDED.volume,
            quote_volume       = EXCLUDED.quote_volume,
            trade_count        = EXCLUDED.trade_count,
            taker_buy_base_volume  = EXCLUDED.taker_buy_base_volume,
            taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume,
            source             = EXCLUDED.source;
        """
    )

    await conn.execute(
        """
        INSERT INTO crypto_price_1s_imports (
            file_name,
            symbol,
            asset,
            quote_asset,
            trading_day,
            source_path,
            rows_loaded,
            zero_trade_rows,
            imported_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (file_name) DO UPDATE SET
            symbol = EXCLUDED.symbol,
            asset = EXCLUDED.asset,
            quote_asset = EXCLUDED.quote_asset,
            trading_day = EXCLUDED.trading_day,
            source_path = EXCLUDED.source_path,
            rows_loaded = EXCLUDED.rows_loaded,
            zero_trade_rows = EXCLUDED.zero_trade_rows,
            imported_at = EXCLUDED.imported_at;
        """,
        source_file.file_name,
        source_file.symbol,
        source_file.asset,
        source_file.quote_asset,
        source_file.trading_day,
        str(source_file.path),
        counters["rows_loaded"],
        counters["zero_trade_rows"],
        datetime.now(timezone.utc),
    )

    print(
        "         "
        f"rows_loaded={counters['rows_loaded']} "
        f"zero_trade_rows={counters['zero_trade_rows']}"
    )
    return ("imported", counters["rows_loaded"])


async def main_async(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists():
        raise RuntimeError(f"Input directory does not exist: {input_dir}")

    source_files = discover_files(input_dir)
    if not source_files:
        raise RuntimeError(
            f"No matching files found in {input_dir}. Expected names like BTCUSDT-1s-2026-03-17.csv"
        )

    conn = await asyncpg.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )
    try:
        await create_tables(conn)

        imported_files = 0
        imported_rows = 0
        skipped_files = 0

        for source_file in source_files:
            async with conn.transaction():
                status, row_count = await import_file(
                    conn=conn,
                    source_file=source_file,
                    source_name=args.source,
                    batch_size=args.batch_size,
                    force=args.force,
                    skip_zero_trade_seconds=args.skip_zero_trade_seconds,
                )

            if status == "imported":
                imported_files += 1
                imported_rows += row_count
            else:
                skipped_files += 1

        print()
        print("Import complete")
        print(f"  Input directory: {input_dir}")
        print(f"  Files discovered: {len(source_files)}")
        print(f"  Files imported: {imported_files}")
        print(f"  Files skipped: {skipped_files}")
        print(f"  Rows imported this run: {imported_rows}")
    finally:
        await conn.close()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
