"""CSV structural and row-level validation for the ingestion pipeline.

Each entity file has a required-column schema. Rows missing a required value
are rejected (logged, counted, excluded) rather than raising -- a batch
import should not abort because of a handful of dirty rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger("ingestion.validation")


class SchemaError(Exception):
    """Raised when a CSV file is missing required columns entirely."""


@dataclass
class ValidatedRows:
    records: list[dict[str, Any]]
    rejected_count: int


def load_and_validate(path: str, required_columns: list[str], not_null_columns: list[str]) -> ValidatedRows:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise SchemaError(f"{path}: missing required columns {missing}")

    before = len(df)
    mask = pd.Series(True, index=df.index)
    for col in not_null_columns:
        mask &= df[col].astype(str).str.strip() != ""
    valid_df = df[mask]
    rejected = before - len(valid_df)

    if rejected:
        logger.warning("%s: rejected %d/%d rows missing required fields %s", path, rejected, before, not_null_columns)

    return ValidatedRows(records=valid_df.to_dict("records"), rejected_count=rejected)


def to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
