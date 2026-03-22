"""Embargoed walk-forward split utilities for signal datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class WalkForwardSplit:
    """A train/validation/embargo/test split defined over market days."""

    split_index: int
    train_days: tuple[str, ...]
    validation_days: tuple[str, ...]
    embargo_days: tuple[str, ...]
    test_days: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "split_index": self.split_index,
            "train_days": list(self.train_days),
            "validation_days": list(self.validation_days),
            "embargo_days": list(self.embargo_days),
            "test_days": list(self.test_days),
        }


def build_embargoed_walkforward_splits(
    df: pd.DataFrame,
    *,
    timestamp_col: str = "started_at",
    train_days: int = 3,
    validation_days: int = 1,
    embargo_days: int = 1,
    test_days: int = 1,
    step_days: int = 1,
) -> list[WalkForwardSplit]:
    """Build rolling day-based splits with an embargo gap before each test block."""
    if df.empty:
        return []
    for value, name in (
        (train_days, "train_days"),
        (validation_days, "validation_days"),
        (embargo_days, "embargo_days"),
        (test_days, "test_days"),
        (step_days, "step_days"),
    ):
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
    if train_days == 0:
        raise ValueError("train_days must be >= 1")
    if validation_days == 0:
        raise ValueError("validation_days must be >= 1")
    if test_days == 0:
        raise ValueError("test_days must be >= 1")
    if step_days == 0:
        raise ValueError("step_days must be >= 1")

    timestamps = pd.to_datetime(df[timestamp_col], utc=True)
    day_labels = timestamps.dt.date.astype(str)
    unique_days = tuple(sorted(day_labels.unique()))
    window = train_days + validation_days + embargo_days + test_days
    if len(unique_days) < window:
        raise ValueError(
            "Not enough distinct market days for the requested walk-forward window: "
            f"need {window}, have {len(unique_days)}."
        )

    splits: list[WalkForwardSplit] = []
    split_index = 1
    max_start = len(unique_days) - window
    for start in range(0, max_start + 1, step_days):
        train_end = start + train_days
        validation_end = train_end + validation_days
        embargo_end = validation_end + embargo_days
        test_end = embargo_end + test_days

        splits.append(
            WalkForwardSplit(
                split_index=split_index,
                train_days=unique_days[start:train_end],
                validation_days=unique_days[train_end:validation_end],
                embargo_days=unique_days[validation_end:embargo_end],
                test_days=unique_days[embargo_end:test_end],
            )
        )
        split_index += 1

    return splits


def apply_walkforward_split(
    df: pd.DataFrame,
    split: WalkForwardSplit,
    *,
    day_col: str = "market_day",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return train/validation/test frames for a split."""
    if day_col not in df.columns:
        raise KeyError(f"Column '{day_col}' not found in DataFrame.")

    train = df[df[day_col].isin(split.train_days)].copy()
    validation = df[df[day_col].isin(split.validation_days)].copy()
    test = df[df[day_col].isin(split.test_days)].copy()
    return train, validation, test
