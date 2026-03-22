from __future__ import annotations

import math

import pytest

from shared.strategies.S20.config import (
    get_default_config as get_s20_default_config,
    get_param_grid as get_s20_param_grid,
    get_quick_param_grid as get_s20_quick_param_grid,
)
from shared.strategies.S21.config import (
    get_default_config as get_s21_default_config,
    get_param_grid as get_s21_param_grid,
    get_quick_param_grid as get_s21_quick_param_grid,
)
from shared.strategies.S22.config import (
    get_default_config as get_s22_default_config,
    get_param_grid as get_s22_param_grid,
    get_quick_param_grid as get_s22_quick_param_grid,
)
from shared.strategies.S23.config import (
    get_default_config as get_s23_default_config,
    get_param_grid as get_s23_param_grid,
    get_quick_param_grid as get_s23_quick_param_grid,
)
from shared.strategies.S24.config import (
    get_default_config as get_s24_default_config,
    get_param_grid as get_s24_param_grid,
    get_quick_param_grid as get_s24_quick_param_grid,
)


@pytest.mark.parametrize(
    ("loader", "strategy_id", "strategy_name"),
    [
        (get_s20_default_config, "S20", "S20_checkpoint_curve_follow"),
        (get_s21_default_config, "S21", "S21_endgame_sweep_follow"),
        (get_s22_default_config, "S22", "S22_session_band_hold"),
        (get_s23_default_config, "S23", "S23_trigger_cross_snipe"),
        (get_s24_default_config, "S24", "S24_opening_drive_accumulate"),
    ],
)
def test_new_strategy_default_configs_are_stable(loader, strategy_id, strategy_name):
    cfg = loader()
    assert cfg.strategy_id == strategy_id
    assert cfg.strategy_name == strategy_name


@pytest.mark.parametrize(
    ("full_loader", "quick_loader", "full_combos"),
    [
        (get_s20_param_grid, get_s20_quick_param_grid, 34992),
        (get_s21_param_grid, get_s21_quick_param_grid, 59049),
        (get_s22_param_grid, get_s22_quick_param_grid, 177147),
        (get_s23_param_grid, get_s23_quick_param_grid, 78732),
        (get_s24_param_grid, get_s24_quick_param_grid, 34992),
    ],
)
def test_new_strategy_quick_grids_are_smaller_than_full(full_loader, quick_loader, full_combos):
    full_grid = full_loader()
    quick_grid = quick_loader()

    assert math.prod(len(values) for values in full_grid.values()) == full_combos
    assert math.prod(len(values) for values in quick_grid.values()) < full_combos
    assert set(quick_grid.keys()) == set(full_grid.keys())
