from datetime import UTC, datetime
from typing import Any

from sowcast.sources.models import Series


def parse_series(payload: dict[str, Any], key: str, expected: dict[str, str]) -> Series:
    block = payload[key]
    units = payload[f"{key}_units"]
    if not isinstance(block, dict) or not isinstance(units, dict):
        raise ValueError("Invalid weather series structure")
    if any(units.get(variable) != unit for variable, unit in expected.items()):
        raise ValueError("Unexpected source units")
    return Series(
        time=tuple(datetime.fromtimestamp(t, UTC) for t in block["time"]),
        values={variable: block[variable] for variable in expected},
        units=expected,
    )
