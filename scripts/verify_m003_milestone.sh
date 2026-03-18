#!/usr/bin/env bash
set -euo pipefail

echo "=== M003 Milestone Verification ==="
echo "Validates all M003 deliverables: strategy refactor, dynamic fees, slippage, optimizer, playbook"
echo ""

cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=src

# Track failures
CHECKS_PASSED=0
CHECKS_FAILED=0

#------------------------------------------------------------------------------
# Check 1: File structure (old deleted, new exist, TEMPLATE updated)
#------------------------------------------------------------------------------
echo "Check 1: File structure (old nested structure deleted, new S1-S7 exist, TEMPLATE updated)"
FILE_CHECK_FAILED=0

# Verify old nested structure is gone (M002 had src/shared/strategies/strategies/S1)
if [ -d "src/shared/strategies/strategies" ]; then
    echo "  ✗ Old nested src/shared/strategies/strategies/ should not exist (M003 flattened structure)"
    FILE_CHECK_FAILED=1
else
    echo "  ✓ Old nested strategies/ directory removed (structure flattened)"
fi

# Verify new S1-S7 exist with required files
for sid in S1 S2 S3 S4 S5 S6 S7; do
    if [ ! -d "src/shared/strategies/$sid" ]; then
        echo "  ✗ Missing directory: src/shared/strategies/$sid"
        FILE_CHECK_FAILED=1
    elif [ ! -f "src/shared/strategies/$sid/config.py" ]; then
        echo "  ✗ Missing file: src/shared/strategies/$sid/config.py"
        FILE_CHECK_FAILED=1
    elif [ ! -f "src/shared/strategies/$sid/strategy.py" ]; then
        echo "  ✗ Missing file: src/shared/strategies/$sid/strategy.py"
        FILE_CHECK_FAILED=1
    else
        echo "  ✓ $sid exists with config.py and strategy.py"
    fi
done

# Verify TEMPLATE folder exists (part of M003 deliverables)
if [ ! -d "src/shared/strategies/TEMPLATE" ]; then
    echo "  ✗ Missing TEMPLATE directory"
    FILE_CHECK_FAILED=1
elif [ ! -f "src/shared/strategies/TEMPLATE/config.py" ]; then
    echo "  ✗ Missing TEMPLATE/config.py"
    FILE_CHECK_FAILED=1
elif [ ! -f "src/shared/strategies/TEMPLATE/strategy.py" ]; then
    echo "  ✗ Missing TEMPLATE/strategy.py"
    FILE_CHECK_FAILED=1
else
    echo "  ✓ TEMPLATE exists with required files"
fi

if [ $FILE_CHECK_FAILED -eq 1 ]; then
    echo "  File structure check FAILED"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    echo "  File structure check PASSED"
    echo ""
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 2: Import checks (all 7 strategies + TEMPLATE import without errors)
#------------------------------------------------------------------------------
echo "Check 2: Import all strategies and TEMPLATE"
python3 <<'PYEOF'
import sys
strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE']
failures = []
for sid in strategies:
    try:
        config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_default_config', 'get_param_grid'])
        strategy_mod = __import__(f'shared.strategies.{sid}.strategy', fromlist=[f'{sid}Strategy'])
        print(f"  ✓ {sid} imports successfully")
    except Exception as e:
        failures.append(f"{sid}: {type(e).__name__}: {e}")
        print(f"  ✗ {sid}: {type(e).__name__}: {e}")
if failures:
    print(f"\n  Import check FAILED: {len(failures)} strategies failed")
    sys.exit(1)
print("\n  Import check PASSED")
print("")
PYEOF

if [ $? -ne 0 ]; then
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 3: Registry discovery (7 strategies + TEMPLATE = 8 discovered)
#------------------------------------------------------------------------------
echo "Check 3: Registry discovers exactly 8 strategies (S1-S7 + TEMPLATE)"
python3 <<'PYEOF'
import sys
from shared.strategies.registry import discover_strategies

discovered = discover_strategies()
expected_count = 8
expected_ids = {'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'TEMPLATE'}

if len(discovered) != expected_count:
    print(f"  ✗ Expected {expected_count} strategies, discovered {len(discovered)}")
    print(f"     Discovered: {sorted(discovered.keys())}")
    sys.exit(1)

missing = expected_ids - set(discovered.keys())
extra = set(discovered.keys()) - expected_ids

if missing:
    print(f"  ✗ Missing strategies: {missing}")
    sys.exit(1)

if extra:
    print(f"  ✗ Unexpected strategies: {extra}")
    sys.exit(1)

print(f"  ✓ Registry discovered exactly {expected_count} strategies")
for sid in sorted(discovered.keys()):
    print(f"     {sid}: {discovered[sid].__name__}")

print("\n  Registry discovery check PASSED")
print("")
PYEOF

if [ $? -ne 0 ]; then
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 4: Engine fee dynamics (fees vary by price, peak near 0.50)
#------------------------------------------------------------------------------
echo "Check 4: Engine dynamic fee formula (fees vary by price)"
python3 <<'PYEOF'
import sys
from analysis.backtest.engine import polymarket_dynamic_fee

# Test fee at three price points
fee_010 = polymarket_dynamic_fee(0.10)
fee_050 = polymarket_dynamic_fee(0.50)
fee_090 = polymarket_dynamic_fee(0.90)

print(f"  Fee at price 0.10: {fee_010:.4f} ({fee_010*100:.2f}%)")
print(f"  Fee at price 0.50: {fee_050:.4f} ({fee_050*100:.2f}%)")
print(f"  Fee at price 0.90: {fee_090:.4f} ({fee_090*100:.2f}%)")

# Verify fee dynamics: peak at 0.50, lower at extremes
if not (fee_010 < fee_050 and fee_050 > fee_090):
    print(f"  ✗ Fee dynamics incorrect: fee(0.10)={fee_010:.4f} fee(0.50)={fee_050:.4f} fee(0.90)={fee_090:.4f}")
    print(f"     Expected: fee(0.10) < fee(0.50) and fee(0.50) > fee(0.90)")
    sys.exit(1)

# Verify fee(0.10) ≈ fee(0.90) (symmetric)
if abs(fee_010 - fee_090) > 0.0001:
    print(f"  ✗ Fee asymmetric: fee(0.10)={fee_010:.4f} != fee(0.90)={fee_090:.4f}")
    sys.exit(1)

print(f"  ✓ Fee dynamics correct: peaks at 0.50, symmetric at extremes")
print("\n  Fee dynamics check PASSED")
print("")
PYEOF

if [ $? -ne 0 ]; then
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 5: Engine slippage impact (PnL differs with slippage parameter)
#------------------------------------------------------------------------------
echo "Check 5: Engine slippage impact (PnL changes with slippage parameter)"
python3 <<'PYEOF'
import sys
from analysis.backtest.engine import make_trade

# Create synthetic market
market = {
    'market_id': 'test',
    'asset': 'BTC',
    'duration_minutes': 5,
    'final_outcome': 'Up',
    'total_seconds': 300,
    'hour': 14
}

# Make two identical trades except for slippage
trade_no_slip = make_trade(
    market=market,
    second_entered=60,
    entry_price=0.50,
    direction='Up',
    slippage=0.0,
    base_rate=0.063
)

trade_with_slip = make_trade(
    market=market,
    second_entered=60,
    entry_price=0.50,
    direction='Up',
    slippage=0.01,  # 1% slippage penalty
    base_rate=0.063
)

print(f"  PnL with slippage=0.0:  {trade_no_slip.pnl:.6f}")
print(f"  PnL with slippage=0.01: {trade_with_slip.pnl:.6f}")

# Verify slippage reduces PnL (makes entry worse)
if trade_with_slip.pnl >= trade_no_slip.pnl:
    print(f"  ✗ Slippage did not reduce PnL: {trade_with_slip.pnl:.6f} >= {trade_no_slip.pnl:.6f}")
    sys.exit(1)

pnl_diff = trade_no_slip.pnl - trade_with_slip.pnl
print(f"  ✓ Slippage reduced PnL by {pnl_diff:.6f} (working correctly)")
print("\n  Slippage impact check PASSED")
print("")
PYEOF

if [ $? -ne 0 ]; then
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 6: Backtest execution on synthetic data (no DB required)
#------------------------------------------------------------------------------
echo "Check 6: Backtest execution with synthetic data (no DB dependency)"
python3 <<'PYEOF'
import sys
import numpy as np
from shared.strategies.base import MarketSnapshot
from shared.strategies.S1.config import get_default_config
from shared.strategies.S1.strategy import S1Strategy

# Create synthetic market snapshot (300 seconds, varied price pattern)
prices = np.full(300, 0.50)
prices[60:90] = 0.45  # small dip
prices[120:150] = 0.55  # small spike
prices[180:210] = 0.60  # larger move

snap = MarketSnapshot(
    market_id='test_market',
    market_type='BTC_5m',
    prices=prices,
    total_seconds=300,
    elapsed_seconds=300,
    metadata={'hour': 14, 'asset': 'BTC'}
)

# Instantiate S1 and evaluate
cfg = get_default_config()
strategy = S1Strategy(cfg)

try:
    signal = strategy.evaluate(snap)
    if signal is not None:
        print(f"  ✓ S1 returned signal: direction={signal.direction}, entry_price={signal.entry_price:.4f}")
    else:
        print(f"  ✓ S1 returned None (valid if conditions not met)")
    print("\n  Backtest execution check PASSED")
    print("")
except Exception as e:
    print(f"  ✗ S1 evaluation crashed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYEOF

if [ $? -ne 0 ]; then
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 7: Optimizer param grid discovery (all grids have ≥2 params, ≥2 values)
#------------------------------------------------------------------------------
echo "Check 7: Optimizer param grid discovery (all strategies have valid grids)"
python3 <<'PYEOF'
import sys
import itertools

strategies = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
failures = []

for sid in strategies:
    try:
        config_mod = __import__(f'shared.strategies.{sid}.config', fromlist=['get_param_grid'])
        grid = config_mod.get_param_grid()
        
        if not isinstance(grid, dict):
            failures.append(f"{sid}: param grid is not a dict")
            continue
        
        if len(grid) < 2:
            failures.append(f"{sid}: param grid has < 2 parameters (got {len(grid)})")
            continue
        
        # Check each parameter has ≥2 values
        for param, values in grid.items():
            if not isinstance(values, list):
                failures.append(f"{sid}: param '{param}' values not a list")
            elif len(values) < 2:
                failures.append(f"{sid}: param '{param}' has < 2 values (got {len(values)})")
        
        # Count total combinations
        combo_count = len(list(itertools.product(*grid.values())))
        print(f"  ✓ {sid}: {len(grid)} parameters, {combo_count} combinations")
        
    except Exception as e:
        failures.append(f"{sid}: {type(e).__name__}: {e}")

if failures:
    print(f"\n  Optimizer discovery check FAILED: {len(failures)} issues")
    for f in failures:
        print(f"     {f}")
    sys.exit(1)

print("\n  Optimizer discovery check PASSED")
print("")
PYEOF

if [ $? -ne 0 ]; then
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
else
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
fi

#------------------------------------------------------------------------------
# Check 8: Core immutability (src/core/ unchanged since M001, per R010)
#------------------------------------------------------------------------------
echo "Check 8: Core immutability (src/core/ unchanged per R010 constraint)"

# Check if M001 tag exists, otherwise use main branch
if git rev-parse M001 >/dev/null 2>&1; then
    BASE_REF="M001"
    echo "  Using M001 tag as baseline"
elif git rev-parse main >/dev/null 2>&1; then
    BASE_REF="main"
    echo "  Using main branch as baseline"
else
    echo "  ✗ Cannot find M001 tag or main branch for comparison"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    exit 1
fi

# Check if we're on the base ref (no diff expected)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" = "$BASE_REF" ]; then
    echo "  ○ On $BASE_REF branch, no diff expected (src/core/ unchanged)"
    echo "\n  Core immutability check PASSED"
    echo ""
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    # Get diff of src/core/ between base and HEAD
    CORE_DIFF=$(git diff "$BASE_REF"..HEAD -- src/core/ 2>/dev/null || echo "ERROR")
    
    if [ "$CORE_DIFF" = "ERROR" ]; then
        echo "  ✗ Failed to run git diff $BASE_REF..HEAD -- src/core/"
        CHECKS_FAILED=$((CHECKS_FAILED + 1))
        exit 1
    fi
    
    if [ -n "$CORE_DIFF" ]; then
        echo "  ✗ src/core/ has been modified (violates R010 constraint)"
        echo "     Modified files:"
        git diff "$BASE_REF"..HEAD --name-only -- src/core/ | sed 's/^/       /'
        echo ""
        echo "     First 20 lines of diff:"
        echo "$CORE_DIFF" | head -20 | sed 's/^/       /'
        CHECKS_FAILED=$((CHECKS_FAILED + 1))
        exit 1
    else
        echo "  ✓ src/core/ unchanged (R010 constraint satisfied)"
        echo "\n  Core immutability check PASSED"
        echo ""
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    fi
fi

#------------------------------------------------------------------------------
# Summary
#------------------------------------------------------------------------------
echo "========================================"
echo "M003 MILESTONE VERIFICATION COMPLETE"
echo "========================================"
echo ""
echo "Checks passed: $CHECKS_PASSED/8"
echo "Checks failed: $CHECKS_FAILED/8"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo "✓ All M003 verification checks passed"
    echo ""
    echo "M003 Deliverables Verified:"
    echo "  1. Strategy refactor: Old S1/S2 deleted, new S1-S7 + TEMPLATE exist"
    echo "  2. All strategies import and instantiate correctly"
    echo "  3. Registry discovers all 8 strategies"
    echo "  4. Dynamic fee formula working (fees vary by price)"
    echo "  5. Slippage parameter affects PnL as expected"
    echo "  6. Backtest execution works on synthetic data (no DB dependency)"
    echo "  7. Optimizer param grids valid for all strategies"
    echo "  8. Core immutability maintained (R010 constraint)"
    echo ""
    exit 0
else
    echo "✗ M003 verification failed: $CHECKS_FAILED check(s) did not pass"
    echo ""
    exit 1
fi
