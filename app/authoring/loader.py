from __future__ import annotations

import json
from pathlib import Path

from app.authoring.models import ComboDraft


def parse_combo_draft(payload: object) -> ComboDraft:
    return ComboDraft.from_dict(payload)


def load_combo_draft(path: Path) -> ComboDraft:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid combo draft JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return parse_combo_draft(payload)
