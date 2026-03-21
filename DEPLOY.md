# PolyEdge Deploy Notes

This project can run `core` and `trading` independently. The common setup here is:

- `core` writes live market data to the PostgreSQL database configured in `.env`
- `trading` reads that same database and can be restarted without stopping `core`

## 1. Prepare `.env`

Use the variable names from `.env.example`:

```bash
cp .env.example .env
nano .env
```

Important DB variables:

```bash
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_HOST=...
POSTGRES_PORT=5432
```

Important trading variables:

```bash
PRIVATE_KEY=...
POLYMARKET_API_KEY=...
POLYMARKET_API_SECRET=...
POLYMARKET_API_PASSPHRASE=...
PROXY_WALLET=...
EOA_ADDRESS=...
RELAYER_API_KEY=...
RELAYER_API_KEY_ADDRESS=...
```

## 2. Build and start `core`

```bash
docker compose build core
docker compose up -d core
docker compose logs -f core
```

## 3. Check `core` is writing to the DB

If already inside `psql`:

```sql
\dt

SELECT COUNT(*) AS ticks FROM market_ticks;

SELECT COUNT(*) AS outcomes FROM market_outcomes;

SELECT asset, MAX(time) AS last_bar
FROM crypto_price_1s
GROUP BY asset
ORDER BY asset;

SELECT market_id, time, up_price
FROM market_ticks
ORDER BY time DESC
LIMIT 10;
```

To confirm updates are still coming:

```sql
SELECT MAX(time) AS latest_tick FROM market_ticks;

SELECT asset, NOW() - MAX(time) AS delay
FROM crypto_price_1s
GROUP BY asset
ORDER BY asset;
```

## 4. Build and start `trading`

```bash
docker compose build trading --no-cache
docker compose up -d trading
docker compose logs -f trading
```

Healthy startup usually shows:

- trading database tables ready
- USDC balance loaded
- startup redemption preflight ok
- bot started
- heartbeats every few seconds

## 5. Check `trading` in the DB

If already inside `psql`:

```sql
SELECT COUNT(*) FROM bot_trades;

SELECT COUNT(*) FROM bot_logs;

SELECT id, strategy_name, direction, status, placed_at
FROM bot_trades
ORDER BY placed_at DESC
LIMIT 20;

SELECT logged_at, log_type, message
FROM bot_logs
ORDER BY logged_at DESC
LIMIT 30;
```

## 6. Safe update flows

### Update `trading` only

This does not stop `core`.

```bash
git pull
docker compose build trading --no-cache
docker compose up -d trading
docker compose logs -f trading
```

### Update `core` only

Use only when you intentionally want to restart the collector.

```bash
git pull
docker compose build core
docker compose up -d core
docker compose logs -f core
```

### Update both `core` and `trading`

```bash
git pull
docker compose build core trading --no-cache
docker compose up -d core trading
docker compose logs -f core
docker compose logs -f trading
```

## 7. Useful status commands

```bash
docker compose ps
docker compose logs --tail=100 core
docker compose logs --tail=100 trading
```

## 8. Common fixes

### DB owner mismatch on Timescale hypertables

If `core` fails with:

```text
must be owner of hypertable "market_ticks"
```

Fix table ownership in PostgreSQL:

```sql
ALTER TABLE public.market_ticks OWNER TO polymarket;
ALTER TABLE public.market_outcomes OWNER TO polymarket;
```

### Trading missing dependency after code update

Rebuild the image without cache:

```bash
docker compose build trading --no-cache
docker compose up -d trading
```
