#!/bin/bash
# Create 7 new strategy folders from TEMPLATE with correct naming

set -e

# Strategy naming map
declare -A strategy_names=(
    ["1"]="calibration"
    ["2"]="momentum"
    ["3"]="reversion"
    ["4"]="volatility"
    ["5"]="time_phase"
    ["6"]="streak"
    ["7"]="composite"
)

declare -A strategy_descriptions=(
    ["1"]="Calibration Mispricing — exploit systematic bias in 50/50 pricing"
    ["2"]="Early Momentum — detect directional velocity in first 30-60 seconds"
    ["3"]="Mean Reversion — fade early spikes after partial reversion"
    ["4"]="Volatility Regime — enter contrarian only under specific vol conditions"
    ["5"]="Time-Phase Entry — optimal entry timing based on market phase"
    ["6"]="Streak/Sequence — exploit consecutive same-direction outcomes"
    ["7"]="Composite Ensemble — enter only when 2+ strategies agree"
)

for i in {1..7}; do
    echo "Creating strategy S${i}..."
    
    # Copy TEMPLATE folder
    cp -r src/shared/strategies/TEMPLATE/ src/shared/strategies/S${i}/
    
    # Get strategy name and description
    name="${strategy_names[$i]}"
    desc="${strategy_descriptions[$i]}"
    
    # Update config.py
    sed -i '' "s/TemplateConfig/S${i}Config/g" src/shared/strategies/S${i}/config.py
    sed -i '' "s/strategy_id=\"TEMPLATE\"/strategy_id=\"S${i}\"/g" src/shared/strategies/S${i}/config.py
    sed -i '' "s/strategy_name=\"TEMPLATE_strategy\"/strategy_name=\"S${i}_${name}\"/g" src/shared/strategies/S${i}/config.py
    sed -i '' "s/Return the production-default TEMPLATE configuration/Return the production-default S${i} configuration/g" src/shared/strategies/S${i}/config.py
    
    # Add TODO comment to get_param_grid if not already present
    if ! grep -q "# TODO: Define parameter ranges in S03" src/shared/strategies/S${i}/config.py; then
        sed -i '' '/return {}$/i\
    # TODO: Define parameter ranges in S03
' src/shared/strategies/S${i}/config.py
    fi
    
    # Update strategy.py
    sed -i '' "s/TemplateStrategy/S${i}Strategy/g" src/shared/strategies/S${i}/strategy.py
    sed -i '' "s/TemplateConfig/S${i}Config/g" src/shared/strategies/S${i}/strategy.py
    sed -i '' "s/from shared.strategies.TEMPLATE.config/from shared.strategies.S${i}.config/g" src/shared/strategies/S${i}/strategy.py
    sed -i '' "s/Placeholder strategy — replace with your signal detection logic\./S${i} Strategy: ${desc}/g" src/shared/strategies/S${i}/strategy.py
    
    # Add TODO comment to evaluate if not already present
    if ! grep -q "# TODO: Implement in S03" src/shared/strategies/S${i}/strategy.py; then
        sed -i '' '/# Placeholder: no signal detected$/i\
        # TODO: Implement in S03
' src/shared/strategies/S${i}/strategy.py
    fi
    
    echo "  ✓ S${i} created with strategy_name=S${i}_${name}"
done

echo ""
echo "All 7 strategies created successfully."
