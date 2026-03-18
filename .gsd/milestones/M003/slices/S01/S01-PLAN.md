# S01: Clean slate + strategy scaffolding

**Goal:** Replace disposable proof-of-concept strategies (S1 spike reversion, S2 volatility) with scaffolding for 7 research-backed strategies. After completion, old S1/S2 are deleted, TEMPLATE includes `get_param_grid()`, and 7 empty strategy folders exist with stub implementations that the registry can discover.

**Demo:** Running `discover_strategies()` finds 7 new strategies (S1 through S7) plus TEMPLATE. Each strategy can be instantiated with `get_strategy('S1')` and has the correct strategy_id, strategy_name, and a stub `evaluate()` that returns `None`.

## Must-Haves

- Old `src/shared/strategies/S1/` and `S2/` deleted
- `src/shared/strategies/TEMPLATE/config.py` includes skeleton `get_param_grid()` function
- `src/shared/strategies/TEMPLATE/README.md` updated to emphasize param grid requirement
- 7 new strategy folders (`S1/` through `S7/`) created by copying TEMPLATE
- Each new strategy has correct class names (e.g. `S1Strategy`, `S1Config`) and IDs matching the naming map from M003-ROADMAP.md
- Each new strategy's `evaluate()` returns `None` with TODO comment for S03
- Each new strategy's `get_param_grid()` returns empty dict with TODO comment
- Registry discovers all 7 new strategies + TEMPLATE
- Each strategy can be instantiated and has correct `strategy_id` and `strategy_name`

## Verification

- `bash scripts/verify_s01_scaffolding.sh` — checks:
  - Old S1, S2 folders deleted
  - TEMPLATE has `get_param_grid()` function
  - All 7 new strategy folders exist with required files (`__init__.py`, `config.py`, `strategy.py`)
  - Registry discovers all 7 strategies + TEMPLATE
  - Each strategy can be instantiated with correct IDs and names
  - Each strategy's `evaluate()` returns `None` (stub behavior)
  - Script exits 0 on success, non-zero on failure

## Integration Closure

- Upstream surfaces consumed: `shared/strategies/base.py` (BaseStrategy, StrategyConfig, MarketSnapshot, Signal), `shared/strategies/registry.py` (discover_strategies, get_strategy)
- New wiring introduced in this slice: none — registry auto-discovery already exists
- What remains before the milestone is truly usable end-to-end: S02 must add dynamic fees and slippage to the engine; S03 must implement real `evaluate()` logic for all 7 strategies; S04 must write operator playbook

## Observability / Diagnostics

**Runtime Signals:**
- Registry discovery: `discover_strategies()` output includes strategy IDs and counts — inspect via Python REPL or logging
- Instantiation: `get_strategy('S1')` returns valid strategy instance with correct `strategy_id` and `strategy_name` attributes
- Stub behavior: All new strategies' `evaluate()` returns `None` — visible via direct call or engine backtest (no signals generated)

**Inspection Surfaces:**
- `scripts/verify_s01_scaffolding.sh` — automated verification script that checks folder structure, registry discovery, and instantiation
- Manual check: `ls src/shared/strategies/` shows 7 new folders (S1-S7) and TEMPLATE, no old S1/S2
- Python snippet: `from shared.strategies.registry import discover_strategies; print(discover_strategies().keys())` lists all discovered strategies
- Individual strategy check: `from shared.strategies.registry import get_strategy; s = get_strategy('S1'); print(s.config.strategy_id, s.config.strategy_name)`

**Failure Visibility:**
- Missing strategy folder: `discover_strategies()` won't include it in returned dict, verification script fails
- Wrong class name: Registry discovery fails or imports crash with `AttributeError`
- Wrong strategy ID: Instantiation succeeds but `strategy_id` assertion in verification script fails
- Missing `get_param_grid()`: `AttributeError` when optimizer tries to access function

**Redaction Constraints:**
- No sensitive data in this slice — all code is scaffolding and stubs
- Strategy names are public research descriptions, no proprietary logic until S03

## Tasks

- [x] **T01: Delete old strategies and update TEMPLATE** `est:20m`
  - Why: Clear out disposable proof-of-concept strategies and establish the new strategy shape (with param grid) that all new strategies will inherit
  - Files: `src/shared/strategies/S1/`, `src/shared/strategies/S2/`, `src/shared/strategies/TEMPLATE/config.py`, `src/shared/strategies/TEMPLATE/README.md`
  - Do: (1) Delete `S1/` and `S2/` folders entirely. (2) Add `get_param_grid()` skeleton to TEMPLATE config.py returning empty dict with docstring explaining grid-search usage. (3) Update TEMPLATE README.md section 6 to make param grid non-optional and more prominent. Use the exact patterns from S01-RESEARCH.md.
  - Verify: `! test -d src/shared/strategies/S1`, `! test -d src/shared/strategies/S2`, `grep -q "get_param_grid" src/shared/strategies/TEMPLATE/config.py`
  - Done when: Old S1/S2 deleted, TEMPLATE config.py contains `get_param_grid()`, README section 6 updated

- [ ] **T02: Create 7 new strategy folders from TEMPLATE** `est:45m`
  - Why: Populate the strategies folder with scaffolding for all 7 research-backed strategies; S03 will implement real logic
  - Files: `src/shared/strategies/S1/` through `S7/` (7 new folders)
  - Do: For each strategy S1-S7: (1) Copy TEMPLATE folder to new strategy folder. (2) Rename classes: `TemplateConfig` → `S{N}Config`, `TemplateStrategy` → `S{N}Strategy`. (3) Update `get_default_config()` to return correct `strategy_id` and `strategy_name` from the naming map in S01-RESEARCH.md. (4) Add empty `get_param_grid()` with TODO comment: `# TODO: Define parameter ranges in S03`. (5) Keep `evaluate()` returning `None` with comment: `# TODO: Implement in S03`. (6) Update import in strategy.py: `from shared.strategies.S{N}.config import S{N}Config`. Follow the per-strategy stub pattern from S01-RESEARCH.md exactly.
  - Verify: `for i in {1..7}; do test -d src/shared/strategies/S$i && test -f src/shared/strategies/S$i/strategy.py || exit 1; done`
  - Done when: 7 new strategy folders exist, each with `__init__.py`, `config.py`, `strategy.py` containing correctly named classes and IDs from the naming map

- [ ] **T03: Write verification script and prove registry discovery** `est:25m`
  - Why: Deliver the slice's verification contract and prove the scaffolding works end-to-end
  - Files: `scripts/verify_s01_scaffolding.sh`
  - Do: Write bash script implementing all checks from the Verification section above. Check folder deletion, TEMPLATE updates, new folder existence, registry discovery (Python snippet calling `discover_strategies()` and checking for all 7 + TEMPLATE), and instantiation (Python snippet calling `get_strategy('S1')` through `get_strategy('S7')` and asserting correct IDs). Script exits 0 only if all checks pass. Run the script and fix any failures.
  - Verify: `bash scripts/verify_s01_scaffolding.sh` exits 0
  - Done when: Verification script exists, runs without errors, and proves all must-haves are met

## Files Likely Touched

- `src/shared/strategies/S1/` (deleted, then recreated)
- `src/shared/strategies/S2/` (deleted, then recreated)
- `src/shared/strategies/S3/` through `S7/` (created)
- `src/shared/strategies/TEMPLATE/config.py`
- `src/shared/strategies/TEMPLATE/README.md`
- `scripts/verify_s01_scaffolding.sh`
