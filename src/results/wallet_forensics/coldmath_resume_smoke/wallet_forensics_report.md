# Wallet Forensics Report: ColdMath

## Wallet Identity
- Proxy wallet: `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11`
- Profile name: `ColdMath`
- Pseudonym: `Fussy-Expedition`
- Bio: `Edge Compounds`
- Total traded markets: `4026`
- Report scope: `weather_only`

## Completeness
- Raw trades fetched: `1`
- Raw activity rows fetched: `1`
- Distinct receipts fetched: `1`
- Market contexts fetched: `1`
- Ledger events rebuilt: `1`
- Backfill complete: `False`

## PnL Attribution
- Rebuilt realized PnL: `0.00`
- Trade events: `1`
- Merge events: `0`
- Redeem events: `0`

## Playbook Catalog
- No rules inferred.

## Replay Results
- No high-confidence shadow trades were generated.

## Limitations
- Public reconstruction cannot observe canceled orders, resting quotes, or private intent.
- Offchain order placement is inferred only through observed fills and onchain settlement traces.
- Conversion support is implemented, but this wallet currently exposes few or no public conversion fixtures.
