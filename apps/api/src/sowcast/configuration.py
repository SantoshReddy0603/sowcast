import os
import re
from pathlib import Path


def load_environment(path: Path) -> None:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid environment entry on line {number}")
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Unclosed environment value on line {number}")
            value = value[1:-1]
        if name in values:
            raise ValueError(f"Duplicate environment entry on line {number}")
        values[name] = value
    os.environ.update(values)
