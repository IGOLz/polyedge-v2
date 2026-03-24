"""Database schema for wallet tracker tables."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS wallet_tracker_activity (
    record_hash         TEXT PRIMARY KEY,
    profile_name        TEXT NOT NULL,
    proxy_wallet        TEXT NOT NULL,
    transaction_hash    TEXT,
    timestamp           BIGINT NOT NULL,
    event_type          TEXT,
    condition_id        TEXT,
    asset               TEXT,
    side                TEXT,
    outcome             TEXT,
    outcome_index       INTEGER,
    size                DOUBLE PRECISION,
    usdc_size           DOUBLE PRECISION,
    price               DOUBLE PRECISION,
    event_slug          TEXT,
    market_slug         TEXT,
    title               TEXT,
    payload_json        JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wallet_tracker_activity_wallet_time
ON wallet_tracker_activity (proxy_wallet, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_wallet_tracker_activity_profile
ON wallet_tracker_activity (profile_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS wallet_tracker_watermark (
    profile_name    TEXT PRIMARY KEY,
    proxy_wallet    TEXT NOT NULL,
    last_timestamp  BIGINT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
