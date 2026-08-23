"""Contratos de capacidades para desacoplar orquestación de implementaciones."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class IChatProvider(Protocol):
    async def chat(self, sistema: str, usuario: str, **kwargs):
        ...

    async def modelos(self) -> list[str]:
        ...

    async def cerrar(self) -> None:
        ...


class IImageProvider(Protocol):
    async def imagen(self, prompt: str, **kwargs) -> Path:
        ...


class IVideoProvider(Protocol):
    async def video(self, prompt: str, **kwargs) -> Path:
        ...


class IPrivacyProvider(Protocol):
    def httpx_kwargs(self) -> dict:
        ...
