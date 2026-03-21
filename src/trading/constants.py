"""All strategy parameters — single source of truth.

Imported by strategies.py (logic) and main.py (startup logging).
Every parameter used in M3, M4, and bet sizing lives here.
"""

# ── M3 Strategy Configuration (Spike Reversion) ─────────────────────────

M3_CONFIG = {
    # Core
    'enabled': True,
    'hold_to_resolution': True,

    # Spike Detection
    'spike_detection_window_seconds': 15,
    'spike_threshold_up': 0.80,
    'spike_threshold_down': 0.20,

    # Reversion Detection
    'reversion_reversal_pct': 0.10,
    'min_reversion_ticks': 10,

    # Entry
    'entry_price_threshold': 0.35,

    # Market Filters
    'only_5min_markets': True,
    'allowed_assets': ['btc', 'eth', 'sol', 'xrp'],
    'min_seconds_remaining': 30,

    # Risk Management
    'stop_loss_enabled': False,

    # Logging
    'log_all_signals': True,
    'log_rejection_reasons': True,
}


# ── M4 Strategy Configuration (Volatility) ──────────────────────────────

M4_CONFIG = {
    # Core
    'enabled': True,
    'eval_second': 30,
    'eval_window': 2,

    # Volatility
    'volatility_window_seconds': 10,
    'volatility_threshold': 0.05,
    'volatility_direction': 'high',

    # Spread Filter
    'min_spread': 0.05,
    'max_spread': 0.50,

    # Market Filters
    'only_5min_markets': True,
    'allowed_assets': ['btc', 'eth', 'sol', 'xrp'],
    'min_seconds_remaining': 60,

    # Risk Management (stop-loss disabled — not in original backtest, was inverting exits)
    'stop_loss_enabled': False,
    'stop_loss_price': 0.30,

    # Logging
    'log_all_signals': True,
    'log_rejection_reasons': True,
}


# ── Shared Bet Sizing ───────────────────────────────────────────────────

STRATEGY_BET_SIZING = {
    # Current live bankroll sizing, based on the validated edge/risk profile
    # of each strategy. At a $170 bankroll this maps to:
    # S13 ~$10.20, S9 ~$7.65, S14 ~$6.80, S5 ~$5.95, S10 ~$4.25.
    'DEFAULT': {'bankroll_pct': 0.03},
    'M3': {'bankroll_pct': 0.04},
    'M4': {'bankroll_pct': 0.03},
    'S5': {'bankroll_pct': 0.035},
    'S9': {'bankroll_pct': 0.045},
    'S10': {'bankroll_pct': 0.025},
    'S13': {'bankroll_pct': 0.06},
    'S14': {'bankroll_pct': 0.04},
}


BET_SIZING = {
    'starting_bankroll': 170.0,
    'starting_bet_amount': 5.1,
    'bet_percentage': 0.03,
    'min_bet': 2.0,
    'max_bet': 100.0,
    'max_single_trade_pct': 0.12,
    'scale_with_growth': True,
    'track_m3_separately': True,
    'track_m4_separately': True,
}


# ── Execution Configuration ─────────────────────────────────────────────

EXECUTION_CONFIG = {
    # Stage 1: GTC limit at ideal price
    'stage_1_offset': 0.00,
    'stage_1_timeout': 2.0,

    # Stage 2: GTC limit at ideal + offset
    'stage_2_offset': 0.01,
    'stage_2_timeout': 2.0,

    # Stage 3: FOK at ideal + offset (wider tolerance for low-liquidity)
    'stage_3_offset': 0.05,

    # FOK retry: keep this short so stale signals do not chase illiquid books
    'fok_retry_max_seconds': 3.0,
    'fok_retry_interval': 0.5,
    'fok_max_attempts': 4,

    # Hard cap on total execution time across all stages
    'max_total_execution_seconds': 8.0,
}
