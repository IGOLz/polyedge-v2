#!/usr/bin/env bash
# S01 Scaffolding Verification Script
#
# Verifies that slice S01 deliverables are complete:
# - Old S1, S2 strategies deleted (replaced with new ones)
# - TEMPLATE updated with get_param_grid()
# - All 7 new strategy folders exist with correct structure
# - Registry discovers all 7 + TEMPLATE (8 total)
# - Each strategy can be instantiated with correct metadata
# - Each strategy's evaluate() returns None (stub behavior)

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "S01 Scaffolding Verification"
echo "=========================================="
echo

# Run all checks in a single Python script for simplicity
python3 << 'PYEOF'
import sys
sys.path.insert(0, 'src')

from shared.strategies.registry import discover_strategies, get_strategy
from shared.strategies.base import MarketSnapshot
import numpy as np
import os

# Color codes
GREEN = '\033[0;32m'
RED = '\033[0;31m'
NC = '\033[0m'

passed = 0
failed = 0

def pass_check(msg):
    global passed
    print(f'{GREEN}✓ PASS:{NC} {msg}')
    passed += 1

def fail_check(msg):
    global failed
    print(f'{RED}✗ FAIL:{NC} {msg}')
    failed += 1

# ── Check 1: Old strategies replaced with new ones ──────────────
print("Check 1: Old S1 and S2 strategies replaced with new structure")
print()

try:
    from shared.strategies.S1.config import get_default_config
    cfg = get_default_config()
    if cfg.strategy_name == 'S1_calibration':
        pass_check("New S1 (S1_calibration) exists with correct structure")
    else:
        fail_check(f"S1 has wrong name: {cfg.strategy_name}")
except Exception as e:
    fail_check(f"S1 structure check failed: {e}")

try:
    from shared.strategies.S2.config import get_default_config as get_s2_config
    cfg = get_s2_config()
    if cfg.strategy_name == 'S2_momentum':
        pass_check("New S2 (S2_momentum) exists with correct structure")
    else:
        fail_check(f"S2 has wrong name: {cfg.strategy_name}")
except Exception as e:
    fail_check(f"S2 structure check failed: {e}")

print()

# ── Check 2: TEMPLATE has get_param_grid() ───────────────────────
print("Check 2: TEMPLATE has get_param_grid() function")
print()

try:
    from shared.strategies.TEMPLATE.config import get_param_grid
    result = get_param_grid()
    if isinstance(result, dict):
        pass_check("TEMPLATE get_param_grid() exists and returns dict")
    else:
        fail_check(f"TEMPLATE get_param_grid() returns {type(result)}, expected dict")
except ImportError:
    fail_check("TEMPLATE missing get_param_grid() function")
except Exception as e:
    fail_check(f"TEMPLATE get_param_grid() error: {e}")

print()

# ── Check 3: All 7 strategy folders exist with required files ────
print("Check 3: All 7 strategy folders exist with required files")
print()

required_files = ['__init__.py', 'config.py', 'strategy.py']

for i in range(1, 8):
    strategy_dir = f'src/shared/strategies/S{i}'
    
    if not os.path.isdir(strategy_dir):
        fail_check(f"S{i} directory missing")
        continue
    
    missing = [f for f in required_files if not os.path.isfile(f'{strategy_dir}/{f}')]
    
    if not missing:
        pass_check(f"S{i} folder exists with all required files")
    else:
        fail_check(f"S{i} folder missing files: {', '.join(missing)}")

print()

# ── Check 4: Registry discovers all 7 + TEMPLATE ─────────────────
print("Check 4: Registry discovers all 7 strategies + TEMPLATE")
print()

strategies = discover_strategies()
found = sorted(strategies.keys())
expected = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE']

print(f"Found {len(found)} strategies: {found}")
print(f"Expected {len(expected)} strategies: {expected}")

missing = set(expected) - set(found)
extra = set(found) - set(expected)

if missing:
    print(f"MISSING: {sorted(missing)}")
    fail_check(f"Registry missing strategies: {', '.join(sorted(missing))}")
else:
    pass_check("Registry discovered all 8 strategies (7 + TEMPLATE)")

if extra:
    print(f"EXTRA: {sorted(extra)} (warning, not a failure)")

print()

# ── Check 5: Each strategy can be instantiated with correct metadata ──
print("Check 5: Each strategy can be instantiated with correct metadata")
print()

expected_names = {
    'S1': 'S1_calibration',
    'S2': 'S2_momentum',
    'S3': 'S3_reversion',
    'S4': 'S4_volatility',
    'S5': 'S5_time_phase',
    'S6': 'S6_streak',
    'S7': 'S7_composite',
}

for strategy_id, expected_name in expected_names.items():
    try:
        s = get_strategy(strategy_id)
        actual_id = s.config.strategy_id
        actual_name = s.config.strategy_name
        
        if actual_id != strategy_id:
            fail_check(f"{strategy_id} ID mismatch: expected '{strategy_id}', got '{actual_id}'")
            continue
        
        if actual_name != expected_name:
            fail_check(f"{strategy_id} Name mismatch: expected '{expected_name}', got '{actual_name}'")
            continue
        
        pass_check(f"{strategy_id} instantiated correctly: {expected_name}")
    except Exception as e:
        fail_check(f"{strategy_id} instantiation failed: {e}")

print()

# ── Check 6: Each strategy's evaluate() returns None (stub) ──────
print("Check 6: Each strategy's evaluate() returns None (stub behavior)")
print()

# Create a dummy snapshot
dummy_snapshot = MarketSnapshot(
    market_id='TEST_001',
    market_type='BLST',
    prices=np.array([50.0, 50.5, 51.0] * 50),  # 150 data points
    total_seconds=150,
    elapsed_seconds=150,
)

for strategy_id in expected_names.keys():
    try:
        s = get_strategy(strategy_id)
        result = s.evaluate(dummy_snapshot)
        
        if result is None:
            pass_check(f"{strategy_id} evaluate() returns None (stub)")
        else:
            fail_check(f"{strategy_id} evaluate() returned {result}, expected None")
    except Exception as e:
        fail_check(f"{strategy_id} evaluate() error: {e}")

print()

# ── Summary ──────────────────────────────────────────────────────
print("==========================================")
print("Summary")
print("==========================================")
print(f"{GREEN}Passed:{NC} {passed}")

if failed > 0:
    print(f"{RED}Failed:{NC} {failed}")
    print()
    print("S01 scaffolding verification FAILED")
    sys.exit(1)
else:
    print(f"{GREEN}Failed:{NC} 0")
    print()
    print("S01 scaffolding verification PASSED ✓")
    sys.exit(0)

PYEOF
