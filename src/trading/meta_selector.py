"""Live meta-selector support for multi-strategy crypto trading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

from analysis.meta_tree import ExpectedPnlTreeRegressor, TabularFeatureEncoder
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
    scored_candidates: pd.DataFrame
    threshold: float | None
    reason: str


class LiveMetaSelector:
    """Load a deployment bundle and score live candidate signals."""

    def __init__(
        self,
        *,
        bundle_path: Path,
        threshold: float,
        encoder: TabularFeatureEncoder,
        model: ExpectedPnlTreeRegressor,
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
            encoder=TabularFeatureEncoder.from_payload(dict(deployment["encoder"])),
            model=ExpectedPnlTreeRegressor.from_payload(dict(deployment["model"])),
            experts=tuple(str(value) for value in payload.get("experts", [])),
        )

    def score_candidates(
        self,
        market: MarketInfo,
        snapshot: MarketSnapshot,
        signals: list[Signal],
    ) -> pd.DataFrame:
        if not signals:
            return pd.DataFrame()

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

        rows: list[dict[str, object]] = []
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

        frame = pd.DataFrame(rows)
        features = self.encoder.transform(frame)
        frame["predicted_pnl"] = self.model.predict(features)
        frame["predicted_positive_rate"] = self.model.predict_positive_rate(features)
        frame["passes_meta_threshold"] = frame["predicted_pnl"] >= self.threshold
        return frame

    def pick_signal(
        self,
        market: MarketInfo,
        snapshot: MarketSnapshot,
        signals: list[Signal],
    ) -> tuple[Signal | None, pd.DataFrame]:
        scored = self.score_candidates(market, snapshot, signals)
        if scored.empty:
            return None, scored

        ranked = scored.sort_values(
            ["passes_meta_threshold", "predicted_pnl", "predicted_positive_rate", "candidate_index"],
            ascending=[False, False, False, True],
            kind="mergesort",
        )
        best_row = ranked.iloc[0]
        if not bool(best_row["passes_meta_threshold"]):
            return None, scored
        return signals[int(best_row["candidate_index"])], scored


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
            scored_candidates=pd.DataFrame(),
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
            scored_candidates=pd.DataFrame(),
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
