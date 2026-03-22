# Wallet Forensics Report: ColdMath

## Wallet Identity
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Profile name: `ColdMath`
- Pseudonym: `Fussy-Expedition`
- Bio: `Edge Compounds`
- Total traded markets: `4074`
- Report scope: `weather_only`

## Completeness
- Raw trades fetched: `20937`
- Raw activity rows fetched: `21883`
- Distinct receipts fetched: `20964`
- Market contexts fetched: `5077`
- Ledger events rebuilt: `23426`
- Playbook sequences extracted: `1551`
- Strategy blueprints generated: `5`
- Backfill complete: `True`

## PnL Attribution
- Rebuilt realized PnL: `4564.24`
- Trade events: `20716`
- Merge events: `888`
- Redeem events: `46`

## Playbook Catalog
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.
- `inventory_rebalancing_merge` at `0.92`: Bought both sides on the same condition and later merged inventory back into collateral.

## Executable Blueprints
- `inventory_rebalancing_merge` status `ready_for_backtest`, confidence `0.99`, support `1071`, priority `249.15`: Accumulate both sides in the same condition when the reconstructed complete-set cost is below par, keep inventory roughly balanced, and exit by merging back into collateral.
- `neg_risk_basket` status `needs_exit_research`, confidence `0.94`, support `421`, priority `135.80`: Construct a same-side basket across sibling negative-risk markets when the basket cost is below a synthetic complete set, then monetize through event completion or later operational exits.
- `late_redemption_farming` status `operational_only`, confidence `0.92`, support `43`, priority `85.32`: Hold winning inventory through resolution and redeem directly, treating redemption as an operational exit path rather than alpha by itself.
- `dust_long_tail_bucket` status `needs_exit_research`, confidence `0.89`, support `10`, priority `26.55`: Pick up extremely low-priced tail buckets, likely as convex payoff scraps or as complements to a larger basket.

## Replay Results
- Shadow trades: `20499`
- Slippage-free replay PnL: `-16792.65`
- Conservative replay PnL: `-25179.81`
- `0xe9cb41d86c1c6fe6b33e3ce4f35136dd48684f5f75379a3568c8ac8d849874b8` `33392817978585616196579783403400494696114510963967743175567807898786014038312` size `3000.0` from `0.5532583166666667` to `1.0` => `1340.23`
- `0xd7810f2a75674d5abc6661d1161aa1e50f521c464cbc0d3a2fa6cb5d8b56d879` `67684958714439843294150880354501599122496774178028545763947094388520510168316` size `1685.0` from `0.35` to `1.0` => `1095.25`
- `0xe9cb41d86c1c6fe6b33e3ce4f35136dd48684f5f75379a3568c8ac8d849874b8` `33392817978585616196579783403400494696114510963967743175567807898786014038312` size `1134.8` from `0.4182225942897427` to `1.0` => `660.20`
- `0x6149d150cb852cc33f1a27b61d31f311a3877f9c72d4290d71c6b312da49d0a6` `103316971747333220996817811343655928303570076251845238439040307406920831816648` size `409.8` from `0.009` to `1.0` => `406.11`
- `0xd7810f2a75674d5abc6661d1161aa1e50f521c464cbc0d3a2fa6cb5d8b56d879` `67684958714439843294150880354501599122496774178028545763947094388520510168316` size `465.95` from `0.17` to `1.0` => `386.74`
- `0x6149d150cb852cc33f1a27b61d31f311a3877f9c72d4290d71c6b312da49d0a6` `103316971747333220996817811343655928303570076251845238439040307406920831816648` size `487.14` from `0.4265815166071355` to `1.0` => `279.34`
- `0xf63b1f8fcb7fcd48a57557881f08ecfd90aa452940b071736e67d359d9b2465d` `80652516982377685369711127761996778191367164596719958867769486951849149088334` size `6088.55` from `0.9594994949536425` to `1.0` => `246.59`
- `0x28c09c14425c51aa68afeba91141bf466946830ae1d60e53cef77e05823f5eef` `12685209322862714241255964170238266248730334030308154119854913625197279501358` size `255.0` from `0.037784313725490196` to `1.0` => `245.37`
- `0xcf499b3218dd728700e33f2a33f972fecb5c70e99c3a83dd0bccc46d22e3c441` `27848433496495468606640357156941493778033220839621735057605323729230360464629` size `231.2` from `0.03128421280276816` to `0.9935` => `222.46`
- `0xd7810f2a75674d5abc6661d1161aa1e50f521c464cbc0d3a2fa6cb5d8b56d879` `67684958714439843294150880354501599122496774178028545763947094388520510168316` size `200.0` from `0.17` to `1.0` => `166.00`

## Limitations
- Public reconstruction cannot observe canceled orders, resting quotes, or private intent.
- Offchain order placement is inferred only through observed fills and onchain settlement traces.
- Conversion support is implemented, but this wallet currently exposes few or no public conversion fixtures.
