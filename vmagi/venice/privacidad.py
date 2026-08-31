"""Integración de privacidad: notrack.ai como proxy HTTP obligatorio."""
from __future__ import annotations

from . import config


class NotrackNoDisponible(RuntimeError):
    """No hay configuración válida de notrack.ai en modo obligatorio."""


class NotrackProvider:
    """Entrega kwargs de httpx para TODO el HTTP del sistema.

    LA SALIDA ES UNA SOLA, Y ESTA CLASE YA NO DECIDE CUAL.
    ======================================================
    Esta clase tenia su propio proxy (`NOTRACK_PROXY`) mientras la puerta
    de Edge tenia el suyo (`/proxy`) y Ritsuko el suyo (`/vpn`). Tres
    puertas para un solo programa es trafico partido: unas peticiones
    salen por la VPN y otras por la linea de casa, y basta una para
    correlacionar las dos rutas — con lo que la VPN deja de servir para
    lo unico que sirve.

    Ahora manda `ritsuko_red`, que gobierna las tres capas. `NOTRACK_PROXY`
    sigue leyendose como una de las fuentes de esa salida unica, asi que
    una configuracion que ya funcionaba sigue funcionando.
    """

    def __init__(self, obligatorio: bool | None = None):
        self.obligatorio = (config.notrack_obligatorio() if obligatorio is None
                            else obligatorio)

    def httpx_kwargs(self) -> dict:
        from vmagi.modules.infrastructure.ritsuko_red import (
            SalidaNoDisponible,
            aplica_a_httpx,
        )
        try:
            kw = aplica_a_httpx()
        except SalidaNoDisponible as e:
            raise NotrackNoDisponible(str(e)) from e
        if kw:
            return kw
        if self.obligatorio:
            raise NotrackNoDisponible(
                "el anonimato esta en modo obligatorio y no hay salida de "
                "red configurada. Fija una con `/vpn socks5://127.0.0.1:9050` "
                "(Tor, gratis) o define NOTRACK_PROXY."
            )
        return {}
