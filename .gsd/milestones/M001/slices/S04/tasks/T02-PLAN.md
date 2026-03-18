---
estimated_steps: 5
estimated_files: 1
---

# T02: Build parity test script proving identical signals across adapters

**Slice:** S04 — Port S2 + parity verification
**Milestone:** M001

## Description

Create `scripts/parity_test.py` — the definitive proof that shared strategies produce identical signals regardless of which adapter context builds the MarketSnapshot. This validates R007 and proves the seconds-vs-ticks bug is eliminated.

The key insight from research: **neither S1 nor S2's `evaluate()` uses `elapsed_seconds`** — they operate entirely on the `prices` numpy array. This means if both adapters produce a MarketSnapshot with the same `prices` array, signals are guaranteed identical. The parity test constructs synthetic data, builds matching MarketSnapshot objects, runs strategies through direct `evaluate()` calls, and asserts signal equality. No need to invoke the full adapter pipelines — the strategies are pure functions.

The script should follow the same numbered-check pattern as verify_s01.py, verify_s02.py, and verify_s03.py for consistency.

## Steps

1. **Read existing verify scripts** for the output pattern: `src/scripts/verify_s01.py` (first 30 lines) to confirm the check numbering and pass/fail format. Also read `src/shared/strategies/S1/strategy.py` to understand S1's signal_data keys (needed for signal equality assertions).

2. **Create `src/scripts/parity_test.py`** with these parity checks:

   **Setup:** Import shared strategy base classes and registry. No imports from `trading` or `analysis` — parity is proven at the strategy layer.

   **Check 1: Registry discovers both S1 and S2** — `discover_strategies()` returns dict with both keys.

   **Check 2: S1 parity — identical prices → identical signal** — Build a MarketSnapshot with S1-triggering spike+reversion data (reuse the calibration knowledge: spike peak at s=4-5, sharp drop 0.85→0.75, entry_price ≤ 0.35). Create TWO MarketSnapshot objects with the SAME prices array but different `elapsed_seconds` values (simulating backtest context with elapsed=60 and live context with elapsed=45). Call `S1Strategy().evaluate()` on both. Assert both return non-None signals with identical `direction`, `entry_price`, and `strategy_id`. This proves elapsed_seconds doesn't affect the signal.

   **Check 3: S2 parity — identical prices → identical signal** — Build a MarketSnapshot with S2-triggering volatility data. Need: price at eval_second=30 deviates from 0.50 by >= 0.08, spread within [0.05, 0.50], and `np.nanstd()` over the 10-second window [20:31] >= 0.05. Use oscillating prices (alternating 0.55/0.45) in that window with price[30]=0.60. Create two snapshots with same prices, different elapsed_seconds. Assert identical signals.

   **Check 4: S1 no-signal parity — flat data → both return None** — MarketSnapshot with flat 0.50 prices. Two snapshots, different elapsed_seconds. Both S1 evaluations return None.

   **Check 5: S2 no-signal parity — flat data → both return None** — Same flat data, S2 returns None on both.

   **Check 6: Multi-strategy consistency** — Run ALL discovered strategies (via registry) on the same MarketSnapshot. For each strategy, evaluate twice with different elapsed_seconds. Assert results match (both None or both identical Signal).

   **Check 7: Prices array identity proof** — Explicitly verify that the strategies don't mutate the prices array. Create a snapshot, copy prices, evaluate, assert `np.array_equal(original, snapshot.prices)` (using nan-safe comparison).

   **Check 8: Seconds-vs-ticks bug elimination proof** — Create a MarketSnapshot where `len(prices) != elapsed_seconds` (e.g., 60 price points but elapsed_seconds=45). Run both strategies. This simulates the exact scenario where the old bug would manifest (tick count ≠ seconds count). Assert signals are based on array indices (seconds), not elapsed_seconds.

3. **Script structure:** Use the same `check()` / `passed` / `failed` counting pattern as verify_s01.py. Print summary at end. Exit 0 if all pass, exit 1 if any fail. Include a header: `"=== S04 Parity Test: Identical data → identical signals ==="`.

4. **Add a summary block** at the end that explicitly states what was proven:
   ```
   print("\n--- PROVEN ---")
   print("1. S1 and S2 produce identical signals on identical price data regardless of elapsed_seconds")
   print("2. Both strategies return None on non-triggering data regardless of context")
   print("3. Strategies are pure functions on prices array — seconds-vs-ticks bug is eliminated")
   ```

5. **Run and verify** the full parity test plus regression checks for S01 and S02.

## Must-Haves

- [ ] `scripts/parity_test.py` covers S1 parity, S2 parity, no-signal parity, and multi-strategy consistency
- [ ] Script proves strategies operate on prices array indices (seconds), not elapsed_seconds
- [ ] Script uses no imports from `trading` or `analysis` — parity proven at the pure strategy layer
- [ ] Exit code 0 when all checks pass, 1 on any failure
- [ ] verify_s01.py and verify_s02.py still pass

## Verification

- `cd src && PYTHONPATH=. python3 scripts/parity_test.py` — exit 0, all checks pass
- `cd src && PYTHONPATH=. python3 scripts/verify_s01.py` — S01 still passes
- `cd src && PYTHONPATH=. python3 scripts/verify_s02.py` — S02 still passes

## Inputs

- `src/shared/strategies/S2/` — T01's S2 strategy (must exist and work)
- `src/shared/strategies/S1/` — existing S1 strategy
- `src/shared/strategies/base.py` — MarketSnapshot, Signal, BaseStrategy
- `src/shared/strategies/registry.py` — discover_strategies()
- `src/scripts/verify_s01.py` — pattern for check numbering format
- S1 synthetic data calibration (from KNOWLEDGE.md): spike peak at s=4-5, sharp drop 0.85→0.75 in 3-4 steps, reversion ≈ 0.12
- S2 synthetic data: oscillating 0.55/0.45 in window [20:31], price[30]=0.60, produces std dev ≈ 0.05+

## Observability Impact

- **New diagnostic surface:** `scripts/parity_test.py` itself is the observability artifact — it prints numbered PASS/FAIL checks and a "--- PROVEN ---" summary block. Exit code 0 means all parity invariants hold; exit code 1 with the failing check name identifies exactly which parity property broke.
- **How a future agent inspects this task:** Run `cd src && PYTHONPATH=. python3 scripts/parity_test.py`. The output shows per-check verdicts. If a check fails, the check name encodes the invariant that broke (e.g., "S1 parity: identical signal on identical prices").
- **Failure state visibility:** A failing check prints `[FAIL] <name>` and immediately exits 1. The last printed check name is the one that failed.

## Expected Output

- `src/scripts/parity_test.py` — parity test script with 8 checks covering signal identity, no-signal identity, multi-strategy consistency, array immutability, and seconds-vs-ticks elimination proof
