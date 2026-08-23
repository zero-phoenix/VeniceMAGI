"""Integración de privacidad: notrack.ai como proxy HTTP obligatorio."""
from __future__ import annotations

from . import config


class NotrackNoDisponible(RuntimeError):
    """No hay configuración válida de notrack.ai en modo obligatorio."""


class NotrackProvider:
    """Entrega kwargs de httpx con proxy notrack.ai cuando aplica."""

    def __init__(self, obligatorio: bool | None = None):
        self.obligatorio = (config.notrack_obligatorio() if obligatorio is None
                            else obligatorio)

    def httpx_kwargs(self) -> dict:
        proxy = config.notrack_proxy()
        if proxy:
            return {"proxy": proxy}
        if self.obligatorio:
            raise NotrackNoDisponible(
                "notrack.ai es obligatorio pero no está configurado. "
                "Define NOTRACK_PROXY (ej. http://127.0.0.1:8080)."
            )
        return {}
