---
estimated_steps: 6
estimated_files: 7
---

# T02: Create 7 new strategy folders from TEMPLATE

**Slice:** S01 — Clean slate + strategy scaffolding
**Milestone:** M003

## Description

Create scaffolding for all 7 research-backed strategies by copying the updated TEMPLATE folder and customizing each copy with the correct strategy ID, class names, and descriptive names. Each strategy will have stub implementations (evaluate returns None, get_param_grid returns empty dict) that S03 will replace with real logic.

The 7 strategies are mapped in S01-RESEARCH.md under "Strategy Naming Map":
- S1: S1_calibration (Calibration Mispricing)
- S2: S2_momentum (Early Momentum)
- S3: S3_reversion (Mean Reversion)
- S4: S4_volatility (Volatility Regime)
- S5: S5_time_phase (Time-Phase Entry)
- S6: S6_streak (Streak/Sequence)
- S7: S7_composite (Composite Ensemble)

This task batches all 7 strategy creations because they follow an identical pattern — batching reduces context overhead and lets you work efficiently.

## Steps

1. For each strategy number 1 through 7, perform the following substeps:
   - Copy `src/shared/strategies/TEMPLATE/` to `src/shared/strategies/S{N}/`
   - In `config.py`: rename `TemplateConfig` class to `S{N}Config`
   - In `config.py`: update `get_default_config()` to return `S{N}Config` with correct `strategy_id="S{N}"` and `strategy_name="S{N}_{name}"` from the naming map
   - In `config.py`: verify `get_param_grid()` exists and add TODO comment if needed: `# TODO: Define parameter ranges in S03`
   - In `strategy.py`: rename `TemplateStrategy` class to `S{N}Strategy`
   - In `strategy.py`: update import to `from shared.strategies.S{N}.config import S{N}Config`
   - In `strategy.py`: update class docstring to match the strategy description from the naming map
   - In `strategy.py`: verify `evaluate()` returns `None` and add TODO comment: `# TODO: Implement in S03`
2. After creating all 7, do a quick sanity check: verify each folder has `__init__.py`, `config.py`, `strategy.py`
3. Verify class names are unique (no leftover "Template" references)

## Must-Haves

- [ ] 7 new strategy folders exist: `src/shared/strategies/S1/` through `S7/`
- [ ] Each folder contains `__init__.py` (empty), `config.py`, `strategy.py`, and optionally `README.md`
- [ ] Each `config.py` has correctly named config class (e.g. `S1Config`, `S2Config`, etc.)
- [ ] Each `get_default_config()` returns correct `strategy_id` and `strategy_name` from the naming map
- [ ] Each `strategy.py` has correctly named strategy class (e.g. `S1Strategy`, `S2Strategy`, etc.)
- [ ] Each `strategy.py` imports the correct config class from its own package
- [ ] Each `evaluate()` method returns `None` with TODO comment
- [ ] Each `get_param_grid()` returns empty dict `{}` with TODO comment
- [ ] No "Template" string remains in class names (case-sensitive search)

## Verification

- `for i in {1..7}; do test -d src/shared/strategies/S$i || exit 1; done` — all 7 folders exist
- `for i in {1..7}; do test -f src/shared/strategies/S$i/__init__.py || exit 1; done` — all have `__init__.py`
- `for i in {1..7}; do grep -q "class S${i}Strategy" src/shared/strategies/S$i/strategy.py || exit 1; done` — class names correct
- `for i in {1..7}; do grep -q "class S${i}Config" src/shared/strategies/S$i/config.py || exit 1; done` — config class names correct
- `! grep -r "TemplateStrategy\|TemplateConfig" src/shared/strategies/S[1-7]/` — no leftover Template references
- Spot check: `grep "strategy_name" src/shared/strategies/S1/config.py | grep "S1_calibration"` — naming map applied correctly

## Inputs

- `src/shared/strategies/TEMPLATE/` — updated template folder from T01 with `get_param_grid()`
- S01-RESEARCH.md section "Strategy Naming Map" — 7 strategy IDs and names
- S01-RESEARCH.md section "Per-Strategy Stub Pattern" — exact code patterns for config and strategy files

## Expected Output

- 7 new strategy folders (`S1/` through `S7/`) with correct class names, IDs, and stub implementations
- Each strategy has:
  - `__init__.py` (empty)
  - `config.py` with `S{N}Config` class and `get_default_config()` returning correct IDs from naming map
  - `strategy.py` with `S{N}Strategy` class and stub `evaluate()` returning None
  - All files ready for S03 to populate with real logic
