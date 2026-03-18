"""Dynamic strategy discovery and instantiation.

Scans ``shared/strategies/*/strategy.py`` for :class:`BaseStrategy` subclasses
and makes them available by folder name (e.g. ``'S1'``).
"""

from __future__ import annotations

import importlib
from pathlib import Path

from .base import BaseStrategy

_registry: dict[str, type[BaseStrategy]] = {}


def discover_strategies() -> dict[str, type[BaseStrategy]]:
    """Scan shared/strategies/*/strategy.py for BaseStrategy subclasses.

    Returns a **copy** of the internal registry so callers can inspect
    discovered strategies without mutating module state.
    """
    strategies_dir = Path(__file__).parent
    _registry.clear()
    for item in sorted(strategies_dir.iterdir()):
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        strategy_module_path = item / "strategy.py"
        if not strategy_module_path.exists():
            continue
        module_name = f"shared.strategies.{item.name}.strategy"
        try:
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy
                ):
                    _registry[item.name] = attr
                    break
        except Exception:
            continue  # skip broken strategy modules
    return dict(_registry)


def get_strategy(strategy_id: str) -> BaseStrategy:
    """Instantiate a strategy by folder-name ID (e.g. ``'S1'``).

    Auto-discovers if the registry is empty.  Raises :class:`KeyError` with
    a diagnostic message listing available IDs when the requested strategy
    is not found.
    """
    if not _registry:
        discover_strategies()
    if strategy_id not in _registry:
        raise KeyError(
            f"Strategy '{strategy_id}' not found. "
            f"Available: {sorted(_registry.keys())}"
        )
    strategy_cls = _registry[strategy_id]
    # Strategy class must define a default config via its module's get_default_config()
    config_module_name = f"shared.strategies.{strategy_id}.config"
    config_module = importlib.import_module(config_module_name)
    config = config_module.get_default_config()
    return strategy_cls(config)
