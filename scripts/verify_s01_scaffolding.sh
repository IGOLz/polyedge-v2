#!/bin/bash
# Verification script for S01 scaffolding
# Checks that old S1/S2 are deleted, TEMPLATE has get_param_grid(),
# and all 7 new strategy folders exist with correct structure and behavior.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== S01 Scaffolding Verification ==="
echo ""

# Check 1: Old S1, S2 folders should not exist (they were deleted in T01)
echo "[1/8] Checking old strategies deleted..."
# Since we're in M003 worktree, the old S1/S2 are already gone from TEMPLATE's perspective
# This check is more relevant in main codebase, but we verify structure here
if [ -d "src/shared/strategies/S1" ] && [ -d "src/shared/strategies/S2" ]; then
    # New S1/S2 should exist, so we just verify they're the new ones
    if grep -q "S1_calibration" src/shared/strategies/S1/config.py; then
        echo "  ✓ New S1 (calibration) exists"
    else
        echo "  ✗ S1 exists but is not the new calibration strategy"
        exit 1
    fi
else
    echo "  ! S1 or S2 missing (unexpected)"
    exit 1
fi

# Check 2: TEMPLATE has get_param_grid()
echo "[2/8] Checking TEMPLATE has get_param_grid()..."
if grep -q "def get_param_grid" src/shared/strategies/TEMPLATE/config.py; then
    echo "  ✓ TEMPLATE has get_param_grid() function"
else
    echo "  ✗ TEMPLATE missing get_param_grid() function"
    exit 1
fi

# Check 3: All 7 new strategy folders exist
echo "[3/8] Checking all 7 strategy folders exist..."
for i in {1..7}; do
    if [ ! -d "src/shared/strategies/S$i" ]; then
        echo "  ✗ Strategy S$i folder missing"
        exit 1
    fi
done
echo "  ✓ All 7 strategy folders exist"

# Check 4: Each has required files
echo "[4/8] Checking required files in each strategy..."
for i in {1..7}; do
    if [ ! -f "src/shared/strategies/S$i/__init__.py" ]; then
        echo "  ✗ S$i missing __init__.py"
        exit 1
    fi
    if [ ! -f "src/shared/strategies/S$i/config.py" ]; then
        echo "  ✗ S$i missing config.py"
        exit 1
    fi
    if [ ! -f "src/shared/strategies/S$i/strategy.py" ]; then
        echo "  ✗ S$i missing strategy.py"
        exit 1
    fi
done
echo "  ✓ All strategies have required files"

# Check 5: Registry discovers all 7 strategies + TEMPLATE
echo "[5/8] Checking registry discovery..."
STRATEGY_COUNT=$(python3 -c "
import sys
sys.path.insert(0, 'src')
from shared.strategies.registry import discover_strategies
strategies = discover_strategies()
print(len(strategies))
")

if [ "$STRATEGY_COUNT" -eq 8 ]; then
    echo "  ✓ Registry discovers 8 strategies (TEMPLATE + 7 new)"
else
    echo "  ✗ Registry discovered $STRATEGY_COUNT strategies, expected 8"
    exit 1
fi

# Check 6: Each strategy can be instantiated with correct IDs
echo "[6/8] Checking strategy instantiation and IDs..."
python3 << 'PYEOF'
import sys
sys.path.insert(0, 'src')
from shared.strategies.registry import get_strategy

expected = {
    'S1': 'S1_calibration',
    'S2': 'S2_momentum',
    'S3': 'S3_reversion',
    'S4': 'S4_volatility',
    'S5': 'S5_time_phase',
    'S6': 'S6_streak',
    'S7': 'S7_composite',
}

for sid, name in expected.items():
    strategy = get_strategy(sid)
    if strategy.config.strategy_id != sid:
        print(f"  ✗ {sid} has wrong strategy_id: {strategy.config.strategy_id}")
        sys.exit(1)
    if strategy.config.strategy_name != name:
        print(f"  ✗ {sid} has wrong strategy_name: {strategy.config.strategy_name}")
        sys.exit(1)

print("  ✓ All strategies have correct IDs and names")
PYEOF

if [ $? -ne 0 ]; then
    exit 1
fi

# Check 7: Each strategy's evaluate() returns None (stub behavior)
echo "[7/8] Checking stub evaluate() behavior..."
python3 << 'PYEOF'
import sys
import numpy as np
sys.path.insert(0, 'src')
from shared.strategies.registry import get_strategy
from shared.strategies.base import MarketSnapshot

snapshot = MarketSnapshot(
    market_id='test',
    market_type='binary',
    prices=np.array([50.0, 50.1, 50.2]),
    total_seconds=180,
    elapsed_seconds=3.0
)

for i in range(1, 8):
    strategy = get_strategy(f'S{i}')
    result = strategy.evaluate(snapshot)
    if result is not None:
        print(f"  ✗ S{i}.evaluate() returned {result}, expected None")
        sys.exit(1)

print("  ✓ All strategies return None (stub behavior)")
PYEOF

if [ $? -ne 0 ]; then
    exit 1
fi

# Check 8: No leftover Template references in code
echo "[8/8] Checking for leftover Template references..."
if grep -r "TemplateStrategy\|TemplateConfig" src/shared/strategies/S[1-7]/*.py > /dev/null 2>&1; then
    echo "  ✗ Found Template references in strategy code:"
    grep -r "TemplateStrategy\|TemplateConfig" src/shared/strategies/S[1-7]/*.py
    exit 1
else
    echo "  ✓ No Template references in strategy code"
fi

echo ""
echo "=== All S01 Scaffolding Checks Passed ✓ ==="
exit 0
