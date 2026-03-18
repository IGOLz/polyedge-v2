#!/usr/bin/env python3
"""Verify S01: Parameter Grid Foundation — all strategies have SL/TP in param grids."""

import sys
from itertools import product


def verify_strategy(strategy_id):
    """Import strategy config, check for SL/TP keys, compute grid size."""
    module_name = f"shared.strategies.{strategy_id}.config"
    try:
        mod = __import__(module_name, fromlist=["get_param_grid"])
        get_param_grid = mod.get_param_grid
    except ImportError as e:
        print(f"  [FAIL] {strategy_id} import failed: {e}")
        return False
    
    grid = get_param_grid()
    
    # Check for stop_loss key
    if "stop_loss" not in grid:
        print(f"  [FAIL] {strategy_id} missing 'stop_loss' key")
        return False
    print(f"  [PASS] {strategy_id} has stop_loss key")
    
    # Check for take_profit key
    if "take_profit" not in grid:
        print(f"  [FAIL] {strategy_id} missing 'take_profit' key")
        return False
    print(f"  [PASS] {strategy_id} has take_profit key")
    
    # Check non-empty
    if not grid["stop_loss"]:
        print(f"  [FAIL] {strategy_id} stop_loss is empty")
        return False
    print(f"  [PASS] {strategy_id} stop_loss has {len(grid['stop_loss'])} values")
    
    if not grid["take_profit"]:
        print(f"  [FAIL] {strategy_id} take_profit is empty")
        return False
    print(f"  [PASS] {strategy_id} take_profit has {len(grid['take_profit'])} values")
    
    # Compute grid size
    grid_size = 1
    for key, values in grid.items():
        grid_size *= len(values)
    
    print(f"  Grid size: {grid_size} combinations")
    if grid_size > 1000:
        print(f"  [WARN] Grid size exceeds 1000 — may be slow")
    
    return True


def main():
    print("=== S01 Verification: Parameter Grid Foundation ===\n")
    
    strategies = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    all_passed = True
    
    for sid in strategies:
        print(f"{sid} config:")
        if not verify_strategy(sid):
            all_passed = False
        print()
    
    # Check TEMPLATE
    print("TEMPLATE config:")
    if not verify_strategy("TEMPLATE"):
        all_passed = False
    print()
    
    if all_passed:
        print("✓ All checks passed. S01 complete.")
        sys.exit(0)
    else:
        print("✗ Some checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
