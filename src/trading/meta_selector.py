"""Live meta-selector support for multi-strategy crypto trading.

This module intentionally avoids research-only dependencies such as pandas so
the trading container can boot even when the selector is disabled.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from shared.opportunity_features import (
    context_features,
    numeric_signal_payload,
    strategy_id_from_name,
)
from shared.strategies import MarketSnapshot, Signal
from trading import config
from trading.db import MarketInfo
from trading.utils import debug_log, log


@dataclass(frozen=True)
class SelectorDecision:
    """Resolution of competing live signals for a single market."""

    mode: str
    actual_signal: Signal | None
    model_signal: Signal | None
    scored_candidates: list[dict[str, Any]]
    threshold: float | None
    reason: str


@dataclass(frozen=True)
class _TreeNode:
    prediction: float
    positive_rate: float
    feature_index: int | None = None
    threshold: float | None = None
    left: "_TreeNode | None" = None
    right: "_TreeNode | None" = None

    @property
    def is_leaf(self) -> bool:
        return self.feature_index is None


class _BundleEncoder:
    """Minimal runtime encoder restored from the deployment payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.numeric_columns = list(payload.get("numeric_columns", []))
        self.category_columns = list(payload.get("category_columns", []))
        self.fill_values = {
            str(key): float(value)
            for key, value in dict(payload.get("fill_values", {})).items()
        }
        self.dummy_columns = list(payload.get("dummy_columns", []))
        self.feature_names = list(payload.get("feature_names", []))
        self._dummy_specs = [self._parse_dummy_column(name) for name in self.dummy_columns]

    def transform_rows(self, rows: list[dict[str, Any]]) -> np.ndarray:
        matrix: list[list[float]] = []
        for row in rows:
            values: list[float] = []
            for column in self.numeric_columns:
                values.append(self._numeric_value(row.get(column), self.fill_values.get(column, 0.0)))
            for category_column, expected_value in self._dummy_specs:
                actual = str(row.get(category_column, "unknown"))
                values.append(1.0 if actual == expected_value else 0.0)
            matrix.append(values)
        if not matrix:
            return np.zeros((0, len(self.numeric_columns) + len(self.dummy_columns)), dtype=float)
        return np.array(matrix, dtype=float)

    @staticmethod
    def _numeric_value(value: Any, fallback: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return fallback
        return fallback if math.isnan(numeric) else numeric

    def _parse_dummy_column(self, dummy_column: str) -> tuple[str, str]:
        for category_column in self.category_columns:
            prefix = f"{category_column}_"
            if dummy_column.startswith(prefix):
                return category_column, dummy_column[len(prefix):]
        raise ValueError(f"Cannot map dummy column '{dummy_column}' to a category column.")


class _BundleTreeModel:
    """Minimal runtime tree predictor restored from the deployment payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.root = self._node_from_payload(dict(payload["tree"]))

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.array([self._predict_row(row)[0] for row in X], dtype=float)

    def predict_positive_rate(self, X: np.ndarray) -> np.ndarray:
        return np.array([self._predict_row(row)[1] for row in X], dtype=float)

    def _predict_row(self, row: np.ndarray) -> tuple[float, float]:
        node = self.root
        while not node.is_leaf:
            assert node.feature_index is not None
            assert node.threshold is not None
            assert node.left is not None
            assert node.right is not None
            node = node.left if row[node.feature_index] <= node.threshold else node.right
        return node.prediction, node.positive_rate

    def _node_from_payload(self, payload: dict[str, Any]) -> _TreeNode:
        node = _TreeNode(
            prediction=float(payload["prediction"]),
            positive_rate=float(payload["positive_rate"]),
        )
        if payload.get("type") == "leaf":
            return node
        return _TreeNode(
            prediction=node.prediction,
            positive_rate=node.positive_rate,
            feature_index=int(payload["feature_index"]),
            threshold=float(payload["threshold"]),
            left=self._node_from_payload(dict(payload["left"])),
            right=self._node_from_payload(dict(payload["right"])),
        )


class LiveMetaSelector:
    """Load a deployment bundle and score live candidate signals."""

    def __init__(
        self,
        *,
        bundle_path: Path,
        threshold: float,
        encoder: _BundleEncoder,
        model: _BundleTreeModel,
        experts: tuple[str, ...],
    ) -> None:
        self.bundle_path = bundle_path
        self.threshold = float(threshold)
        self.encoder = encoder
        self.model = model
        self.experts = experts

    @classmethod
    def from_bundle_path(cls, bundle_path: str | Path) -> "LiveMetaSelector":
        path = Path(bundle_path).expanduser().resolve()
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        deployment = dict(payload["deployment"])
        return cls(
            bundle_path=path,
            threshold=float(deployment["recommended_threshold"]),
            encoder=_BundleEncoder(dict(deployment["encoder"])),
            model=_BundleTreeModel(dict(deployment["model"])),
            experts=tuple(str(value) for value in payload.get("experts", [])),
        )

    def score_candidates(
        self,
        market: MarketInfo,
        snapshot: MarketSnapshot,
        signals: list[Signal],
    ) -> list[dict[str, Any]]:
        if not signals:
            return []

        second = max(0, int(snapshot.elapsed_seconds))
        second_signals = {
            strategy_id_from_name(signal.strategy_name): signal
            for signal in signals
        }
        market_day = market.started_at.astimezone(timezone.utc).date().isoformat()
        context = context_features(
            prices=snapshot.prices,
            feature_series=snapshot.feature_series,
            total_seconds=snapshot.total_seconds,
            second=second,
            second_signals=second_signals,
        )

        rows: list[dict[str, Any]] = []
        for candidate_index, signal in enumerate(signals):
            strategy_id = strategy_id_from_name(signal.strategy_name)
            rows.append(
                {
                    "candidate_index": candidate_index,
                    "market_id": market.market_id,
                    "market_type": market.market_type,
                    "asset": str(snapshot.metadata.get("asset", "")).lower(),
                    "duration_minutes": int(snapshot.metadata.get("duration_minutes", 0) or 0),
                    "hour": int(snapshot.metadata.get("hour", market.started_at.hour) or 0),
                    "started_at": market.started_at,
                    "market_day": market_day,
                    "strategy_id": strategy_id,
                    "strategy_name": signal.strategy_name,
                    "direction": signal.direction,
                    "direction_sign": 1 if signal.direction == "Up" else -1,
                    "signal_entry_price": float(signal.entry_price),
                    "peer_same_direction_count": sum(
                        1 for peer in signals if peer.direction == signal.direction
                    )
                    - 1,
                    "peer_opposite_direction_count": sum(
                        1 for peer in signals if peer.direction != signal.direction
                    ),
                    **context,
                    **numeric_signal_payload(signal),
                }
            )

        features = self.encoder.transform_rows(rows)
        predicted_pnl = self.model.predict(features)
        predicted_positive_rate = self.model.predict_positive_rate(features)

        scored: list[dict[str, Any]] = []
        for row, pnl, positive_rate in zip(rows, predicted_pnl, predicted_positive_rate, strict=False):
            enriched = dict(row)
            enriched["predicted_pnl"] = float(pnl)
            enriched["predicted_positive_rate"] = float(positive_rate)
            enriched["passes_meta_threshold"] = float(pnl) >= self.threshold
            scored.append(enriched)
        return scored

    def pick_signal(
        self,
        market: MarketInfo,
        snapshot: MarketSnapshot,
        signals: list[Signal],
    ) -> tuple[Signal | None, list[dict[str, Any]]]:
        scored = self.score_candidates(market, snapshot, signals)
        if not scored:
            return None, scored

        ranked = rank_scored_candidates(scored)
        best_row = ranked[0]
        if not bool(best_row["passes_meta_threshold"]):
            return None, scored
        return signals[int(best_row["candidate_index"])], scored


def rank_scored_candidates(scored_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort scored candidates from strongest to weakest."""
    return sorted(
        scored_candidates,
        key=lambda row: (
            bool(row.get("passes_meta_threshold", False)),
            float(row.get("predicted_pnl", float("-inf"))),
            float(row.get("predicted_positive_rate", float("-inf"))),
            -int(row.get("candidate_index", 0)),
        ),
        reverse=True,
    )


def find_candidate_row(
    scored_candidates: list[dict[str, Any]],
    *,
    candidate_index: int,
) -> dict[str, Any] | None:
    """Return the scored row for *candidate_index* when present."""
    for row in scored_candidates:
        if int(row.get("candidate_index", -1)) == candidate_index:
            return row
    return None


def _validate_mode(mode: str) -> str:
    normalized = (mode or "off").strip().lower()
    if normalized not in {"off", "shadow", "enforce"}:
        log.warning("Invalid LIVE_META_SELECTOR_MODE=%r - falling back to off", mode)
        return "off"
    return normalized


@lru_cache(maxsize=1)
def get_live_meta_selector() -> LiveMetaSelector | None:
    """Return the configured live meta-selector, if enabled."""
    mode = _validate_mode(config.LIVE_META_SELECTOR_MODE)
    bundle_path = config.LIVE_META_SELECTOR_BUNDLE
    if mode == "off" or not bundle_path:
        return None

    try:
        selector = LiveMetaSelector.from_bundle_path(bundle_path)
    except FileNotFoundError:
        log.warning("Meta-selector bundle not found: %s - disabling selector", bundle_path)
        return None
    except Exception as exc:
        log.warning("Failed to load meta-selector bundle %s: %s", bundle_path, exc)
        return None

    debug_log.info(
        "[META] Loaded selector bundle %s | threshold=%.6f | experts=%s",
        selector.bundle_path,
        selector.threshold,
        list(selector.experts),
    )
    return selector


def live_meta_selector_mode() -> str:
    """Return the active selector mode after config validation."""
    selector = get_live_meta_selector()
    if selector is None:
        return "off"
    return _validate_mode(config.LIVE_META_SELECTOR_MODE)


def live_meta_selector_summary() -> str:
    """Human-readable selector summary for startup logs."""
    selector = get_live_meta_selector()
    mode = _validate_mode(config.LIVE_META_SELECTOR_MODE)
    if selector is None:
        if mode != "off" and config.LIVE_META_SELECTOR_BUNDLE:
            return f"meta_selector mode={mode} bundle=unavailable"
        return "meta_selector mode=off"
    return (
        f"meta_selector mode={mode} "
        f"threshold={selector.threshold:.6f} "
        f"bundle={selector.bundle_path.name}"
    )


def resolve_live_signal(
    market: MarketInfo,
    snapshot: MarketSnapshot,
    signals: list[Signal],
) -> SelectorDecision:
    """Choose the single live signal to act on for a market."""
    if not signals:
        return SelectorDecision(
            mode="off",
            actual_signal=None,
            model_signal=None,
            scored_candidates=[],
            threshold=None,
            reason="no_signals",
        )

    fallback_signal = signals[0]
    selector = get_live_meta_selector()
    mode = live_meta_selector_mode()
    if selector is None:
        return SelectorDecision(
            mode="off",
            actual_signal=fallback_signal,
            model_signal=None,
            scored_candidates=[],
            threshold=None,
            reason="selector_disabled",
        )

    model_signal, scored = selector.pick_signal(market, snapshot, signals)
    if model_signal is None:
        if mode == "enforce":
            return SelectorDecision(
                mode=mode,
                actual_signal=None,
                model_signal=None,
                scored_candidates=scored,
                threshold=selector.threshold,
                reason="rejected_by_threshold",
            )
        return SelectorDecision(
            mode=mode,
            actual_signal=fallback_signal,
            model_signal=None,
            scored_candidates=scored,
            threshold=selector.threshold,
            reason="shadow_rejected",
        )

    actual_signal = model_signal if mode == "enforce" else fallback_signal
    return SelectorDecision(
        mode=mode,
        actual_signal=actual_signal,
        model_signal=model_signal,
        scored_candidates=scored,
        threshold=selector.threshold,
        reason="model_selected" if actual_signal is model_signal else "shadow_selected",
    )
