"""Naoko: supervisión y errores explicados en español."""
from __future__ import annotations

from . import config, sesion
from .media_pipeline import BackendImagenError, VideoSeedanceError
from .venice import CupoDiarioAgotado, VeniceError


def estado_legible() -> str:
    edge = ("disponible" if sesion.edge_disponible()
            else "NO ENCONTRADO (instala Edge: es la puerta sin cuenta)")
    lineas = [
        "modo: Venice Guest — sin cuenta, sin clave",
        f"puerta: Edge real con ventana visible ({edge})",
        f"perfil: {sesion.perfil_dir()}",
        f"datos: {config.data_dir()}",
        "cupo: el que Venice dé al Guest cada día (por IP)",
        f"proxy propio: {config.proxy() or '(ninguno: /proxy URL para usar tu VPN)'}",
    ]
    return "\n".join(lineas)


def explica_error(e: Exception) -> str:
    if isinstance(e, CupoDiarioAgotado):
        return (str(e)
                + "\n\nMientras tanto, el enjambre no puede hablar con "
                  "Venice hasta mañana. El resto (ficheros, ejecutar "
                  "código) sigue funcionando.")
    if isinstance(e, VeniceError):
        return str(e)
    if isinstance(e, (BackendImagenError, VideoSeedanceError)):
        return str(e)
    if isinstance(e, sesion.SesionNoDisponible):
        return ("La puerta no abrió: " + str(e)
                + "\nLa sesión Guest se emite en un Edge real; revisa la "
                  "ventana si quedó algo a medias.")
    return f"{type(e).__name__}: {e}"
