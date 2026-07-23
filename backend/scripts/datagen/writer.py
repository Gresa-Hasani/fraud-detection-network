"""CSV export helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def write_csv(records: list[dict[str, Any]], path: Path, columns: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame.from_records(records, columns=columns)
    df.to_csv(path, index=False)
    return len(df)
