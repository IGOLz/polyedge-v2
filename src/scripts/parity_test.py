"""S04 parity test — prove identical data → identical signals across adapters.

Run from src/ directory:
    PYTHONPATH=. python3 scripts/parity_test.py

Proves R007: shared strategies are pure functions on the prices array.
No imports from trading or analysis — parity proven at the strategy layer.
"""
import sys

import numpy as np

# ── shared strategy imports only ────────────────────────────────────────
from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.registry import discover_strategies, get_strategy
from shared.strategies.S1.config import get_default_config as s1_default_config
from shared.strategies.S1.strategy import S1Strategy
from shared.strategies.S2.config import get_default_config as s2_default_config
from shared.strategies.S2.strategy import S2Strategy

# ── test harness ────────────────────────────────────────────────────────
_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    global _passed, _failed
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if condition:
        _passed += 1
    else:
        _failed += 1


def signals_equal(a: Signal | None, b: Signal | None) -> bool:
    """Compare two Signal objects for parity (direction, entry_price, strategy_name)."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return (
        a.direction == b.direction
        and a.entry_price == b.entry_price
        and a.strategy_name == b.strategy_name
    )


# ── helpers to build synthetic data ─────────────────────────────────────
def _make_s1_triggering_prices() -> np.ndarray:
    """Build a 60-element prices array that triggers S1 spike-reversion.

    Spike at s=3..7 (0.85), reversion at s=8..14 (0.75).
    Reversion amount: (0.85 - 0.75) / 0.85 ≈ 0.118 ≥ 0.10 threshold.
    Entry price: 1.0 - 0.75 = 0.25 ≤ 0.35 threshold.
    """
    prices = np.full(60, 0.50)
    prices[3:8] = 0.85   # up-spike in detection window (≥ 0.80)
    prices[8:15] = 0.75  # partial reversion
    return prices


def _make_s2_triggering_prices() -> np.ndarray:
    """Build a 60-element prices array that triggers S2 volatility.

    eval_second=30, vol window [20:31].
    Oscillating 0.55/0.45 in [20:30], price[30]=0.60.
    Deviation: |0.60 - 0.50| = 0.10 ≥ 0.08 threshold.
    Spread: |2*0.60 - 1| = 0.20, within [0.05, 0.50].
    Volatility: std of oscillating + 0.60 tail ≥ 0.05 threshold.
    """
    prices = np.full(60, 0.50)
    for i in range(20, 30):
        prices[i] = 0.55 if i % 2 == 0 else 0.45
    prices[30] = 0.60
    return prices


def _make_flat_prices() -> np.ndarray:
    """Flat 0.50 — no strategy should fire."""
    return np.full(60, 0.50)


def _snap(prices: np.ndarray, elapsed: float) -> MarketSnapshot:
    """Build a MarketSnapshot with given prices and elapsed_seconds."""
    return MarketSnapshot(
        market_id="parity_test",
        market_type="test",
        prices=prices,
        total_seconds=300,
        elapsed_seconds=elapsed,
    )


# ── main ────────────────────────────────────────────────────────────────
print("=== S04 Parity Test: Identical data → identical signals ===\n")

# ── Check 1: Registry discovers both S1 and S2 ─────────────────────────
print("1. Registry discovers both S1 and S2")
registry = discover_strategies()
check("S1 in registry", "S1" in registry)
check("S2 in registry", "S2" in registry)

# ── Check 2: S1 parity — identical prices → identical signal ───────────
print("\n2. S1 parity — identical prices, different elapsed_seconds")
s1 = S1Strategy(s1_default_config())
s1_prices = _make_s1_triggering_prices()

snap_a = _snap(s1_prices.copy(), elapsed=60.0)   # simulates backtest context
snap_b = _snap(s1_prices.copy(), elapsed=45.0)   # simulates live context

sig_a = s1.evaluate(snap_a)
sig_b = s1.evaluate(snap_b)

check("Both return non-None signal", sig_a is not None and sig_b is not None)
check("Signals are identical (direction, entry_price, strategy_name)",
      signals_equal(sig_a, sig_b))
if sig_a and sig_b:
    check("Direction matches: Down (contrarian to up-spike)",
          sig_a.direction == "Down" and sig_b.direction == "Down")
    check("Entry prices match exactly",
          sig_a.entry_price == sig_b.entry_price)
    check("Strategy name matches",
          sig_a.strategy_name == sig_b.strategy_name)

# ── Check 3: S2 parity — identical prices → identical signal ───────────
print("\n3. S2 parity — identical prices, different elapsed_seconds")
s2 = S2Strategy(s2_default_config())
s2_prices = _make_s2_triggering_prices()

snap_c = _snap(s2_prices.copy(), elapsed=60.0)   # backtest context
snap_d = _snap(s2_prices.copy(), elapsed=45.0)   # live context

sig_c = s2.evaluate(snap_c)
sig_d = s2.evaluate(snap_d)

check("Both return non-None signal", sig_c is not None and sig_d is not None)
check("Signals are identical (direction, entry_price, strategy_name)",
      signals_equal(sig_c, sig_d))
if sig_c and sig_d:
    check("Direction matches: Down (contrarian, price > 0.50)",
          sig_c.direction == "Down" and sig_d.direction == "Down")
    check("Entry prices match exactly",
          sig_c.entry_price == sig_d.entry_price)
    check("Strategy name matches",
          sig_c.strategy_name == sig_d.strategy_name)
    check("signal_data['volatility'] matches",
          sig_c.signal_data["volatility"] == sig_d.signal_data["volatility"])

# ── Check 4: S1 no-signal parity — flat data → both return None ────────
print("\n4. S1 no-signal parity — flat data, different elapsed_seconds")
flat = _make_flat_prices()
snap_e = _snap(flat.copy(), elapsed=60.0)
snap_f = _snap(flat.copy(), elapsed=30.0)

sig_e = s1.evaluate(snap_e)
sig_f = s1.evaluate(snap_f)

check("Both return None", sig_e is None and sig_f is None)

# ── Check 5: S2 no-signal parity — flat data → both return None ────────
print("\n5. S2 no-signal parity — flat data, different elapsed_seconds")
sig_g = s2.evaluate(_snap(flat.copy(), elapsed=60.0))
sig_h = s2.evaluate(_snap(flat.copy(), elapsed=30.0))

check("Both return None", sig_g is None and sig_h is None)

# ── Check 6: Multi-strategy consistency via registry ────────────────────
print("\n6. Multi-strategy consistency — all discovered strategies")
# Use S2-triggering data (will fire S2 but not S1 — that's fine, we test parity per strategy)
ms_prices = _make_s2_triggering_prices()
for strategy_id, strategy_cls in sorted(registry.items()):
    strat = get_strategy(strategy_id)
    snap_x = _snap(ms_prices.copy(), elapsed=60.0)
    snap_y = _snap(ms_prices.copy(), elapsed=25.0)
    sig_x = strat.evaluate(snap_x)
    sig_y = strat.evaluate(snap_y)
    both_none = sig_x is None and sig_y is None
    both_match = signals_equal(sig_x, sig_y)
    check(f"{strategy_id}: both None or identical signal", both_none or both_match)

# ── Check 7: Prices array immutability proof ────────────────────────────
print("\n7. Prices array immutability — strategies don't mutate input")
imm_prices = _make_s1_triggering_prices()
snap_imm = _snap(imm_prices, elapsed=50.0)
original_copy = imm_prices.copy()

s1.evaluate(snap_imm)
check("S1 does not mutate prices array",
      np.array_equal(original_copy, snap_imm.prices))

imm_prices2 = _make_s2_triggering_prices()
snap_imm2 = _snap(imm_prices2, elapsed=50.0)
original_copy2 = imm_prices2.copy()

s2.evaluate(snap_imm2)
check("S2 does not mutate prices array",
      np.array_equal(original_copy2, snap_imm2.prices))

# ── Check 8: Seconds-vs-ticks bug elimination proof ────────────────────
print("\n8. Seconds-vs-ticks bug elimination — len(prices) ≠ elapsed_seconds")
# 60 price points but elapsed_seconds=45 — simulates the exact scenario where
# the old bug would manifest (tick count ≠ seconds count).
ticks_prices_s1 = _make_s1_triggering_prices()  # 60 elements
snap_tick = _snap(ticks_prices_s1, elapsed=45.0)  # elapsed ≠ len(prices)
sig_tick_s1 = s1.evaluate(snap_tick)
check("S1 fires on 60 prices despite elapsed_seconds=45 (uses array indices)",
      sig_tick_s1 is not None)

ticks_prices_s2 = _make_s2_triggering_prices()  # 60 elements
snap_tick2 = _snap(ticks_prices_s2, elapsed=45.0)  # elapsed ≠ len(prices)
sig_tick_s2 = s2.evaluate(snap_tick2)
check("S2 fires on 60 prices despite elapsed_seconds=45 (uses array indices)",
      sig_tick_s2 is not None)

# Compare with normal elapsed_seconds to confirm identical signals
snap_normal_s1 = _snap(ticks_prices_s1, elapsed=60.0)
sig_normal_s1 = s1.evaluate(snap_normal_s1)
check("S1 signal identical whether elapsed=45 or elapsed=60",
      signals_equal(sig_tick_s1, sig_normal_s1))

snap_normal_s2 = _snap(ticks_prices_s2, elapsed=60.0)
sig_normal_s2 = s2.evaluate(snap_normal_s2)
check("S2 signal identical whether elapsed=45 or elapsed=60",
      signals_equal(sig_tick_s2, sig_normal_s2))

# ── Summary ─────────────────────────────────────────────────────────────
print(f"\n=== Results: {_passed} passed, {_failed} failed ===")

if _failed == 0:
    print("\n--- PROVEN ---")
    print("1. S1 and S2 produce identical signals on identical price data regardless of elapsed_seconds")
    print("2. Both strategies return None on non-triggering data regardless of context")
    print("3. Strategies are pure functions on prices array — seconds-vs-ticks bug is eliminated")
    print("\n=== All S04 parity checks passed ===")
else:
    print(f"\n!!! {_failed} check(s) FAILED — parity NOT proven !!!")

sys.exit(0 if _failed == 0 else 1)
