from __future__ import annotations

import math

from shared.strategies.S25.config import (
    get_default_config,
    get_param_grid,
    get_quick_param_grid,
)


def test_s25_default_config_is_stable():
    cfg = get_default_config()
    assert cfg.strategy_id == "S25"
    assert cfg.strategy_name == "S25_s20_lite_checkpoint_drift"


def test_s25_quick_grid_is_smaller_than_full():
    full_grid = get_param_grid()
    quick_grid = get_quick_param_grid()

    assert math.prod(len(values) for values in full_grid.values()) == 34992
    assert math.prod(len(values) for values in quick_grid.values()) == 1024
    assert set(quick_grid.keys()) == set(full_grid.keys())
