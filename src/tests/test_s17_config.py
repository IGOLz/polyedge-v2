from __future__ import annotations

import math

from shared.strategies.S17.config import get_default_config, get_param_grid, get_quick_param_grid


def test_s17_default_config_is_stable():
    cfg = get_default_config()

    assert cfg.strategy_id == "S17"
    assert cfg.strategy_name == "S17_residual_fade"
    assert cfg.entry_window_start == 20
    assert cfg.entry_window_end == 180
    assert cfg.underlying_beta == 30.0
    assert cfg.residual_threshold == 0.04
    assert cfg.min_underlying_move_abs == 0.001
    assert cfg.reversal_confirmation_abs == 0.003
    assert cfg.extreme_price_low == 0.30
    assert cfg.extreme_price_high == 0.70


def test_s17_quick_grid_is_smaller_than_full_grid():
    full_grid = get_param_grid()
    quick_grid = get_quick_param_grid()

    full_combos = math.prod(len(values) for values in full_grid.values())
    quick_combos = math.prod(len(values) for values in quick_grid.values())

    assert full_combos == 1310720
    assert quick_combos == 5184
    assert quick_combos < full_combos
    assert set(quick_grid.keys()) == set(full_grid.keys())
