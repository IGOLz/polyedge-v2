"""TEMPLATE: Strategy skeleton — copy this folder to create a new strategy.

This module provides a minimal ``BaseStrategy`` subclass whose ``evaluate()``
returns ``None`` (no signal).  Copy the entire ``TEMPLATE/`` folder, rename
it to ``S3/``, ``S4/``, etc., then implement the detection logic.

See ``TEMPLATE/README.md`` for a step-by-step guide.
"""

from __future__ import annotations

from shared.strategies.base import BaseStrategy, MarketSnapshot, Signal
from shared.strategies.TEMPLATE.config import TemplateConfig


class TemplateStrategy(BaseStrategy):
    """Placeholder strategy — replace with your signal detection logic.

    TODO: Rename this class to ``S<N>Strategy`` (e.g. ``S3Strategy``).
    """

    config: TemplateConfig

    # ── public contract ─────────────────────────────────────────────

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Detect a trading signal from the market snapshot.

        Contract:
        - Pure function: no side effects, no async, no database access.
        - Return a ``Signal`` when entry conditions are met, ``None`` otherwise.
        - Never raise on NaN-heavy, flat, or insufficient data — just return None.

        TODO: Implement your detection logic below.
        """
        prices = snapshot.prices
        cfg = self.config

        # TODO: Step 1 — Guard checks
        # Verify you have enough data to evaluate.  Return None if not.
        # Example:
        #   if len(prices) < cfg.example_window_seconds:
        #       return None

        # TODO: Step 2 — Signal detection logic
        # Scan the prices array for your entry pattern.
        # Example:
        #   current_price = float(prices[cfg.example_window_seconds])
        #   if some_condition(current_price):
        #       ...

        # TODO: Step 3 — Construct and return Signal
        # When entry conditions are met, return a Signal.
        # Use ``entry_second`` as the canonical key in signal_data (see D010).
        # Example:
        #   return Signal(
        #       direction="Up",  # or "Down"
        #       strategy_name=cfg.strategy_name,
        #       entry_price=entry_price,
        #       signal_data={
        #           "entry_second": entry_second,
        #           "your_metric": value,
        #       },
        #   )

        # Placeholder: no signal detected
        return None
