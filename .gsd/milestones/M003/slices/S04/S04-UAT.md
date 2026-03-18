---
id: S04-UAT
parent: S04
milestone: M003
uat_type: artifact-driven
completed_at: 2026-03-18T16:08:44+01:00
---

# S04: Operator playbook + verification — UAT

**Milestone:** M003
**Written:** 2026-03-18

## UAT Type

- **UAT mode:** artifact-driven
- **Why this mode is sufficient:** This slice produces documentation and verification tooling (not runtime systems). Success means the playbook accurately describes strategies/metrics/CLI, and the verification script correctly validates M003 deliverables. Both can be tested by inspecting artifacts and running commands against synthetic data.

## Preconditions

1. Working directory is `/Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003`
2. Python environment has access to `src/` modules (PYTHONPATH includes src)
3. All S01-S03 deliverables exist (7 strategies, engine with dynamic fees/slippage, backtest infrastructure)
4. No TimescaleDB connection required (verification uses synthetic data only)
5. Git repo in clean state for core immutability check

## Smoke Test

Run the verification script to confirm all M003 deliverables integrate:

```bash
cd /Users/igol/Documents/repo/polyedge/.gsd/worktrees/M003
bash scripts/verify_m003_milestone.sh
```

**Expected:** Script prints 8 check results, all with "check PASSED" status, exits with code 0, final summary shows "8/8 checks passed"

## Test Cases

### 1. Playbook File Structure

**Goal:** Confirm playbook exists with all required sections

1. Check file exists:
   ```bash
   test -f src/docs/STRATEGY_PLAYBOOK.md && echo "PASS: File exists"
   ```
2. Count sections (should have 8+ major sections):
   ```bash
   grep -c "^## " src/docs/STRATEGY_PLAYBOOK.md
   ```
3. Verify required sections present:
   ```bash
   grep "^## Quick Start" src/docs/STRATEGY_PLAYBOOK.md
   grep "^## Strategy Reference" src/docs/STRATEGY_PLAYBOOK.md
   grep "^## CLI Reference" src/docs/STRATEGY_PLAYBOOK.md
   grep "^## Metric Interpretation" src/docs/STRATEGY_PLAYBOOK.md
   grep "^## Go/No-Go Decision Framework" src/docs/STRATEGY_PLAYBOOK.md
   grep "^## Parameter Optimization" src/docs/STRATEGY_PLAYBOOK.md
   grep "^## Troubleshooting" src/docs/STRATEGY_PLAYBOOK.md
   ```

**Expected:** All 7 section headers found, file is 1000+ lines (comprehensive reference doc)

### 2. Playbook Strategy Coverage

**Goal:** Confirm playbook documents all 7 strategies with complete metadata

1. Count strategy subsections:
   ```bash
   grep -c "^### S[1-7]:" src/docs/STRATEGY_PLAYBOOK.md
   ```
2. Check each strategy has entry conditions:
   ```bash
   grep -A10 "^### S1:" src/docs/STRATEGY_PLAYBOOK.md | grep -i "entry"
   grep -A10 "^### S2:" src/docs/STRATEGY_PLAYBOOK.md | grep -i "entry"
   # ... repeat for S3-S7
   ```
3. Check each strategy has parameter documentation:
   ```bash
   grep -A20 "^### S1:" src/docs/STRATEGY_PLAYBOOK.md | grep -i "parameter"
   ```
4. Check grid sizes documented:
   ```bash
   grep "combinations" src/docs/STRATEGY_PLAYBOOK.md | wc -l
   ```

**Expected:** 7 strategy sections found, each includes entry conditions, parameters, and grid size; at least 7 mentions of "combinations"

### 3. Playbook Metric Documentation

**Goal:** Confirm playbook explains all critical metrics with formulas and thresholds

1. Check metric subsections exist:
   ```bash
   grep "^#### " src/docs/STRATEGY_PLAYBOOK.md | grep -i "sharpe"
   grep "^#### " src/docs/STRATEGY_PLAYBOOK.md | grep -i "sortino"
   grep "^#### " src/docs/STRATEGY_PLAYBOOK.md | grep -i "profit_factor"
   grep "^#### " src/docs/STRATEGY_PLAYBOOK.md | grep -i "win_rate"
   grep "^#### " src/docs/STRATEGY_PLAYBOOK.md | grep -i "drawdown"
   ```
2. Check formulas are present:
   ```bash
   grep -i "formula:" src/docs/STRATEGY_PLAYBOOK.md | wc -l
   ```
3. Check thresholds are concrete numbers:
   ```bash
   grep -E "[0-9]+\.[0-9]+" src/docs/STRATEGY_PLAYBOOK.md | head -20
   ```

**Expected:** At least 5 metric subsections found, at least 5 formula definitions, multiple concrete numeric thresholds (e.g., "1.0", "1.2", "52%")

### 4. Playbook Go/No-Go Framework

**Goal:** Confirm playbook defines concrete deployment criteria

1. Check 6-threshold framework exists:
   ```bash
   grep "total_pnl > 0" src/docs/STRATEGY_PLAYBOOK.md
   grep "sharpe_ratio > 1.0" src/docs/STRATEGY_PLAYBOOK.md
   grep "profit_factor > 1.2" src/docs/STRATEGY_PLAYBOOK.md
   grep "win_rate.*52" src/docs/STRATEGY_PLAYBOOK.md
   grep "max_drawdown.*50" src/docs/STRATEGY_PLAYBOOK.md
   grep "consistency.*60" src/docs/STRATEGY_PLAYBOOK.md
   ```
2. Check decision matrix exists (GO/CONDITIONAL/NO-GO):
   ```bash
   grep -i "GO" src/docs/STRATEGY_PLAYBOOK.md | grep -i "conditional"
   ```

**Expected:** All 6 threshold conditions found as exact strings, decision matrix with 3 outcomes documented

### 5. Playbook CLI Examples

**Goal:** Confirm playbook provides copy-pasteable commands

1. Check Quick Start has command examples:
   ```bash
   grep "python3 -m analysis.backtest_strategies" src/docs/STRATEGY_PLAYBOOK.md | head -5
   ```
2. Check CLI Reference documents flags:
   ```bash
   grep "\-\-strategy" src/docs/STRATEGY_PLAYBOOK.md
   grep "\-\-assets" src/docs/STRATEGY_PLAYBOOK.md
   grep "\-\-slippage" src/docs/STRATEGY_PLAYBOOK.md
   grep "\-\-fee-rate" src/docs/STRATEGY_PLAYBOOK.md
   ```
3. Check optimizer commands documented:
   ```bash
   grep "python3 -m analysis.optimize" src/docs/STRATEGY_PLAYBOOK.md
   ```

**Expected:** At least 3 `backtest_strategies` commands in Quick Start, all 4 common flags documented, at least 1 optimizer command

### 6. Playbook Troubleshooting Coverage

**Goal:** Confirm playbook addresses known failure modes

1. Check zero-trade scenario documented:
   ```bash
   grep -i "zero trades" src/docs/STRATEGY_PLAYBOOK.md
   ```
2. Check sparse data issue documented:
   ```bash
   grep -i "sparse data" src/docs/STRATEGY_PLAYBOOK.md
   ```
3. Check optimizer runtime documented:
   ```bash
   grep -i "optimizer.*runtime\|runtime.*optimizer" src/docs/STRATEGY_PLAYBOOK.md
   ```
4. Check S6 limitation documented:
   ```bash
   grep -A5 "^### S6:" src/docs/STRATEGY_PLAYBOOK.md | grep -i "limitation\|intra-market\|streak"
   ```

**Expected:** All 4 issues found in playbook (zero trades, sparse data, optimizer runtime, S6 limitation)

### 7. Verification Script File Structure

**Goal:** Confirm verification script exists and is executable

1. Check file exists with executable permissions:
   ```bash
   test -f scripts/verify_m003_milestone.sh && echo "PASS: File exists"
   test -x scripts/verify_m003_milestone.sh && echo "PASS: Executable"
   ```
2. Count check groups (should have 8):
   ```bash
   grep -cE "^echo \"Check [0-9]:" scripts/verify_m003_milestone.sh
   ```
3. Verify script has structured output format:
   ```bash
   grep "VERIFICATION COMPLETE" scripts/verify_m003_milestone.sh
   ```

**Expected:** File exists, executable bit set, 8 check groups found, structured output format present

### 8. Verification Script Check 1 — File Structure

**Goal:** Confirm script validates M003 file structure changes

1. Run verification script and isolate Check 1 output:
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep -A15 "Check 1:"
   ```
2. Verify checks for old nested structure removal:
   ```bash
   grep "strategies/strategies" scripts/verify_m003_milestone.sh
   ```
3. Verify checks for new S1-S7 folders:
   ```bash
   grep "src/shared/strategies/S[1-7]" scripts/verify_m003_milestone.sh | head -7
   ```

**Expected:** Check 1 output shows "File structure check PASSED", script contains logic testing for old structure absence and new S1-S7 presence

### 9. Verification Script Check 4 — Fee Dynamics

**Goal:** Confirm script validates dynamic fee formula works

1. Run verification script and isolate Check 4 output:
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep -A10 "Check 4:"
   ```
2. Verify fee values printed at 3 price points:
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep "Fee at price"
   ```
3. Check script source has fee comparison logic:
   ```bash
   grep "polymarket_dynamic_fee" scripts/verify_m003_milestone.sh
   ```

**Expected:** Check 4 output shows fee at 0.50 > fee at 0.10 ≈ fee at 0.90, prints "Fee dynamics check PASSED"

### 10. Verification Script Check 5 — Slippage Impact

**Goal:** Confirm script validates slippage parameter affects PnL

1. Run verification script and isolate Check 5 output:
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep -A10 "Check 5:"
   ```
2. Verify two PnL values printed (with and without slippage):
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep "PnL with slippage"
   ```
3. Check script source has slippage comparison logic:
   ```bash
   grep "make_trade" scripts/verify_m003_milestone.sh
   ```

**Expected:** Check 5 output shows two different PnL values, prints "Slippage impact check PASSED"

### 11. Verification Script Check 8 — Core Immutability

**Goal:** Confirm script validates R010 constraint (src/core/ unchanged)

1. Run verification script and isolate Check 8 output:
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep -A10 "Check 8:"
   ```
2. Verify git diff command used:
   ```bash
   grep "git diff.*src/core" scripts/verify_m003_milestone.sh
   ```
3. Check script tests for empty diff output:
   ```bash
   grep -A3 "git diff.*src/core" scripts/verify_m003_milestone.sh | grep "if.*test.*-z"
   ```

**Expected:** Check 8 output shows "Core immutability check PASSED", script runs git diff and tests for empty output

### 12. Verification Script Exit Code

**Goal:** Confirm script exits 0 when all checks pass (binary go/no-go signal)

1. Run verification script and capture exit code:
   ```bash
   bash scripts/verify_m003_milestone.sh
   echo "Exit code: $?"
   ```
2. Verify summary shows 8/8 passed:
   ```bash
   bash scripts/verify_m003_milestone.sh 2>&1 | grep "Checks passed:"
   ```

**Expected:** Exit code 0, summary shows "Checks passed: 8/8", "All M003 verification checks passed" message

## Edge Cases

### Edge Case 1: Playbook Readable Without Prior Context

**Scenario:** New operator with no M003 history reads playbook

1. Open `src/docs/STRATEGY_PLAYBOOK.md` in text editor
2. Jump to Quick Start section
3. Verify commands are complete (no placeholders like `<ASSET>` or `<PATH>`)
4. Jump to Metric Interpretation section
5. Verify thresholds are concrete numbers with units (not vague like "high is good")

**Expected:** All Quick Start commands are copy-pasteable without modification, all metric thresholds are specific numbers (e.g., "Sharpe > 1.0" not "positive Sharpe indicates edge")

### Edge Case 2: Verification Script with Missing Strategy

**Scenario:** One strategy folder deleted to test verification failure detection

1. Temporarily rename S7 folder:
   ```bash
   mv src/shared/strategies/S7 src/shared/strategies/S7_backup
   ```
2. Run verification script:
   ```bash
   bash scripts/verify_m003_milestone.sh
   ```
3. Verify script exits 1 with diagnostic:
   ```bash
   echo "Exit code: $?"
   bash scripts/verify_m003_milestone.sh 2>&1 | grep "Missing directory"
   ```
4. Restore S7 folder:
   ```bash
   mv src/shared/strategies/S7_backup src/shared/strategies/S7
   ```

**Expected:** Script exits 1, Check 1 fails with "Missing directory: src/shared/strategies/S7" message

### Edge Case 3: Verification Script with Core Modified

**Scenario:** src/core/ file modified to test R010 constraint detection

1. Create temporary file in src/core/:
   ```bash
   echo "test" > src/core/test_violation.py
   ```
2. Run verification script:
   ```bash
   bash scripts/verify_m003_milestone.sh
   ```
3. Verify script exits 1 with diagnostic showing git diff:
   ```bash
   echo "Exit code: $?"
   bash scripts/verify_m003_milestone.sh 2>&1 | grep "src/core/"
   ```
4. Remove test file:
   ```bash
   rm src/core/test_violation.py
   ```

**Expected:** Script exits 1, Check 8 fails with git diff output showing untracked test_violation.py file

### Edge Case 4: Playbook Troubleshooting Matches S03 Forward Intelligence

**Scenario:** Confirm playbook addresses known issues from S03 task summaries

1. Check S03 forward intelligence items documented:
   ```bash
   # S6 intra-market limitation
   grep -i "intra-market" src/docs/STRATEGY_PLAYBOOK.md
   # S7 inline duplication
   grep -i "inline duplication\|duplicates.*inline" src/docs/STRATEGY_PLAYBOOK.md
   # Zero-trade scenarios
   grep -i "zero trades" src/docs/STRATEGY_PLAYBOOK.md
   # Sparse data
   grep -i "sparse data" src/docs/STRATEGY_PLAYBOOK.md
   ```

**Expected:** All 4 S03 forward intelligence items documented in playbook (S6 limitation in Strategy Reference, S7 note in Strategy Reference, zero trades in Troubleshooting, sparse data in Troubleshooting)

## Failure Signals

**Playbook failures:**
- Missing sections (grep for "## Quick Start" etc. returns no matches)
- Incomplete strategy coverage (fewer than 7 "### S[1-7]:" headers found)
- Vague thresholds (no concrete numbers like "1.0" or "52%" in Go/No-Go section)
- Missing CLI examples (Quick Start has no `python3 -m analysis.backtest_strategies` commands)

**Verification script failures:**
- Script exits 1 (at least one check failed)
- Summary shows "Checks failed: N/8" where N > 0
- Check output missing "check PASSED" status line
- Fewer than 8 "Check N:" headers in script source

**Integration failures:**
- Playbook references strategies that don't exist (e.g., documents S8 when only S1-S7 exist)
- Playbook CLI examples use wrong flag names (e.g., `--slip` instead of `--slippage`)
- Verification script tests wrong file paths (e.g., checks for `src/strategies/S1/` when actual path is `src/shared/strategies/S1/`)

## Requirements Proved By This UAT

- **R019** (Backtest output includes clear profitability metrics and go/no-go guidance) — Test Cases 3, 4 prove playbook documents 18 metrics with formulas and 6-threshold decision framework
- **R018** (Each strategy independently runnable via `--strategy SID` CLI flag) — Test Case 5 proves playbook documents `--strategy` flag usage with examples
- **R014-R022** (all M003 requirements) — Test Case 12 proves verification script validates all M003 deliverables and exits 0

## Not Proven By This UAT

**Live runtime behavior:** This UAT validates artifacts (playbook content, verification script logic) but does not run real backtests against production TimescaleDB. The following are intentionally not proven:

1. **Strategies produce profitable results on real data:** Verification Check 6 uses synthetic MarketSnapshot only. Real profitability requires user to run `python3 -m analysis.backtest_strategies` against production DB.

2. **Optimizer completes in documented runtime:** Playbook says "5-15 minutes per strategy on single asset" but UAT doesn't run optimizer to confirm timing.

3. **DB queries work correctly:** Strategies use `_get_price()` which queries MarketSnapshot. Verification uses synthetic data only, so SQL performance and correctness are not tested.

4. **Cross-asset consistency holds:** Playbook documents consistency_score metric for cross-asset generalization, but UAT doesn't run multi-asset backtests to verify calculation.

5. **S6 legitimately produces zero trades:** Playbook Troubleshooting says S6 may produce zero trades if no streaks exist. UAT doesn't run S6 against real data to confirm this scenario.

**These gaps are acceptable** because:
- M003 roadmap explicitly states user runs real backtests post-milestone at their own pace (not gated by completion)
- S04 slice plan specifies "Proof Level: final-assembly" with "Real runtime required: no"
- Verification script uses synthetic data per S02 forward intelligence (no DB dependency)

## Notes for Tester

**Expected duration:** 15-20 minutes for complete UAT (12 test cases + 4 edge cases)

**Prerequisites:** Must be run from M003 worktree. If you try to run from main repo, verification Check 8 will fail (git diff will show worktree-specific changes).

**Known rough edges:**
1. Playbook is long (1189 lines) — use text search to find specific sections rather than reading linearly
2. Verification script output is verbose (8 checks × ~10 lines each) — focus on "check PASSED/FAILED" lines and final summary
3. Edge Case 2 and 3 modify filesystem state — restore original state after testing or verification will fail on subsequent runs

**What to gut-check:**
- Do playbook metric thresholds feel realistic for 5-minute crypto markets? (e.g., Sharpe > 1.0 achievable but not trivial)
- Are playbook CLI examples actually copy-pasteable without modification?
- Does verification script output clearly indicate which check failed when you intentionally break something?

**Areas not covered by UAT:**
- Playbook prose quality (grammar, clarity, formatting) — assumed to be good if grep checks pass
- Verification script performance (runtime) — assumed to be fast (<5s per S02 forward intelligence)
- Real DB backtest results — user responsibility post-milestone
