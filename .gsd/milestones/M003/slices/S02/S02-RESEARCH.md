# S02 — Engine upgrades — dynamic fees + slippage — Research

**Date:** 2026-03-18

## Summary

This slice upgrades the backtest engine from flat 2% fees to Polymarket's dynamic taker fee model and adds configurable slippage penalty. The existing `engine.py` has clean separation between PnL calculation (`calculate_pnl_hold`, `calculate_pnl_exit`) and trade construction (`make_trade`), making this straightforward.

**Dynamic fees:** Polymarket CLOB uses `baseRate × min(price, 1-price)` — fees peak at ~3.15% for 50-cent tokens (near toss-up markets) and drop to ~0.63% for 10-cent tokens (confident outcomes). Current flat 2% fee understates costs for balanced markets and overstates for lopsided ones. We'll implement the formula with a configurable base rate (default 6.3% to match the 3.15% peak observation).

**Slippage:** Strategies detect a price and emit a signal, but execution happens later — the fill price differs from the detection price. In 5-minute markets, even a 1-second delay can move prices. We'll add a configurable `slippage` parameter (default 1 cent = $0.01) that penalizes the entry price in the unfavorable direction before computing PnL. This makes backtest results more honest.

The work is localized to two files: `engine.py` (add fee/slippage functions, update PnL calculations) and `backtest_strategies.py` (add CLI flags). No strategy code changes — strategies already emit `entry_price` and `signal_data["entry_second"]`; the engine just needs to adjust the price before calculating PnL.

## Recommendation

**Approach:** Add a `polymarket_dynamic_fee(price, base_rate)` function to `engine.py` returning `base_rate × min(price, 1-price)`. Update `calculate_pnl_hold()` and `calculate_pnl_exit()` to call this instead of using a flat `fee_rate`. Add a `slippage` parameter to `make_trade()` that adjusts `entry_price` before passing it to PnL functions (penalize Up bets by adding slippage, Down bets by subtracting). Add `--slippage` and `--fee-base-rate` CLI flags to `backtest_strategies.py`, pass them to `make_trade()`.

**Why this works:**
- The formula shape is mathematically verified: at price=0.50, `0.063 × 0.50 = 0.0315` (3.15%); at price=0.10, `0.063 × 0.10 = 0.0063` (0.63%).
- Slippage penalty simulates realistic execution — if a strategy detects price=0.45 for an Up bet, adding 1 cent slippage means the backtest assumes we bought at 0.46, reducing gross profit.
- Backward compatibility: existing code that doesn't pass slippage gets 0 by default (no change in behavior). The dynamic fee formula with base_rate=0.0317 (approx 2% at extreme prices) can approximate the old flat 2% if needed.
- Verification is trivial: run the same strategy twice with different slippage values and confirm PnL differs; check that fee at price=0.50 > fee at price=0.10.

## Implementation Landscape

### Key Files

- `src/analysis/backtest/engine.py` — Contains `calculate_pnl_hold()`, `calculate_pnl_exit()`, `make_trade()`, and `Trade` dataclass. All fee logic lives here. Currently uses `DEFAULT_FEE_RATE = 0.02` as a constant.
- `src/analysis/backtest_strategies.py` — CLI entry point. Calls `make_trade(market, second_entered, entry_price, direction)` from the strategy runner loop. Currently doesn't pass any fee or slippage parameters.

### Build Order

1. **Add dynamic fee function to `engine.py`** (prove first)
   - Define `polymarket_dynamic_fee(price: float, base_rate: float = 0.063) -> float` returning `base_rate × min(price, 1.0 - price)`
   - Test it in a Python REPL to confirm fee at 0.50 = 3.15% and fee at 0.10 = 0.63%
   - This is the foundation — everything else depends on having a working fee function

2. **Update PnL calculation functions**
   - Replace `fee_rate` parameter in `calculate_pnl_hold()` and `calculate_pnl_exit()` with `base_rate` (or keep both and add logic to call `polymarket_dynamic_fee` internally)
   - For hold: `fee = polymarket_dynamic_fee(entry_price, base_rate) × gross_profit`
   - For exit: `fee = polymarket_dynamic_fee(entry_price, base_rate) × max(0, gross_profit)` (only fee on profit)
   - **Important:** The fee is a function of the entry price (the price we paid), not the exit price. Polymarket charges fees on the token you buy, not the outcome.

3. **Add slippage adjustment to `make_trade()`**
   - Add `slippage: float = 0.0` parameter
   - Before calling PnL functions, adjust entry_price:
     - If direction == 'Up': `adjusted_entry = entry_price + slippage` (we paid more than detected)
     - If direction == 'Down': `adjusted_entry = entry_price - slippage` (we paid less than detected, which is worse for Down bets)
   - Clamp adjusted_entry to [0.01, 0.99] to stay within valid token price range
   - Pass `adjusted_entry` to PnL functions instead of raw `entry_price`

4. **Update CLI to pass slippage and base_rate**
   - Add `--slippage` flag to `backtest_strategies.py` (default 0.0 for backward compatibility)
   - Add `--fee-base-rate` flag (default 0.063 to match documented peak fee)
   - In `run_strategy()`, pass these to `make_trade()`

5. **Update `make_trade()` signature** to accept these new parameters and wire them through

### Verification Approach

**Dynamic fees:**
```bash
cd src && python3 << 'EOF'
from analysis.backtest.engine import polymarket_dynamic_fee
print(f"Fee at 0.50: {polymarket_dynamic_fee(0.50, 0.063):.4f} (expect 0.0315)")
print(f"Fee at 0.10: {polymarket_dynamic_fee(0.10, 0.063):.4f} (expect 0.0063)")
print(f"Fee at 0.90: {polymarket_dynamic_fee(0.90, 0.063):.4f} (expect 0.0063)")
EOF
```

**Slippage impact:**
Run the same strategy with different slippage values and confirm PnL changes:
```bash
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.0 > /tmp/no_slippage.txt
cd src && PYTHONPATH=. python3 -m analysis.backtest_strategies --strategy S1 --slippage 0.01 > /tmp/with_slippage.txt
diff /tmp/no_slippage.txt /tmp/with_slippage.txt
# Should see different total_pnl values
```

**Observable behavior:**
- Running with `--slippage 0.01` should produce lower PnL than `--slippage 0`
- Running with `--fee-base-rate 0.063` on a strategy that enters at price=0.50 should show higher fees than the old flat 2%
- Running with `--fee-base-rate 0.063` on a strategy that enters at price=0.10 should show lower fees than flat 2%

## Constraints

- **Backward compatibility:** Existing code (including old analysis modules in `analysis/backtest/module_*.py`) must continue to work. Default parameters must preserve old behavior where possible. The `fee_rate` parameter should remain supported as an override path.
- **No strategy changes:** Strategies already emit `entry_price` and `signal_data["entry_second"]`. They should not need to know about slippage or fee formulas — the engine handles all of that.
- **PnL formula correctness:** Polymarket fees are charged on the buy side (the token you purchase), not the outcome. For a hold-to-resolution trade:
  - Win: gross = (1.0 - entry_price), fee = dynamic_fee(entry_price) × gross, net = gross - fee
  - Loss: gross = -entry_price, no fee refund
- **Valid price range:** Adjusted entry prices (after slippage) must stay within [0.01, 0.99] to avoid impossible token prices.

## Common Pitfalls

- **Fee on exit price vs entry price:** The dynamic fee formula uses the entry price (the price we paid), not the exit price. If we buy a 0.50 token and sell at 0.60, the fee is still based on 0.50.
- **Slippage direction:** For Up bets, slippage increases cost (we pay more). For Down bets, slippage decreases what we receive (we pay less for the Down token, which is bad because Down tokens pay out when price goes down). The adjustment must be directionally correct:
  - Up bet with slippage: `entry_price + slippage` (higher cost = lower profit)
  - Down bet with slippage: `entry_price - slippage` (lower "price" means we're betting at worse odds)
  - Wait, this is confusing. Let me rethink: in Polymarket, "entry_price" is the price of the Up token. For an Up bet, slippage means we paid more than detected. For a Down bet, we're buying the Down token, whose price is (1 - up_price). If up_price increases due to slippage, the Down token becomes cheaper, which is *good* for Down bets. So:
    - **Up bet:** `adjusted_entry = entry_price + slippage` (paid more, worse)
    - **Down bet:** `adjusted_entry = entry_price + slippage` (Up token more expensive, Down token cheaper, which is actually good for us)
  - Actually, this is still wrong. Let me reconsider the semantics. The `entry_price` in our system is the price of the Up token (always). When we make a Down bet, we're buying the Down token at price = (1 - up_price). So:
    - If up_price = 0.45 and we want to bet Down, we buy the Down token at 0.55.
    - Slippage of 0.01 means by the time we execute, up_price = 0.46, so Down token costs 0.54 — better for us!
    - But that's slippage in our *favor* for Down bets, which is asymmetric and unrealistic.
  - The **right model:** Slippage should always be unfavorable. For Up bets, we pay more. For Down bets, the Down token got more expensive (meaning up_price went down, but the Down token's actual price in the orderbook increased due to demand). This means:
    - **Up bet with slippage:** buy Up token at `entry_price + slippage`
    - **Down bet with slippage:** buy Down token at `(1 - entry_price) + slippage`, which is equivalent to up_price = `entry_price - slippage`
  - So for implementation:
    ```python
    if direction == "Up":
        adjusted_entry = entry_price + slippage
    else:  # Down
        adjusted_entry = entry_price - slippage
    adjusted_entry = max(0.01, min(0.99, adjusted_entry))
    ```
- **Default slippage:** Default should be 0.0 for backward compatibility, but the playbook (S04) should recommend testing with realistic slippage (0.005 to 0.02) to see if strategies remain profitable.

## Open Risks

- **Base rate accuracy:** The 6.3% base rate is inferred from "fees up to ~3.15% at 50/50 prices" but Polymarket doesn't publish the exact constant. If the actual base rate is different (say, 5% or 7%), backtest PnL will be off. Mitigation: make it configurable via CLI flag so the user can adjust if they have better data.
- **Slippage model realism:** A flat 1-cent penalty is simplistic — real slippage depends on order book depth, volatility, and time between signal and execution. But order book data isn't available in this backtest setup. This model is conservative (assumes constant unfavorable slippage) which is safer than assuming zero.

## Sources

- Polymarket CLOB fee formula shape: `baseRate × min(price, 1-price)` — from M003 milestone context and D009 decision
- Observed peak fee ~3.15% at 50/50 prices — from M003 context, implies base rate ~6.3%
- Current engine implementation: `src/analysis/backtest/engine.py` lines 1-260
