"""El contenedor virtual local: orquesta capacidades cloud guest.

QUE ES Y QUE NO ES
==================
No es un contenedor de Docker ni una maquina virtual. Es la pieza que, en
modo `cloud`, decide QUE proveedor guest atiende cada capacidad (chat,
imagen, video) sin que exista inferencia local de por medio. El nombre
viene del manifiesto de VeniceMAGI: «arquitectura de contenedor virtual
local para orquestar capacidades».

Su valor esta en lo que declara. Un proveedor que no hace video figura
aqui con `video=False`, y pedirselo devuelve un error que dice el motivo
y el nombre del proveedor — en vez de intentarlo, esperar cuatro minutos
y contestar «no apareci en el plazo», que fue lo que hacia la v1.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sitios import SITIOS, SitioGuest


@dataclass(frozen=True)
class CloudProvider:
    nombre: str
    chat: bool
    image: bool
    video: bool

    @classmethod
    def desde_sitio(cls, s: SitioGuest) -> "CloudProvider":
        return cls(nombre=f"{s.nombre}-guest-free", chat=s.chat,
                   image=s.imagen, video=s.video)


class CloudModelContainer:
    """Orquesta capacidades cloud sin inferencia local real."""

    def __init__(self, venice):
        self._venice = venice
        #: La lista sale de `sitios.py`, no de constantes duplicadas. En la
        #: v1 el contenedor traia su propia copia de las capacidades de
        #: Venice y ya discrepaba del cliente: decia `image=True` mientras
        #: el cliente no tenia ninguna ruta de imagen guest conectada.
        self._providers = [CloudProvider.desde_sitio(s)
                           for s in SITIOS.values()]

    # ------------------------------------------------------ inventario

    def proveedores(self) -> list[CloudProvider]:
        return list(self._providers)

    def proveedor_activo(self) -> CloudProvider:
        """El que atiende el chat. El primero que lo declare."""
        propio = getattr(self._venice, "sitio", None)
        if propio is not None:
            for p in self._providers:
                if p.nombre.startswith(propio.nombre) and p.chat:
                    return p
        for p in self._providers:
            if p.chat:
                return p
        return self._providers[0]

    def proveedor_para(self, capacidad: str) -> CloudProvider | None:
        """Quien puede con esta capacidad, o None. None es una respuesta."""
        campo = {"chat": "chat", "imagen": "image", "image": "image",
                 "video": "video"}.get(capacidad)
        if campo is None:
            return None
        return next((p for p in self._providers if getattr(p, campo)), None)

    def etiqueta_container(self) -> str:
        p = self.proveedor_activo()
        return f"cloud-virtual:{p.nombre}"

    def inventario(self) -> list[dict]:
        """Para `/salud` y la GUI: quien hay y que sabe hacer cada uno."""
        return [{"proveedor": p.nombre,
                 "capacidades": [n for n, v in (("chat", p.chat),
                                                ("imagen", p.image),
                                                ("video", p.video)) if v]}
                for p in self._providers]

    # ----------------------------------------------------- capacidades

    async def imagen(self, prompt: str, *, aspect_ratio: str,
                     seed: int | None) -> Path:
        p = self.proveedor_para("imagen")
        if p is None:
            raise RuntimeError(
                "Ningun proveedor guest del contenedor declara imagen. "
                "Con `/modo hybrid` entran los backends locales "
                "(automatic1111/comfyui).")
        return await self._venice._imagen_guest(
            prompt, aspect_ratio=aspect_ratio, seed=seed)

    async def video(self, *_args, **_kwargs) -> Path:
        p = self.proveedor_para("video")
        if p is None:
            raise self._venice._error_video_cloud_only()
        raise self._venice._error_video_cloud_only()
