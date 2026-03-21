# Binance 1s Import Workflow

This note documents how raw Binance 1-second files in `data/binance_1s` move into PostgreSQL and what to run after the import so backtests can use the aligned crypto features.

## Purpose

The workflow has two stages:

1. Import raw Binance 1-second klines into `crypto_price_1s`
2. Materialize per-market aligned features into `market_crypto_features_1s`

After that, run backtests or optimization jobs against the enriched dataset.

## Input Files

The importer expects files named like:

- `BTCUSDT-1s-2026-03-17.csv`
- `ETHUSDT-1s-2026-03-17.zip`

The repo already stores these under `data/binance_1s`.

## Import Into PostgreSQL

Run from the repository `src` directory:

```powershell
cd C:\Users\igol\Documents\GitHub\polyedge-v2\src
$env:PYTHONPATH='.'

python -m scripts.import_binance_1s --input-dir ..\data\binance_1s
```

What this creates:

- `crypto_price_1s`: raw imported 1-second bars
- `crypto_price_1s_imports`: import log used to skip files already loaded

Notes:

- The importer accepts both `.csv` and `.zip`
- Re-running the same command skips files already present in `crypto_price_1s_imports`
- Use `--force` to re-import files already recorded
- Use `--skip-zero-trade-seconds` only if you explicitly want to drop zero-trade bars

Example:

```powershell
python -m scripts.import_binance_1s --input-dir ..\data\binance_1s --force
```

## Build Aligned Market Features

Once raw Binance bars are imported, materialize the aligned feature table:

```powershell
python -m scripts.materialize_market_crypto_features --quote-asset USDT
```

What this creates:

- `market_crypto_features_1s`: one row per market-second with market and underlying crypto features
- `vw_market_crypto_features_research`: research-friendly view over the feature table

Important:

- This step joins `market_outcomes`, `market_ticks`, and `crypto_price_1s`
- Only markets with matching crypto data coverage are materialized
- If you re-import overlapping raw dates, rerun with `--refresh`

Example refresh:

```powershell
python -m scripts.materialize_market_crypto_features --quote-asset USDT --refresh
```

Optional filters:

```powershell
python -m scripts.materialize_market_crypto_features --quote-asset USDT --assets BTC,ETH --durations 5,15
```

## What To Do After Import

After import and materialization, the normal next step is backtesting.

Run all shared strategies:

```powershell
python -m analysis.backtest_strategies --assets BTC,ETH,SOL,XRP --durations 5,15 --slippage 0.01 --output-dir ..\backtest_results
```

Run one strategy:

```powershell
python -m analysis.backtest_strategies --strategy S13 --assets BTC --durations 5 --slippage 0.01 --output-dir ..\backtest_results
```

Run parameter optimization:

```powershell
python -m analysis.optimize --strategy S13 --assets BTC --durations 5 --output-dir ..\optimization_results
```

## How The Backtest Loader Uses This

The backtest data loader always reads resolved `market_outcomes` and `market_ticks`.

If `market_crypto_features_1s` exists, it also loads aligned per-second crypto features and attaches them to each market snapshot used by the strategies.

This means:

- Tick-only strategies can still run without the feature table
- Feature-driven strategies rely on `market_crypto_features_1s`
- Markets missing required aligned feature data are skipped automatically by the framework

## Quick Verification Queries

Check imported raw crypto rows:

```sql
SELECT symbol, COUNT(*) AS rows, MIN(time) AS min_time, MAX(time) AS max_time
FROM crypto_price_1s
GROUP BY symbol
ORDER BY symbol;
```

Check aligned feature coverage:

```sql
SELECT market_type, COUNT(DISTINCT market_id) AS markets, COUNT(*) AS rows
FROM market_crypto_features_1s
GROUP BY market_type
ORDER BY market_type;
```

Check whether the research view exists:

```sql
SELECT to_regclass('public.vw_market_crypto_features_research');
```

## File References

- `src/scripts/import_binance_1s.py`
- `src/scripts/materialize_market_crypto_features.py`
- `src/analysis/backtest/data_loader.py`
- `src/analysis/backtest_strategies.py`
