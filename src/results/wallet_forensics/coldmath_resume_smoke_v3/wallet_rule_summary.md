# Rule Summary: ColdMath

## Overview
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Total inferred rules: `3490`
- High-confidence rules: `3490`
- Shadow trades linked to rules: `20542`

## Dominant Playbooks
- `dust_long_tail_bucket`: `1817` rules, `1817` high-confidence, `0.84` avg confidence, `-468.90` conservative replay
- `neg_risk_basket`: `769` rules, `769` high-confidence, `0.80` avg confidence, `-4665.70` conservative replay
- `inventory_rebalancing_merge`: `489` rules, `489` high-confidence, `0.92` avg confidence, `-20509.04` conservative replay
- `laddered_execution`: `372` rules, `372` high-confidence, `0.75` avg confidence, `0.00` conservative replay
- `late_redemption_farming`: `43` rules, `43` high-confidence, `0.78` avg confidence, `0.00` conservative replay

## Executable Blueprints
- `inventory_rebalancing_merge`: status `ready_for_backtest`, confidence `0.99`, priority `249.15`, support `1071`
- `neg_risk_basket`: status `needs_exit_research`, confidence `0.94`, priority `135.80`, support `421`
- `dust_long_tail_bucket`: status `needs_exit_research`, confidence `0.89`, priority `26.55`, support `10`
- `laddered_execution`: status `execution_overlay`, confidence `0.99`, priority `180.94`, support `830`
- `late_redemption_farming`: status `operational_only`, confidence `0.92`, priority `85.32`, support `43`

## Bot Candidates
- `dust_long_tail_bucket` score `5451.84`: 1817 rules, 1817 high-confidence, avg confidence 0.84, conservative replay -468.90
- `neg_risk_basket` score `2307.80`: 769 rules, 769 high-confidence, avg confidence 0.80, conservative replay -4665.70
- `inventory_rebalancing_merge` score `1467.92`: 489 rules, 489 high-confidence, avg confidence 0.92, conservative replay -20509.04
- `laddered_execution` score `1116.75`: 372 rules, 372 high-confidence, avg confidence 0.75, conservative replay 0.00
- `inventory_rebalancing_merge` score `251.13`: blueprint status ready_for_backtest, support 1071, priority 249.15

## Top Conditions
- `0xdfd780958dfcbfe6af4ee70a4a1028b2bb4bb2c0950f08e89d46bd54b93281f1` (highest-temperature-in-atlanta-on-march-14-2026) rules `243`, max confidence `0.92`, realized PnL `158.12`
- `0xbe57e65d2625915a12a0f2c1821f0e3d8660288dd368472cf57d4e6f84134abe` (highest-temperature-in-tokyo-on-march-22-2026) rules `125`, max confidence `0.92`, realized PnL `34.07`
- `0x3d2f1a03e2dc9879f92822b07c27bfaa5cde4872088e5fe46d7238bae519ad4a` (highest-temperature-in-wellington-on-february-28-2026) rules `92`, max confidence `0.92`, realized PnL `29.45`
- `0x40885feba2985e0929b067704d86a00e307deec7a51f95220874b88793de1d68` (highest-temperature-in-seattle-on-march-7-2026) rules `71`, max confidence `0.92`, realized PnL `10.49`
- `0x3e62a09853441b31da2539de74bfd25d99c65d62e78ae1ade7b21759c3697edd` (highest-temperature-in-london-on-february-26-2026) rules `62`, max confidence `0.92`, realized PnL `15.63`
- `0xa0f45dc7b67f2e054b06a76cc2afc1fe8e207a24314bf8f3bdd1dd3c5c9a39d5` (highest-temperature-in-seoul-on-march-4-2026) rules `57`, max confidence `0.92`, realized PnL `10.58`
- `0x05ea66701ed7111e7c0e1cad7a798f79567998bcd786fd668cf09fdf6fb260dd` (highest-temperature-in-seoul-on-march-3-2026) rules `55`, max confidence `0.92`, realized PnL `8.17`
- `0x373219d6c90b2caf1d38b4a7340102271f8287dac57fd9395497324e83bb8b18` (highest-temperature-in-milan-on-march-22-2026) rules `45`, max confidence `0.92`, realized PnL `3.77`
- `0x9965e31f646b21e6459ccb1edfcd133a8c1760ce6b03b20b8b6eca8b1b364b0e` (highest-temperature-in-wellington-on-march-6-2026) rules `40`, max confidence `0.92`, realized PnL `56.60`
- `0x34c0b81c08d5f2c61fe13be1efb0883a51ca3e625daa3a98d2251c8ba8d583cf` (highest-temperature-in-wellington-on-march-13-2026) rules `38`, max confidence `0.92`, realized PnL `4.56`
