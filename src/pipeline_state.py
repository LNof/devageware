import json
import os
from pathlib import Path
from typing import Any


def _path() -> Path | None:
    p = os.environ.get("PIPELINE_STATE_PATH")
    return Path(p) if p else None


def in_pipeline() -> bool:
    return _path() is not None


def load() -> dict[str, Any]:
    p = _path()
    if not p or not p.exists():
        return {}
    return json.loads(p.read_text())


def update(**kwargs: Any) -> None:
    p = _path()
    if not p:
        return
    current = load()
    current.update(kwargs)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(current, indent=2))
