# T02: Enhance Top 10 Console Summary with SL/TP Display

## Description

The optimization results already include stop_loss and take_profit values in the CSV output (delivered by S03's metrics dict augmentation), and the Best_Configs.txt file shows these values in the detailed per-rank breakdown. However, R028 requires that the **top 10 console summary** also display explicit SL/TP values for each ranked combination.

Currently, the console summary in `optimize.py` lines 176-184 prints:
- config_id
- total_bets
- win_rate_pct
- total_pnl
- sharpe_ratio
- ranking_score

This task adds `SL={stop_loss}, TP={take_profit}` to the console output format, making parameter values immediately visible without needing to open the CSV or Best_Configs.txt file.

## Steps

1. **Locate the current top 10 console summary code:**
   ```bash
   cd src
   rg "Top 10 Configurations" analysis/optimize.py -A 10
   ```
   Expected: Lines 176-184 show the print loop for top 10 results.

2. **Read the current output format:**
   - Open `src/analysis/optimize.py`
   - Find the top 10 print loop (around lines 176-184)
   - Current format should be something like:
     ```python
     print(f"  {i+1}. {row['config_id']}")
     print(f"     Bets={row['total_bets']}, WR={row['win_rate_pct']:.1f}%, "
           f"PnL={row['total_pnl']:.4f}, Sharpe={row['sharpe_ratio']:.2f}, "
           f"Score={row['ranking_score']:.4f}")
     ```

3. **Add SL/TP to the output string:**
   - Modify the print statement to include:
     ```python
     f"SL={row.get('stop_loss', 'N/A')}, TP={row.get('take_profit', 'N/A')}, "
     ```
   - Insert this after the `Score=...` field for readability
   - Use `.get()` with `'N/A'` default to handle cases where SL/TP might not be present (defensive coding, though S03 guarantees they're always in the metrics dict)

4. **Expected new format:**
   ```python
   print(f"  {i+1}. {row['config_id']}")
   print(f"     Bets={row['total_bets']}, WR={row['win_rate_pct']:.1f}%, "
         f"PnL={row['total_pnl']:.4f}, Sharpe={row['sharpe_ratio']:.2f}, "
         f"Score={row['ranking_score']:.4f}, SL={row.get('stop_loss', 'N/A')}, "
         f"TP={row.get('take_profit', 'N/A')}")
   ```

5. **Verify the console output includes SL/TP:**
   ```bash
   cd src && PYTHONPATH=. python3 -c "
   from analysis.optimize import optimize_strategy
   from analysis.backtest import data_loader
   
   markets = data_loader.load_all_data()[:100]
   optimize_strategy('S1', markets, './results/optimization')
   " | grep -E 'SL=.*TP='
   ```
   Expected output: Multiple lines showing `SL=0.XX, TP=0.YY` values for top 10 combinations.

6. **Verify the format is human-readable:**
   - Run the same command without grep to see full output
   - Check that SL/TP values align with the declared parameter grid:
     - S1 should show stop_loss in [0.35, 0.40, 0.45]
     - S1 should show take_profit in [0.65, 0.70, 0.75]

7. **Commit the enhancement:**
   ```bash
   git add src/analysis/optimize.py
   git commit -m "feat(M004-S04-T02): add stop_loss and take_profit to top 10 console summary

   R028 requires explicit SL/TP values visible in console output. The CSV
   and Best_Configs.txt already include these values (S03), but the top 10
   summary did not. This change adds SL=X.XX, TP=Y.YY to the console output
   for immediate visibility without needing to open files."
   ```

## Must-Haves

- Top 10 console summary includes `SL={stop_loss}, TP={take_profit}` for each ranked combination
- Use `.get()` with 'N/A' default for defensive coding
- Format is human-readable and aligned with existing metrics display
- Verification proves SL/TP values appear in console output

## Verification

Run the verification command from step 5 above. Success criteria:
- Console output includes lines matching pattern `SL=.*TP=`
- Values are numeric and match the declared parameter grid ranges
- Top 10 summary is still readable and well-formatted
- No exceptions or formatting errors

## Inputs

- Existing optimize.py with top 10 console summary code (lines 176-184)
- S03's metrics dict augmentation guarantees stop_loss and take_profit keys exist in results DataFrame
- Ranked results DataFrame with stop_loss and take_profit columns

## Expected Output

- Modified optimize.py with enhanced print statement including SL/TP display
- Console output showing top 10 combinations with explicit parameter values:
  ```
  Top 10 Configurations:
    1. S1_entry_window_start=30_...
       Bets=123, WR=52.3%, PnL=1.2345, Sharpe=0.87, Score=0.4567, SL=0.40, TP=0.70
    2. S1_entry_window_start=35_...
       Bets=118, WR=51.2%, PnL=1.1890, Sharpe=0.82, Score=0.4512, SL=0.35, TP=0.75
    ...
  ```
- User can immediately see which SL/TP values each top-ranked combination used without opening CSV

## Observability Impact

**Signals that change:**
- Console stdout from `optimize_strategy()` now includes stop_loss and take_profit values in the top 10 summary lines (previously these parameters were only visible in CSV or Best_Configs.txt)
- Pattern `SL=\d+\.\d+, TP=\d+\.\d+` becomes searchable in console logs and terminal history

**Inspection surfaces for future agents:**
```bash
# Verify console output includes SL/TP display
cd src && PYTHONPATH=. python3 -c "
from analysis.optimize import optimize_strategy
from analysis.backtest import data_loader
markets = data_loader.load_all_data()[:100]
optimize_strategy('S1', markets, './results/optimization')
" | grep -E 'SL=.*TP='

# Expected: ~10 lines matching pattern like 'Score=0.4567, SL=0.40, TP=0.70'
```

**Failure states that become visible:**
- Missing SL/TP values: If console output shows `SL=N/A, TP=N/A` instead of numeric values, it indicates the metrics dict augmentation from S03 didn't propagate to the results DataFrame
- Mismatched values: If console SL/TP values don't align with declared parameter grid ranges (e.g., stop_loss outside [0.35, 0.40, 0.45] for S1), it indicates parameter grid configuration error
- Format exceptions: If print statement raises KeyError or AttributeError, it indicates DataFrame schema mismatch
