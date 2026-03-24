# ColdMath Vs Weather Bot: 24-Hour Findings

## Window

- Bot window start UTC: `2026-03-23T19:45:14+00:00`
- Bot window end UTC: `2026-03-24T19:45:14+00:00`
- Start source: `tmp_trading_weather_lxc_2000_clean.log:2`

## Bot Evidence

- `trading-weather` was up continuously through the 24-hour window.
- Heartbeat rows in window: `1429`
- Restart lines after initial start: `0`
- Downtime gaps over threshold: `0`
- Every observed cycle ended with `stand_down=no_qualifying_candidate`.
- Every observed cycle had `candidates=0`.
- `weather_merge_positions` rows opened in window: `0`
- Entry log rows in `bot_logs`: `0`
- Merge/redeem/unwind rows in `weather_merge_positions`: `0`

## ColdMath Evidence

- ColdMath weather trades in same 24-hour window: `2473`
- Distinct conditions traded: `125`
- Distinct events traded: `70`
- Earliest trade UTC: `2026-03-23T20:24:35+00:00`
- Latest trade UTC: `2026-03-24T19:44:55+00:00`
- Every ColdMath trade in the report matched a prior bot heartbeat with `candidates=0`.

## Operational Issues

- `bot_logs` recorded `12` `weather_merge_error` rows during the window.
- `4` of those errors were explicit `401 Unauthorized/Invalid api key`.
- The remaining error rows were request exceptions.
- These errors did not create downtime in the minute summary log, but they do mean the weather bot had intermittent broken API access during the comparison window.

## Strategy Mismatch

The deployed bot is not trying to reproduce all of ColdMath's weather behavior. Its config only allows a narrow paired-entry playbook:

- same-condition both-side accumulation
- `complete_set_cost <= 0.995`
- strict inventory imbalance cap
- required fill-context checks
- preference for favorable execution labels
- merge/redeem exit after matched inventory

ColdMath traded much more broadly in this window:

- `2419` buys and `54` sells
- `567` fills below `0.05`
- `313` fills above `0.95`
- average fill price `0.402475`

That mix shows more than simple under-par merge accumulation. It includes directional fills, tail bucket buys, and likely inventory management across multiple conditions and time horizons.

## Important Missed-Signal Finding

Within the same 24-hour window, ColdMath still executed the bot's core pattern on a subset of trades:

- `25` conditions had both `Yes` and `No` buys within `1` minute.
- `21` of those conditions had a reconstructed paired buy cost `<= 0.995`.

Examples:

- Wellington 2026-03-25 `15°C`: paired cost `0.969379`
- Tokyo 2026-03-24 `19°C`: paired cost `0.954293`
- Beijing 2026-03-24 `22°C`: paired cost `0.954141`
- Taipei 2026-03-24 `24°C`: paired cost `0.958479`
- Tel Aviv 2026-03-24 `22°C`: paired cost `0.965472`

So the conclusion is not just "ColdMath traded a different strategy." He also traded opportunities that look compatible with the bot's intended merge-arb logic, while the bot still reported `candidates=0`.

## Most Likely Reasons The Bot Did Not Trade

1. The bot's live candidate builder is stricter than the reconstructed ColdMath signal.
   It likely rejected opportunities because of live-only checks that are not visible in the public ledger, such as quote freshness, mergeable size, full fill-context availability, or inventory-balance requirements.

2. The bot had intermittent API failures, including explicit `401` auth failures.
   Even if not constant, this reduces scanner reliability during live windows that already depend on short-lived order book states.

3. The current logging is not sufficient to explain candidate rejection.
   The live container emitted minute summaries, but no detailed near-miss or rejection diagnostics for the exact window. That means we can prove `candidates=0`, but we cannot yet prove which live rule blocked each missed opportunity.

## Practical Conclusion

- ColdMath did trade heavily during the exact 24-hour bot window.
- The bot made zero live trades.
- The zero-trade result was not caused by downtime.
- The zero-trade result was caused by a combination of:
  - a narrower live strategy than ColdMath's actual behavior,
  - intermittent API/auth failures,
  - and missing live rejection diagnostics that prevent exact root-cause attribution on each missed setup.

## Next Technical Step

The next step is not more wallet forensics. It is live scanner instrumentation:

- persist every 5-second scan result
- save top-of-book yes/no prices and sizes
- save explicit rejection reasons per condition
- log whether a candidate failed because of freshness, size, fill-context, imbalance, or cost threshold

Without that, the comparison can prove the bot missed ColdMath activity, but it cannot prove which exact live rule rejected each missed paired opportunity.
