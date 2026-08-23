"""Logging estructurado y correlación por ronda."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


class EventLogger:
    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex[:16]

    def emit(self, *, level: str, code: str, trace_id: str,
             message: str, extra: dict | None = None) -> None:
        e = {
            "ts": time.time(),
            "level": level,
            "code": code,
            "trace_id": trace_id,
            "message": message,
            "extra": extra or {},
        }
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
