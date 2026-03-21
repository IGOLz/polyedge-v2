/**
 * SQL expression that recalculates PnL from trade parameters.
 *
 * Polymarket binary options:
 *  - Win:  shares resolve at $1.00 → PnL = shares × (1 - entry_price)
 *  - Loss: shares resolve at $0.00 → PnL = -bet_size_usd
 *  - Stop-loss: sold early      → PnL = (stop_loss_price - entry_price) × shares
 */
export const PNL_SQL = `
  CASE
    WHEN final_outcome = 'win_resolution' THEN
      COALESCE(shares, bet_size_usd / NULLIF(entry_price, 0)) * (1.0 - entry_price)
    WHEN final_outcome = 'loss' THEN
      -bet_size_usd
    WHEN final_outcome = 'stop_loss' THEN
      (COALESCE(stop_loss_price, 0) - entry_price)
        * COALESCE(shares, bet_size_usd / NULLIF(entry_price, 0))
    WHEN final_outcome = 'take_profit' THEN
      (COALESCE(take_profit_price, 0) - entry_price)
        * COALESCE(shares, bet_size_usd / NULLIF(entry_price, 0))
    ELSE NULL
  END`;
