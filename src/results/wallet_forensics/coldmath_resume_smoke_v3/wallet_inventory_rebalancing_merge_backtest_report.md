# Sequence Backtest: inventory_rebalancing_merge

## Overview
- Profile: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Configs tested: `24300`
- Selected sequences under best config: `93`
- Fill-context-aware mode: `True`
- Fill-context artifact: `/Users/igol/Documents/repo/polyedge-v2/src/results/wallet_forensics/coldmath_resume_smoke_v3/wallet_fill_context.csv`

## Best Config
- Complete set cost <= `0.995`
- Inventory imbalance <= `0.491617`
- Min matched size >= `0.0`
- Max merge delay minutes: `240.0`
- Require full buy-fill context: `True`
- Under-par buy-fill ratio >= `0.5`
- Max worse-than-nearby-buy ratio <= `0.25`
- Worse-fill override complete-set cost <= `0.98`
- Total realized PnL: `1683.30`
- ROI: `2.69%`
- Win rate: `100.00%`
- Profit factor: `999.00`
- Max drawdown: `0.00`

## PnL Attribution
- Estimated under-par entry edge: `1683.30`
- Realized via merge/redeem: `2025.83`
- Realized via sell-side inventory rebalancing: `0.00`
- Tail/dust residual realized PnL: `-83.08`
- Other residual realized PnL: `-259.45`
- Avg under-par buy-fill ratio: `0.802482`
- Avg worse-than-nearby-buy ratio: `0.161982`
- Sequences with full buy-fill context: `93`

## Top Configs
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.491617` | matched>=`0.0` | delay<=`240.0` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.491617` | matched>=`0.0` | delay<=`nan` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.491617` | matched>=`1.0` | delay<=`240.0` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.491617` | matched>=`1.0` | delay<=`nan` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.491617` | matched>=`5.0` | delay<=`240.0` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.491617` | matched>=`5.0` | delay<=`nan` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.5` | matched>=`0.0` | delay<=`240.0` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.5` | matched>=`0.0` | delay<=`nan` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.5` | matched>=`1.0` | delay<=`240.0` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`
- score `80.47` | pnl `1062.76` | roi `4.72%` | support `49` | cost<=`0.99` | imbalance<=`0.5` | matched>=`1.0` | delay<=`nan` | under_par>=`0.5` | worse<=`0.0` | override<=`0.97`

## Sample Sequences
- `0x413089dc17ed079a4f0634f536ee40d54001716f1aae756db72122049adddcdc` pnl `10.43`, cost `0.7393333333333333`, matched `40.0`, delay `114.666667`, under_par_ratio `1.0`, worse_ratio `0.0`, merge/redeem `10.426667`
- `0xbce5a54c8eebe220ac1d252383c7945c264d50c5ef910757d8eb048e3628d326` pnl `28.79`, cost `0.7654888478722219`, matched `122.764388`, delay `0.466667`, under_par_ratio `0.6`, worse_ratio `0.4`, merge/redeem `28.789618`
- `0x6e32c838780b9da439aff54df5b375343144f07fff7561bfc104005b25b4ec39` pnl `0.70`, cost `0.9304152682580948`, matched `10.0`, delay `13.333333`, under_par_ratio `0.5`, worse_ratio `0.5`, merge/redeem `0.695847`
- `0x0d7b74db994f2e3584012cfeec7e6cded88b42bedc55480e50a468793f4e4c61` pnl `1.13`, cost `0.9932170519887971`, matched `167.3`, delay `59.8`, under_par_ratio `0.75`, worse_ratio `0.25`, merge/redeem `1.134787`
- `0xcee107c89d3b6b40cb46d4fd3dfed2696ec8474e1f705f51f4668558be6ff607` pnl `10.87`, cost `0.9342859810192583`, matched `165.478975`, delay `0.466667`, under_par_ratio `0.884615`, worse_ratio `0.115385`, merge/redeem `10.874289`
- `0x2f7aa1eacd665c1c40a9344f8bca6ff3f8a2686ebcc510f42defb058cc580883` pnl `6.34`, cost `0.947140294973499`, matched `119.964157`, delay `0.566667`, under_par_ratio `0.529412`, worse_ratio `0.470588`, merge/redeem `6.34127`
- `0x8f6b3594824957123da6025938307fc2b51b6df7331828d35ed7bfce595d021d` pnl `6.87`, cost `0.9925383424253772`, matched `920.986499`, delay `1.133333`, under_par_ratio `0.848485`, worse_ratio `0.0`, merge/redeem `6.872086`
- `0x0679631969df166f3b147723078c968c028a2cb03d0ccbf8466aabc7322ae242` pnl `0.81`, cost `0.9916640741378493`, matched `97.67`, delay `1.333333`, under_par_ratio `0.833333`, worse_ratio `0.166667`, merge/redeem `0.81417`
- `0x2f7aa1eacd665c1c40a9344f8bca6ff3f8a2686ebcc510f42defb058cc580883` pnl `47.24`, cost `0.9019882216070584`, matched `481.992132`, delay `0.366667`, under_par_ratio `0.700935`, worse_ratio `0.233645`, merge/redeem `47.240906`
- `0x2f7aa1eacd665c1c40a9344f8bca6ff3f8a2686ebcc510f42defb058cc580883` pnl `2.01`, cost `0.9828877594758952`, matched `117.720605`, delay `0.933333`, under_par_ratio `0.727273`, worse_ratio `0.181818`, merge/redeem `12.608127`
