"""El kernel de VeniceMAGI v2: cola de trabajo, eventos y aprobaciones.

El REPL mandaba una petición y esperaba; una IDE encola, muestra el
progreso en vivo y pide permiso cuando el enjambre quiere tocar la shell.
Todo lo que la GUI ve pasa por aquí: los eventos son la única fuente.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..venice import config
from .orchestrator import Orquestador
from .store import Historial
from ..venice.cliente import Venice


@dataclass
class Aprobacion:
    id: str
    cmd: str
    futuro: asyncio.Future = field(default_factory=lambda:
                                   asyncio.get_event_loop()
                                   .create_future())


class Kernel:
    def __init__(self, venice: Venice, historial: Historial):
        self.v = venice
        self.hist = historial
        self.orch = Orquestador(venice, config.workspace())
        #: eventos para la GUI: lista acotada, ids crecientes.
        self.eventos: list[dict] = []
        self._id = itertools.count(1)
        self._lock = asyncio.Lock()
        #: aprobaciones de shell pendientes (id → Aprobacion)
        self.aprobaciones: dict[str, Aprobacion] = {}
        #: cola de peticiones del usuario
        self.cola: asyncio.Queue[str] = asyncio.Queue()
        #: contadores de hoy (ración vista desde fuera)
        self.hoy = time.strftime("%Y-%m-%d")
        self.llamadas_hoy = 0
        self._trabajando = False

    # ------------------------------------------------------------ eventos

    def emite(self, tipo: str, **datos) -> None:
        self.eventos.append({"id": next(self._id), "ts": time.time(),
                             "tipo": tipo, **datos})
        if len(self.eventos) > 500:
            del self.eventos[:250]

    def eventos_desde(self, desde_id: int) -> list[dict]:
        return [e for e in self.eventos if e["id"] > desde_id]

    # -------------------------------------------------------- aprobaciones

    async def pide_aprobacion(self, cmd: str, plazo_s: float = 120.0) -> bool:
        """El enjambre quiere ejecutar un comando de shell. ¿Le dejas?"""
        aid = f"ap{next(self._id)}"
        ap = Aprobacion(aid, cmd)
        self.aprobaciones[aid] = ap
        self.emite("aprobacion_pedida", id=aid, cmd=cmd)
        try:
            return await asyncio.wait_for(ap.futuro, timeout=plazo_s)
        except asyncio.TimeoutError:
            self.emite("aprobacion_expirada", id=aid, cmd=cmd)
            return False
        finally:
            self.aprobaciones.pop(aid, None)

    def resuelve_aprobacion(self, aid: str, ok: bool,
                            loop: asyncio.AbstractEventLoop) -> bool:
        ap = self.aprobaciones.get(aid)
        if ap is None or ap.futuro.done():
            return False
        loop.call_soon_threadsafe(ap.futuro.set_result, ok)
        self.emite("aprobacion_resuelta", id=aid, ok=ok)
        return True

    # ------------------------------------------------------------- trabajo

    @property
    def trabajando(self) -> bool:
        return self._trabajando

    async def procesa_cola(self) -> None:
        """El trabajador: una petición cada vez, en orden, con eventos."""
        while True:
            texto = await self.cola.get()
            self._trabajando = True
            self.emite("ronda_empieza", peticion=texto[:200])
            try:
                await self.ronda(texto)
            except Exception as e:                        # noqa: BLE001
                from . import naoko
                self.emite("ronda_error", mensaje=naoko.explica_error(e))
            finally:
                self._trabajando = False
                self.cola.task_done()

    async def ronda(self, texto: str):
        if texto.startswith("/imagen "):
            prompt = texto[len("/imagen "):]
            self.emite("estado", mensaje="generando imagen…")
            ruta = await self.v.imagen(prompt)
            self.hist.anota(texto, f"imagen: {ruta}", [str(ruta)])
            self.emite("medio_nuevo", ruta=str(ruta), tipo="imagen")
            return
        if texto.startswith("/video_planos "):
            from .tools import Ejecutor
            self.emite("estado", mensaje="componiendo vídeo de planos…")
            ej = Ejecutor(self.v, config.workspace(), kernel=self)
            r = await ej._video_planos(**_args_video(texto[14:]))
            self.emite("medio_nuevo", ruta=str(r.ruta), tipo="video")
            return
        r = await self.orch.ronda(texto)
        self.hist.anota(texto, r.sintesis, r.artefactos)
        self.emite("ronda_fin",
                   tesis=r.tesis[:4000], antitesis=r.antitesis[:4000],
                   sintesis=r.sintesis[:8000], nota=r.nota_naoko,
                   artefactos=r.artefactos)

    def cuenta_llamada(self) -> None:
        hoy = time.strftime("%Y-%m-%d")
        if hoy != self.hoy:
            self.hoy = hoy
            self.llamadas_hoy = 0
        self.llamadas_hoy += 1


def _args_video(texto: str) -> dict:
    """'/video_planos p1 | p2 | p3' → {planos:[...]}.

    Sintaxis simple y visible en la GUI: los planos se separan por | y
    cada uno es un prompt de imagen.
    """
    planos = [p.strip() for p in texto.split("|") if p.strip()]
    return {"planos": planos or [texto.strip()]}
