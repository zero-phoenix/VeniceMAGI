"""El nucleo cloud-first de VeniceMAGI: proveedores guest sin key ni login.

Todo lo que aqui vive existe para sostener una sola promesa del manifiesto:
**sin cuenta ni key obligatoria en el camino principal**. La inferencia
sale por la pagina viva de un proveedor guest, operada desde el Edge real
del usuario, y el contenedor virtual local reparte las capacidades entre
los que hay.

    puerta.py      el Edge real, en su hilo propio, uno por sitio
    sitios.py      que sitios guest sabemos operar y como
    cliente.py     escribe el prompt, espera, recoge y limpia
    contenedor.py  quien atiende chat, imagen y video
    racion.py      cuantas llamadas van hoy, y cache para no repetir
    medios.py      el pipeline HQ opcional del modo hybrid
    privacidad.py  proxy HTTP para el trafico compatible
    config.py      modos, rutas y ajustes persistentes
"""
from __future__ import annotations

from .cliente import ChatResp, CupoDiarioAgotado, Venice, VeniceError
from .contenedor import CloudModelContainer, CloudProvider
from .puerta import ModalDeLogin, Puerta, SesionNoDisponible, edge_disponible
from .racion import Racion, estado_global, racion_de
from .sitios import NOTRACK, SITIOS, VENICE, SitioGuest, sitio, sitios_con

__all__ = [
    "ChatResp", "CupoDiarioAgotado", "Venice", "VeniceError",
    "CloudModelContainer", "CloudProvider",
    "ModalDeLogin", "Puerta", "SesionNoDisponible", "edge_disponible",
    "Racion", "estado_global", "racion_de",
    "NOTRACK", "SITIOS", "VENICE", "SitioGuest", "sitio", "sitios_con",
]
