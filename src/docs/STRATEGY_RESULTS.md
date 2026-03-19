# Strategy Results

Short notes on what we learned from each strategy. Keep entries compact and update only the current conclusion.

## 2026-03-19

### Rejected / Weak

- `S3`: edge too thin. It regressed on the broader rerun, had weak PF/Sharpe after fees and slippage, and looked too fragile for a live bot.
- `S5` broad version: better than `S3`, but mixing all assets and durations hid weak slices. `15m` added little, `BTC` was weak, `XRP` was less stable, and the broad version softened in the latest regime.

### Current Lead

- `S5` conservative, `5m`, `ETH+SOL` only
- Why it looks good: kept most of the PnL while improving PF, Sharpe, and drawdown; stayed profitable with `1s-3s` entry delay; stayed profitable at `0.03` slippage; all current folds remained positive.
- Why this version is better: cutting `15m`, `BTC`, and `XRP` removed weaker slices and left the strongest core of the signal.

### Parameters

- `entry_window_start=45`
- `entry_window_end=180`
- `allowed_hours=[18,19,20,21,22,23]`
- `price_range_low=0.45`
- `price_range_high=0.6`
- `approach_lookback=12`
- `cross_buffer=0.02`
- `confirmation_lookback=5`
- `confirmation_min_move=0.01`
- `min_cross_move=0.04`
- `stop_loss=0.35`
- `take_profit=0.7`

### Status

- Best paper-trade candidate so far.
