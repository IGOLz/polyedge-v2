#!/usr/bin/env python3
"""Create 7 new strategy folders from TEMPLATE with correct naming."""

import shutil
import re
from pathlib import Path

# Strategy naming map
strategies = [
    ("S1", "calibration", "Calibration Mispricing — exploit systematic bias in 50/50 pricing"),
    ("S2", "momentum", "Early Momentum — detect directional velocity in first 30-60 seconds"),
    ("S3", "reversion", "Mean Reversion — fade early spikes after partial reversion"),
    ("S4", "volatility", "Volatility Regime — enter contrarian only under specific vol conditions"),
    ("S5", "time_phase", "Time-Phase Entry — optimal entry timing based on market phase"),
    ("S6", "streak", "Streak/Sequence — exploit consecutive same-direction outcomes"),
    ("S7", "composite", "Composite Ensemble — enter only when 2+ strategies agree"),
]

template_dir = Path("src/shared/strategies/TEMPLATE")
strategies_dir = Path("src/shared/strategies")

for strategy_id, name, description in strategies:
    print(f"Creating strategy {strategy_id}...")
    
    # Copy TEMPLATE folder
    target_dir = strategies_dir / strategy_id
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(template_dir, target_dir)
    
    # Update config.py
    config_file = target_dir / "config.py"
    config_content = config_file.read_text()
    
    config_content = config_content.replace("TemplateConfig", f"{strategy_id}Config")
    config_content = config_content.replace('strategy_id="TEMPLATE"', f'strategy_id="{strategy_id}"')
    config_content = config_content.replace('strategy_name="TEMPLATE_strategy"', f'strategy_name="{strategy_id}_{name}"')
    config_content = config_content.replace(
        "Return the production-default TEMPLATE configuration",
        f"Return the production-default {strategy_id} configuration"
    )
    
    # Add TODO comment to get_param_grid if not present
    if "# TODO: Define parameter ranges in S03" not in config_content:
        config_content = config_content.replace(
            "    return {}",
            "    # TODO: Define parameter ranges in S03\n    return {}"
        )
    
    config_file.write_text(config_content)
    
    # Update strategy.py
    strategy_file = target_dir / "strategy.py"
    strategy_content = strategy_file.read_text()
    
    strategy_content = strategy_content.replace("TemplateStrategy", f"{strategy_id}Strategy")
    strategy_content = strategy_content.replace("TemplateConfig", f"{strategy_id}Config")
    strategy_content = strategy_content.replace(
        "from shared.strategies.TEMPLATE.config",
        f"from shared.strategies.{strategy_id}.config"
    )
    strategy_content = strategy_content.replace(
        "Placeholder strategy — replace with your signal detection logic.",
        f"{strategy_id} Strategy: {description}"
    )
    
    # Add TODO comment to evaluate if not present
    if "# TODO: Implement in S03" not in strategy_content:
        strategy_content = strategy_content.replace(
            "        # Placeholder: no signal detected",
            "        # TODO: Implement in S03\n        # Placeholder: no signal detected"
        )
    
    strategy_file.write_text(strategy_content)
    
    print(f"  ✓ {strategy_id} created with strategy_name={strategy_id}_{name}")

print("\nAll 7 strategies created successfully.")
