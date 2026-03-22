"""Database schema for wallet-forensics."""

from __future__ import annotations

import psycopg2.extensions


DDL = """
CREATE TABLE IF NOT EXISTS wallet_targets (
    proxy_wallet TEXT PRIMARY KEY,
    profile_name TEXT,
    pseudonym TEXT,
    bio TEXT,
    display_username_public BOOLEAN,
    created_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_traded_markets INTEGER,
    source_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS wallet_trades_raw (
    record_hash TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    transaction_hash TEXT,
    timestamp BIGINT NOT NULL,
    condition_id TEXT,
    asset TEXT,
    side TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    size DOUBLE PRECISION,
    price DOUBLE PRECISION,
    event_slug TEXT,
    market_slug TEXT,
    title TEXT,
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_trades_raw_wallet_time
ON wallet_trades_raw (proxy_wallet, timestamp);

CREATE TABLE IF NOT EXISTS wallet_activity_raw (
    record_hash TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    transaction_hash TEXT,
    timestamp BIGINT NOT NULL,
    condition_id TEXT,
    event_type TEXT NOT NULL,
    asset TEXT,
    side TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    size DOUBLE PRECISION,
    usdc_size DOUBLE PRECISION,
    price DOUBLE PRECISION,
    event_slug TEXT,
    market_slug TEXT,
    title TEXT,
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_activity_raw_wallet_time
ON wallet_activity_raw (proxy_wallet, timestamp);

CREATE TABLE IF NOT EXISTS wallet_positions_raw (
    record_hash TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    condition_id TEXT,
    asset TEXT,
    outcome TEXT,
    size DOUBLE PRECISION,
    avg_price DOUBLE PRECISION,
    cur_price DOUBLE PRECISION,
    cash_pnl DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION,
    event_slug TEXT,
    market_slug TEXT,
    title TEXT,
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_positions_raw_wallet
ON wallet_positions_raw (proxy_wallet);

CREATE TABLE IF NOT EXISTS wallet_closed_positions_raw (
    record_hash TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    condition_id TEXT,
    asset TEXT,
    outcome TEXT,
    total_bought DOUBLE PRECISION,
    avg_price DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION,
    event_slug TEXT,
    market_slug TEXT,
    title TEXT,
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_closed_positions_raw_wallet
ON wallet_closed_positions_raw (proxy_wallet);

CREATE TABLE IF NOT EXISTS wallet_value_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_json JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS wallet_tx_receipts (
    transaction_hash TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    block_number BIGINT,
    block_timestamp BIGINT,
    classifications_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    touched_contracts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    usdc_in DOUBLE PRECISION NOT NULL DEFAULT 0,
    usdc_out DOUBLE PRECISION NOT NULL DEFAULT 0,
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_tx_receipts_wallet
ON wallet_tx_receipts (proxy_wallet);

CREATE TABLE IF NOT EXISTS wallet_market_context (
    market_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    event_id TEXT,
    event_slug TEXT,
    gamma_market_id TEXT,
    market_slug TEXT,
    question TEXT,
    title TEXT,
    category TEXT,
    end_date TIMESTAMPTZ,
    active BOOLEAN,
    closed BOOLEAN,
    neg_risk BOOLEAN,
    resolution_source_url TEXT,
    yes_token_id TEXT,
    no_token_id TEXT,
    yes_price DOUBLE PRECISION,
    no_price DOUBLE PRECISION,
    outcomes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome_prices_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    sibling_market_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload_json JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_market_context_wallet_event
ON wallet_market_context (proxy_wallet, event_slug);

CREATE TABLE IF NOT EXISTS wallet_ledger_events (
    ledger_event_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    transaction_hash TEXT,
    condition_id TEXT,
    event_slug TEXT,
    asset TEXT,
    outcome TEXT,
    side TEXT,
    event_type TEXT NOT NULL,
    size DOUBLE PRECISION,
    token_delta DOUBLE PRECISION,
    usdc_delta DOUBLE PRECISION,
    price DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION,
    source_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_events_wallet_time
ON wallet_ledger_events (proxy_wallet, occurred_at);

CREATE TABLE IF NOT EXISTS wallet_positions_rebuilt (
    snapshot_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    ledger_event_id TEXT NOT NULL,
    condition_id TEXT,
    asset TEXT,
    outcome TEXT,
    position_size DOUBLE PRECISION NOT NULL,
    average_cost DOUBLE PRECISION NOT NULL,
    cost_basis DOUBLE PRECISION NOT NULL,
    realized_pnl_cumulative DOUBLE PRECISION NOT NULL,
    payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wallet_positions_rebuilt_wallet_event
ON wallet_positions_rebuilt (proxy_wallet, ledger_event_id);

CREATE TABLE IF NOT EXISTS wallet_inferred_rules (
    rule_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    condition_id TEXT,
    asset TEXT,
    confidence DOUBLE PRECISION NOT NULL,
    summary TEXT NOT NULL,
    trade_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_inferred_rules_wallet_conf
ON wallet_inferred_rules (proxy_wallet, confidence DESC);

CREATE TABLE IF NOT EXISTS wallet_playbook_sequences (
    sequence_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    strategy_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    condition_id TEXT,
    event_slug TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,
    duration_minutes DOUBLE PRECISION NOT NULL,
    trade_count INTEGER NOT NULL,
    buy_count INTEGER NOT NULL,
    merge_count INTEGER NOT NULL,
    redeem_count INTEGER NOT NULL,
    distinct_conditions INTEGER NOT NULL,
    realized_pnl DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    summary TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_playbook_sequences_wallet_time
ON wallet_playbook_sequences (proxy_wallet, started_at);

CREATE TABLE IF NOT EXISTS wallet_strategy_blueprints (
    blueprint_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    priority_score DOUBLE PRECISION NOT NULL,
    support_count INTEGER NOT NULL,
    distinct_conditions INTEGER NOT NULL,
    distinct_events INTEGER NOT NULL,
    realized_pnl_total DOUBLE PRECISION NOT NULL,
    realized_pnl_avg DOUBLE PRECISION NOT NULL,
    win_rate DOUBLE PRECISION NOT NULL,
    summary TEXT NOT NULL,
    entry_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sizing_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exit_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wallet_strategy_blueprints_wallet_priority
ON wallet_strategy_blueprints (proxy_wallet, priority_score DESC);

CREATE TABLE IF NOT EXISTS wallet_shadow_replay_trades (
    shadow_trade_id TEXT PRIMARY KEY,
    proxy_wallet TEXT NOT NULL,
    rule_id TEXT,
    condition_id TEXT,
    asset TEXT,
    side TEXT,
    entry_at TIMESTAMPTZ NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_mark_price DOUBLE PRECISION,
    size DOUBLE PRECISION NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    pnl_slippage_free DOUBLE PRECISION NOT NULL,
    pnl_conservative DOUBLE PRECISION NOT NULL,
    payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wallet_shadow_replay_wallet_entry
ON wallet_shadow_replay_trades (proxy_wallet, entry_at);
"""


def ensure_schema(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(DDL)
    conn.commit()
