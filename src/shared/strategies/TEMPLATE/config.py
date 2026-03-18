"""TEMPLATE strategy configuration — copy and customize for new strategies.

Rename this module's class and replace the example fields with your strategy's
real parameters.  Keep ``get_default_config()`` returning an instance with
sensible production defaults.
"""

from dataclasses import dataclass

from shared.strategies.base import StrategyConfig


@dataclass
class TemplateConfig(StrategyConfig):
    """Configuration for a new strategy.

    TODO: Rename this class to ``S<N>Config`` (e.g. ``S3Config``).
    TODO: Replace the example fields below with your strategy's parameters.
    """

    # Example: price threshold for entry filter
    example_threshold: float = 0.50

    # Example: rolling window size in seconds
    example_window_seconds: int = 30

    # Example: minimum spread to consider
    example_min_spread: float = 0.05


def get_default_config() -> TemplateConfig:
    """Return the production-default TEMPLATE configuration.

    TODO: Update ``strategy_id`` to your folder name (e.g. ``'S3'``)
          and ``strategy_name`` to a descriptive slug (e.g. ``'S3_momentum'``).
    """
    return TemplateConfig(
        strategy_id="TEMPLATE",
        strategy_name="TEMPLATE_strategy",
    )


def get_param_grid() -> dict[str, list]:
    """Return grid-search parameter space for this strategy.

    The optimizer generates the Cartesian product of all parameter values
    and backtests every combination.

    Example:
        return {
            "example_threshold": [0.30, 0.40, 0.50],
            "example_window_seconds": [10, 20, 30],
        }

    Returns:
        Empty dict (no optimization) — replace with real parameters.
    """
    return {}
