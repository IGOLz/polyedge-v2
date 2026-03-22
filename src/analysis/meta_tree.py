"""Lightweight tabular feature encoding and in-repo expected-PnL tree model."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd

from analysis.accelerators.base import compute_metrics_from_arrays

DEFAULT_CATEGORY_COLUMNS = ("strategy_id", "asset", "direction")
LABEL_COLUMNS = {
    "actual_result",
    "entry_fee_usdc",
    "exit_fee_usdc",
    "exit_reason",
    "expert_config_source",
    "market_day",
    "market_id",
    "market_type",
    "realized_gross_pnl",
    "realized_is_win",
    "realized_pnl",
    "started_at",
    "strategy_name",
}


def default_feature_columns(
    df: pd.DataFrame,
    *,
    category_columns: tuple[str, ...] = DEFAULT_CATEGORY_COLUMNS,
) -> tuple[list[str], list[str]]:
    """Return numeric and categorical feature columns for the selector."""
    categories = [column for column in category_columns if column in df.columns]
    numeric = [
        column
        for column in df.columns
        if column not in LABEL_COLUMNS
        and column not in categories
        and pd.api.types.is_numeric_dtype(df[column])
    ]
    return sorted(numeric), categories


@dataclass
class TabularFeatureEncoder:
    """Median-impute numeric columns and one-hot encode low-cardinality categories."""

    numeric_columns: list[str] | None = None
    category_columns: list[str] | None = None
    fill_values_: dict[str, float] | None = None
    dummy_columns_: list[str] | None = None
    feature_names_: list[str] | None = None

    def fit(self, df: pd.DataFrame) -> "TabularFeatureEncoder":
        if self.numeric_columns is None or self.category_columns is None:
            numeric, categories = default_feature_columns(df)
            if self.numeric_columns is None:
                self.numeric_columns = numeric
            if self.category_columns is None:
                self.category_columns = categories

        numeric_frame = df[self.numeric_columns].apply(pd.to_numeric, errors="coerce")
        fill_values: dict[str, float] = {}
        for column in self.numeric_columns:
            median = numeric_frame[column].median()
            fill_values[column] = float(median) if pd.notna(median) else 0.0

        category_frame = self._category_frame(df)
        dummies = pd.get_dummies(category_frame, prefix=self.category_columns, dtype=float)

        self.fill_values_ = fill_values
        self.dummy_columns_ = list(dummies.columns)
        self.feature_names_ = list(self.numeric_columns) + list(self.dummy_columns_)
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if self.fill_values_ is None or self.dummy_columns_ is None:
            raise RuntimeError("Encoder must be fit before transform().")

        numeric_frame = (
            df[self.numeric_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(self.fill_values_)
            .astype(float)
        )
        category_frame = self._category_frame(df)
        dummies = pd.get_dummies(category_frame, prefix=self.category_columns, dtype=float)
        dummies = dummies.reindex(columns=self.dummy_columns_, fill_value=0.0)
        frame = pd.concat([numeric_frame, dummies], axis=1)
        return frame.to_numpy(dtype=float, copy=False)

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        self.fit(df)
        return self.transform(df)

    def to_payload(self) -> dict[str, Any]:
        """Serialize the fitted encoder for deployment."""
        if self.fill_values_ is None or self.dummy_columns_ is None:
            raise RuntimeError("Encoder must be fit before to_payload().")
        return {
            "numeric_columns": list(self.numeric_columns or []),
            "category_columns": list(self.category_columns or []),
            "fill_values": dict(self.fill_values_),
            "dummy_columns": list(self.dummy_columns_),
            "feature_names": list(self.feature_names_ or []),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TabularFeatureEncoder":
        """Restore a fitted encoder from a serialized payload."""
        encoder = cls(
            numeric_columns=list(payload.get("numeric_columns", [])),
            category_columns=list(payload.get("category_columns", [])),
        )
        encoder.fill_values_ = {
            str(key): float(value)
            for key, value in dict(payload.get("fill_values", {})).items()
        }
        encoder.dummy_columns_ = list(payload.get("dummy_columns", []))
        encoder.feature_names_ = list(payload.get("feature_names", []))
        return encoder

    def _category_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.category_columns:
            return pd.DataFrame(index=df.index)
        return df[self.category_columns].fillna("unknown").astype(str)


@dataclass
class TreeNode:
    """A simple regression tree node predicting expected PnL."""

    prediction: float
    positive_rate: float
    sample_count: int
    feature_index: int | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None

    @property
    def is_leaf(self) -> bool:
        return self.feature_index is None


class ExpectedPnlTreeRegressor:
    """A depth-limited CART-style regressor trained on realized PnL."""

    def __init__(
        self,
        *,
        max_depth: int = 3,
        min_samples_leaf: int = 25,
        max_candidate_splits: int = 16,
        min_gain: float = 1e-6,
    ) -> None:
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_candidate_splits = max_candidate_splits
        self.min_gain = min_gain
        self.root_: TreeNode | None = None
        self.n_features_in_: int | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ExpectedPnlTreeRegressor":
        if X.ndim != 2:
            raise ValueError("X must be a 2D array.")
        if y.ndim != 1:
            raise ValueError("y must be a 1D array.")
        if len(X) != len(y):
            raise ValueError("X and y must contain the same number of rows.")
        if len(y) == 0:
            raise ValueError("Cannot fit on an empty dataset.")

        self.n_features_in_ = X.shape[1]
        self.root_ = self._build_node(X.astype(float, copy=False), y.astype(float, copy=False), depth=0)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.root_ is None:
            raise RuntimeError("Model must be fit before predict().")
        return np.array([self._predict_row(self.root_, row)[0] for row in X], dtype=float)

    def predict_positive_rate(self, X: np.ndarray) -> np.ndarray:
        if self.root_ is None:
            raise RuntimeError("Model must be fit before predict_positive_rate().")
        return np.array([self._predict_row(self.root_, row)[1] for row in X], dtype=float)

    def to_dict(self, feature_names: list[str] | None = None) -> dict[str, Any]:
        if self.root_ is None:
            raise RuntimeError("Model must be fit before to_dict().")
        return self._node_to_dict(self.root_, feature_names=feature_names)

    def to_payload(self, feature_names: list[str] | None = None) -> dict[str, Any]:
        """Serialize the fitted model for deployment."""
        if self.root_ is None:
            raise RuntimeError("Model must be fit before to_payload().")
        return {
            "max_depth": self.max_depth,
            "min_samples_leaf": self.min_samples_leaf,
            "max_candidate_splits": self.max_candidate_splits,
            "min_gain": self.min_gain,
            "n_features_in": self.n_features_in_,
            "tree": self.to_dict(feature_names=feature_names),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ExpectedPnlTreeRegressor":
        """Restore a fitted model from a serialized payload."""
        model = cls(
            max_depth=int(payload.get("max_depth", 3)),
            min_samples_leaf=int(payload.get("min_samples_leaf", 25)),
            max_candidate_splits=int(payload.get("max_candidate_splits", 16)),
            min_gain=float(payload.get("min_gain", 1e-6)),
        )
        model.n_features_in_ = int(payload.get("n_features_in", 0) or 0)
        model.root_ = model._node_from_dict(dict(payload["tree"]))
        return model

    def _build_node(self, X: np.ndarray, y: np.ndarray, *, depth: int) -> TreeNode:
        prediction = float(np.mean(y))
        positive_rate = float(np.mean(y > 0.0))
        node = TreeNode(
            prediction=prediction,
            positive_rate=positive_rate,
            sample_count=len(y),
        )

        if (
            depth >= self.max_depth
            or len(y) < max(self.min_samples_leaf * 2, 2)
            or np.allclose(y, y[0])
        ):
            return node

        feature_index, threshold, gain = self._best_split(X, y)
        if feature_index is None or threshold is None or gain < self.min_gain:
            return node

        left_mask = X[:, feature_index] <= threshold
        right_mask = ~left_mask
        if left_mask.sum() < self.min_samples_leaf or right_mask.sum() < self.min_samples_leaf:
            return node

        node.feature_index = feature_index
        node.threshold = float(threshold)
        node.left = self._build_node(X[left_mask], y[left_mask], depth=depth + 1)
        node.right = self._build_node(X[right_mask], y[right_mask], depth=depth + 1)
        return node

    def _best_split(self, X: np.ndarray, y: np.ndarray) -> tuple[int | None, float | None, float]:
        parent_sse = self._sum_squared_error(y)
        best_feature: int | None = None
        best_threshold: float | None = None
        best_gain = 0.0

        for feature_index in range(X.shape[1]):
            thresholds = self._candidate_thresholds(X[:, feature_index])
            if thresholds.size == 0:
                continue

            column = X[:, feature_index]
            for threshold in thresholds:
                left_mask = column <= threshold
                right_mask = ~left_mask
                if (
                    left_mask.sum() < self.min_samples_leaf
                    or right_mask.sum() < self.min_samples_leaf
                ):
                    continue
                child_sse = self._sum_squared_error(y[left_mask]) + self._sum_squared_error(y[right_mask])
                gain = parent_sse - child_sse
                if gain > best_gain:
                    best_feature = feature_index
                    best_threshold = float(threshold)
                    best_gain = float(gain)

        return best_feature, best_threshold, best_gain

    def _candidate_thresholds(self, column: np.ndarray) -> np.ndarray:
        unique = np.unique(column)
        if unique.size <= 1:
            return np.array([], dtype=float)
        if unique.size <= self.max_candidate_splits:
            return ((unique[:-1] + unique[1:]) / 2.0).astype(float)

        quantiles = np.linspace(0.05, 0.95, self.max_candidate_splits)
        values = np.quantile(unique, quantiles)
        return np.unique(values.astype(float))

    @staticmethod
    def _sum_squared_error(values: np.ndarray) -> float:
        if values.size == 0:
            return 0.0
        mean_value = float(np.mean(values))
        return float(np.sum((values - mean_value) ** 2))

    def _predict_row(self, node: TreeNode, row: np.ndarray) -> tuple[float, float]:
        current = node
        while not current.is_leaf:
            assert current.feature_index is not None
            assert current.threshold is not None
            if row[current.feature_index] <= current.threshold:
                assert current.left is not None
                current = current.left
            else:
                assert current.right is not None
                current = current.right
        return current.prediction, current.positive_rate

    def _node_to_dict(
        self,
        node: TreeNode,
        *,
        feature_names: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "prediction": round(node.prediction, 6),
            "positive_rate": round(node.positive_rate, 6),
            "sample_count": node.sample_count,
        }
        if node.is_leaf:
            payload["type"] = "leaf"
            return payload

        assert node.feature_index is not None
        assert node.threshold is not None
        payload["type"] = "split"
        payload["feature_index"] = node.feature_index
        payload["feature_name"] = (
            feature_names[node.feature_index]
            if feature_names is not None and node.feature_index < len(feature_names)
            else f"feature_{node.feature_index}"
        )
        payload["threshold"] = round(node.threshold, 6)
        payload["left"] = self._node_to_dict(node.left, feature_names=feature_names)
        payload["right"] = self._node_to_dict(node.right, feature_names=feature_names)
        return payload

    def _node_from_dict(self, payload: dict[str, Any]) -> TreeNode:
        node = TreeNode(
            prediction=float(payload["prediction"]),
            positive_rate=float(payload["positive_rate"]),
            sample_count=int(payload["sample_count"]),
        )
        if payload.get("type") == "leaf":
            return node

        node.feature_index = int(payload["feature_index"])
        node.threshold = float(payload["threshold"])
        node.left = self._node_from_dict(dict(payload["left"]))
        node.right = self._node_from_dict(dict(payload["right"]))
        return node


def compute_signal_metrics(
    df: pd.DataFrame,
    *,
    config_id: str = "selector",
) -> dict[str, Any]:
    """Compute backtest-like metrics directly from opportunity rows."""
    if df.empty:
        metrics = compute_metrics_from_arrays(
            np.array([], dtype=float),
            np.array([], dtype=float),
            np.array([], dtype=float),
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int64),
            config_id=config_id,
        )
        metrics["selected_markets"] = 0
        return metrics

    asset_codes = pd.Categorical(df["asset"].astype(str)).codes.astype(np.int64, copy=False)
    durations = df["duration_minutes"].astype(int).to_numpy(dtype=np.int64, copy=False)
    metrics = compute_metrics_from_arrays(
        df["realized_pnl"].to_numpy(dtype=float, copy=False),
        df["entry_fee_usdc"].to_numpy(dtype=float, copy=False),
        df["exit_fee_usdc"].to_numpy(dtype=float, copy=False),
        asset_codes,
        durations,
        config_id=config_id,
    )
    metrics["selected_markets"] = int(df["market_id"].nunique())
    return metrics


def apply_selection_policy(
    df: pd.DataFrame,
    *,
    threshold: float,
    min_threshold: float = 0.0,
    top_k_per_day: int | None = None,
    top_percent_per_day: float | None = None,
    day_col: str = "market_day",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply threshold and optional per-day caps to model predictions."""
    if "predicted_pnl" not in df.columns:
        raise KeyError("DataFrame must contain a 'predicted_pnl' column.")
    if top_k_per_day is not None and top_k_per_day < 1:
        raise ValueError("top_k_per_day must be >= 1 when provided.")
    if top_percent_per_day is not None and not (0.0 < top_percent_per_day <= 1.0):
        raise ValueError("top_percent_per_day must be in (0, 1].")
    if (top_k_per_day is not None or top_percent_per_day is not None) and day_col not in df.columns:
        raise KeyError(f"DataFrame must contain '{day_col}' when per-day caps are used.")

    effective_threshold = max(float(threshold), float(min_threshold))
    candidates = df[df["predicted_pnl"] >= effective_threshold].copy()
    policy_summary = {
        "raw_threshold": float(threshold),
        "effective_threshold": effective_threshold,
        "rows_before_policy": int(len(df)),
        "rows_after_threshold": int(len(candidates)),
        "top_k_per_day": top_k_per_day,
        "top_percent_per_day": top_percent_per_day,
    }
    if candidates.empty:
        policy_summary["rows_after_policy"] = 0
        return candidates, policy_summary

    if top_k_per_day is None and top_percent_per_day is None:
        policy_summary["rows_after_policy"] = int(len(candidates))
        return candidates, policy_summary

    sort_cols = ["predicted_pnl"]
    ascending = [False]
    if "predicted_positive_rate" in candidates.columns:
        sort_cols.append("predicted_positive_rate")
        ascending.append(False)
    sort_cols.extend([day_col, "market_id"])
    ascending.extend([True, True])
    ordered = candidates.sort_values(sort_cols, ascending=ascending, kind="mergesort")

    selected_frames: list[pd.DataFrame] = []
    for _, group in ordered.groupby(day_col, sort=False):
        keep_count = len(group)
        if top_percent_per_day is not None:
            keep_count = min(keep_count, max(1, math.ceil(len(group) * top_percent_per_day)))
        if top_k_per_day is not None:
            keep_count = min(keep_count, top_k_per_day)
        selected_frames.append(group.head(keep_count))

    selected = pd.concat(selected_frames).sort_index() if selected_frames else candidates.iloc[0:0].copy()
    policy_summary["rows_after_policy"] = int(len(selected))
    return selected, policy_summary


def threshold_candidates(
    predictions: np.ndarray,
    *,
    min_threshold: float = 0.0,
) -> list[float]:
    if predictions.size == 0:
        return [float(min_threshold)]
    quantiles = np.linspace(0.0, 0.95, 20)
    candidates = {float(np.quantile(predictions, quantile)) for quantile in quantiles}
    candidates.add(float(min_threshold))
    return sorted(candidate for candidate in candidates if candidate >= float(min_threshold))


def choose_prediction_threshold(
    df: pd.DataFrame,
    predictions: np.ndarray,
    *,
    min_trades: int = 25,
    min_threshold: float = 0.0,
    top_k_per_day: int | None = None,
    top_percent_per_day: float | None = None,
) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    """Choose a prediction threshold on a validation block."""
    if len(df) != len(predictions):
        raise ValueError("df and predictions must have the same number of rows.")

    policy_df = df.copy()
    policy_df["predicted_pnl"] = predictions

    leaderboard: list[dict[str, Any]] = []
    best_threshold = float(min_threshold)
    best_metrics = compute_signal_metrics(df.iloc[0:0], config_id="threshold_search_empty")
    best_score: tuple[float, ...] | None = None

    for threshold in threshold_candidates(predictions, min_threshold=min_threshold):
        selected, policy_summary = apply_selection_policy(
            policy_df,
            threshold=threshold,
            min_threshold=min_threshold,
            top_k_per_day=top_k_per_day,
            top_percent_per_day=top_percent_per_day,
        )
        metrics = compute_signal_metrics(selected, config_id=f"threshold_{threshold:.6f}")
        metrics["threshold"] = threshold
        metrics["effective_threshold"] = policy_summary["effective_threshold"]
        metrics["rows_after_threshold"] = policy_summary["rows_after_threshold"]
        metrics["rows_after_policy"] = policy_summary["rows_after_policy"]
        leaderboard.append(metrics)

        meets_min_trades = metrics["total_bets"] >= min_trades
        score = (
            1.0 if meets_min_trades else 0.0,
            float(metrics["total_pnl"]),
            float(metrics["profit_factor"]),
            float(metrics["sharpe_ratio"]),
            -float(metrics["max_drawdown"]),
            -float(metrics["total_bets"]),
            float(threshold),
        )
        if best_score is None or score > best_score:
            best_threshold = threshold
            best_metrics = metrics
            best_score = score

    leaderboard.sort(
        key=lambda item: (
            item["total_pnl"],
            item["profit_factor"],
            item["sharpe_ratio"],
            -item["max_drawdown"],
            item["total_bets"],
        ),
        reverse=True,
    )
    return best_threshold, best_metrics, leaderboard
