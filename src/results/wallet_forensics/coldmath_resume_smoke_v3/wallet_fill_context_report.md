# Fill Context Report: ColdMath

## Coverage
- Total fills analyzed: `20716`
- Token-mapped fills: `20716`
- Weather fills: `20716`
- Fills with any context: `20716`
- Full local quote pairs: `0`
- Full price-history pairs: `20716`

## Context Sources
- `prices_history`: `20716`

## Execution Labels
### Quote-Based
- `unknown`: `20716`
### Price-History-Based
- `nearby_trade_aligned`: `8677`
- `worse_than_nearby_trade`: `7588`
- `better_than_nearby_trade`: `4451`

## Pair-Cost Signals
- Fills with `executed + opposite history price < 1`: `12095`
- Buy fills with `executed + opposite history price < 1`: `12095`
- Buy-fill under-par rate: `58.5261`%
- Fills with `executed + opposite local ask < 1`: `0`
- Avg local execution edge (bps): `None`
- Avg price-history execution edge (bps): `-43.9666`

### Under-Par Buy Labels
- `nearby_trade_aligned`: `7398`
- `better_than_nearby_trade`: `4407`
- `worse_than_nearby_trade`: `290`
### Non-Under-Par Buy Labels
- `worse_than_nearby_trade`: `7298`
- `nearby_trade_aligned`: `1229`
- `better_than_nearby_trade`: `44`

## Top Conditions
- `0xbee8e1a45964fc6c8115ef478b7f68600c56380b8df1adc4503377897606e5e1` fills `658`, history under-par `410`, quote-labeled `0`, history-labeled `658`
- `0xead8838e1f75807c4ab695a436b50adf20b22d30ebe263d2309ae53ca1e19ed1` fills `638`, history under-par `524`, quote-labeled `0`, history-labeled `638`
- `0xf52a906c49f212334d3a6b1b0660aee846a12f90616a6668f2686e8cb0507451` fills `474`, history under-par `413`, quote-labeled `0`, history-labeled `474`
- `0x7c03930d203c1cac45fd513cb32d818cf0ace564cd2768600cc02c00badfc766` fills `423`, history under-par `344`, quote-labeled `0`, history-labeled `423`
- `0xdfd780958dfcbfe6af4ee70a4a1028b2bb4bb2c0950f08e89d46bd54b93281f1` fills `379`, history under-par `348`, quote-labeled `0`, history-labeled `379`
- `0xbe57e65d2625915a12a0f2c1821f0e3d8660288dd368472cf57d4e6f84134abe` fills `361`, history under-par `232`, quote-labeled `0`, history-labeled `361`
- `0x7c55c68ea1bb1b5312eef24605cfc7225d08dd8ed6cd0d910295dd14ee232eae` fills `329`, history under-par `227`, quote-labeled `0`, history-labeled `329`
- `0x2f7aa1eacd665c1c40a9344f8bca6ff3f8a2686ebcc510f42defb058cc580883` fills `323`, history under-par `189`, quote-labeled `0`, history-labeled `323`
- `0xbcf46994658ed52b8c9c21caceaf06a8d9aaa26ba8934e3e40ad5d7047e19dc5` fills `314`, history under-par `206`, quote-labeled `0`, history-labeled `314`
- `0x5f7b7241cad539bdd117b39d683aa5e2109296a20b194396192462a9871eeeb1` fills `292`, history under-par `262`, quote-labeled `0`, history-labeled `292`

## Limitations
- Local `market_quotes` only cover the periods we personally collected, so true quote snapshots may be sparse for older fills.
- Historical `prices-history` points are nearby trade prices, not guaranteed bid/ask snapshots, so maker-vs-taker inference remains approximate without quote coverage.
- A fill can still be strategically correct even if its isolated execution looks aggressive; sequence-level inventory management still matters.
