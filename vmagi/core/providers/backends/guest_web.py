"""Backend de sitios guest: la web viva como proveedor de inferencia.

POR QUE ESTE BACKEND EXISTE
===========================
El resto de backends hablan HTTP contra una API. Los proveedores guest de
VeniceMAGI no tienen API sin clave: Venice mide la atestacion del cliente
y responde 403 a cualquier cosa que no sea un navegador real. Lo que si
funciona es la pagina, operada desde el Edge de la maquina.

Este backend envuelve esa operacion en el mismo contrato que los demas
(`BaseProvider`), de modo que el registro puede repartir familias,
aplicar cortacircuitos y medir latencias sin saber que detras hay un
navegador y no un endpoint.

LA FAMILIA ES EL EJE, Y AQUI NO SE FALSEA
=========================================
`venice` y `notrack` son familias DISTINTAS, y esa distincion es la que
sostiene el debate: si Melchior propone con el mismo modelo con el que
Balthasar refuta, no hay refutacion, hay eco. El registro reparte por
familia; este backend declara la suya y no la disfraza.

LO QUE NO HACE
==============
No abre una ventana por peticion (la puerta es persistente y vive en su
hilo), no rota IP ni perfiles cuando el sitio raciona, y no reintenta
contra un cupo agotado: eso lo dice y para. Ver `venice/racion.py`.
"""
from __future__ import annotations

import asyncio
import logging
import time

from vmagi.venice.cliente import CupoDiarioAgotado, Venice, VeniceError
from vmagi.venice.sitios import SITIOS, SitioGuest

from ..base import (
    BaseProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    Usage,
)

logger = logging.getLogger(__name__)

__all__ = ["GuestWebProvider", "proveedores_guest"]

# NOTA para quien venga a añadir un `proveedor_guest(nombre)` de conveniencia:
# ya existió y se borró en el mismo commit que lo trajo. Nadie lo llamaba, y el
# trinquete de huérfanos lo cazó. Primera regla del proyecto: todo cambio se
# conecta o se borra. Si lo necesitas, `GuestWebProvider(sitio("venice"))` ya
# lo hace en una línea.


def _parte_mensajes(req: CompletionRequest) -> tuple[str, str]:
    """Aplana la conversacion en (sistema, usuario).

    La pagina de un chat guest no acepta una lista de mensajes con roles:
    acepta un texto. Aplanar mal fue un fallo real de la v1 — se mandaba
    solo el ultimo mensaje y el modelo perdia el contrato de su rol, que
    viaja SIEMPRE en el mensaje de sistema.
    """
    sistema = "\n\n".join(str(m.content) for m in req.messages
                          if m.role == "system").strip()
    resto = [m for m in req.messages if m.role != "system"]
    usuario = "\n\n".join(
        (f"[{m.role}] {m.content}" if m.role != "user" else str(m.content))
        for m in resto
    ).strip()
    return sistema, usuario


class GuestWebProvider(BaseProvider):
    """Un sitio guest, presentado como proveedor del registro."""

    supports_tools = False        # la pagina no devuelve tool_calls
    supports_vision = False
    supports_stream = False       # el fallback de BaseProvider basta
    is_local = False

    def __init__(self, sitio: SitioGuest, progreso=None):
        self.sitio = sitio
        self.id = f"{sitio.nombre}-guest"
        self.family = sitio.familia
        self.default_model = f"{sitio.nombre}-guest"
        self._cliente = Venice(progreso=progreso, sitio=sitio)
        self._latencias: list[float] = []

    # ------------------------------------------------------ disponibilidad

    async def available(self) -> bool:
        """Hay Edge en disco. NO lanza el navegador para averiguarlo.

        Comprobarlo abriendo una ventana costaba segundos y parpadeaba en
        pantalla, y cualquier timeout se leia como «no hay Edge». Que la
        puerta ARRANQUE de verdad se comprueba al primer `complete`.
        """
        from vmagi.venice.puerta import edge_disponible
        return edge_disponible()

    def mejor_latencia_ms(self) -> float | None:
        return min(self._latencias) if self._latencias else None

    # -------------------------------------------------------- inferencia

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        empezado = time.monotonic()
        sistema, usuario = _parte_mensajes(req)
        try:
            resp = await asyncio.wait_for(
                self._cliente.chat(sistema, usuario),
                timeout=req.timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise ProviderTimeout(
                f"{self.id}: sin respuesta en {req.timeout_s:.0f}s. La "
                "ventana del Edge sigue abierta; mirala si esto se repite."
            ) from e
        except CupoDiarioAgotado as e:
            # Un cupo agotado NO es un proveedor roto: es un proveedor que
            # hoy no atiende. Se distingue para que el cortacircuitos no lo
            # marque como averiado y lo saque del catalogo manana.
            raise ProviderUnavailable(f"{self.id}: {e}") from e
        except VeniceError as e:
            raise ProviderError(f"{self.id}: {e}") from e

        self._latencias.append(resp.ms)
        del self._latencias[:-50]
        uso = Usage(
            prompt_tokens=self.estimate_tokens(sistema + usuario),
            completion_tokens=self.estimate_tokens(resp.texto),
        )
        return self._mk_response(resp.texto, resp.modelo, empezado, uso)

    async def cerrar(self) -> None:
        await self._cliente.cerrar()

    def estado(self) -> dict:
        return self._cliente.estado()


def proveedores_guest(progreso=None) -> list[GuestWebProvider]:
    """Todos los sitios guest que declaran chat, como proveedores.

    Se construye desde `sitios.py` y no desde una lista propia: una
    segunda lista de proveedores es una lista que se queda vieja, y ya
    paso una vez (el contenedor decia `image=True` de un sitio para el
    que el cliente no tenia ninguna ruta de imagen).
    """
    return [GuestWebProvider(s, progreso=progreso)
            for s in SITIOS.values() if s.chat]
