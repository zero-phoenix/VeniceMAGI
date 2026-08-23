"""Contenedor virtual local para proveedores cloud guest (sin key/login)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CloudProvider:
    nombre: str
    chat: bool
    image: bool
    video: bool


class CloudModelContainer:
    """Orquesta capacidades cloud sin inferencia local real."""

    def __init__(self, venice):
        self._venice = venice
        self._providers = [
            CloudProvider("venice-guest-free", chat=True, image=True, video=False),
        ]

    def proveedor_activo(self) -> CloudProvider:
        # Lista blanca simple; preparado para más proveedores guest.
        for p in self._providers:
            if p.chat:
                return p
        return self._providers[0]

    def etiqueta_container(self) -> str:
        p = self.proveedor_activo()
        return f"cloud-virtual:{p.nombre}"

    async def imagen(self, prompt: str, *, aspect_ratio: str, seed: int | None) -> Path:
        _ = self.proveedor_activo()
        return await self._venice._imagen_guest(prompt, aspect_ratio=aspect_ratio, seed=seed)

    async def video(self, *_args, **_kwargs) -> Path:
        raise self._venice._error_video_cloud_only()
