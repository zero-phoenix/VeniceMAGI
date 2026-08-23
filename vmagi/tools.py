"""Protocolo y ejecutor de herramientas del enjambre.

Las herramientas son REALES: escribir ficheros, ejecutar código y generar
imagen/vídeo en Venice. Balthasar sin run_python sería un crítico de
sillón; Melchior sin write_file, un charlatán.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_BLOQUE = re.compile(r"```tool\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass
class Llamada:
    herramienta: str
    args: dict


@dataclass
class Resultado:
    ok: bool
    salida: str = ""
    ruta: Path | None = None

    def render(self) -> str:
        estado = "OK" if self.ok else "FALLO"
        extra = f" · {self.ruta}" if self.ruta else ""
        return f"[{estado}{extra}]\n{self.salida}".strip()


def parsea_herramientas(texto: str) -> list[Llamada]:
    """Extrae los bloques ```tool``` de una respuesta del modelo."""
    out: list[Llamada] = []
    for m in _BLOQUE.finditer(texto or ""):
        try:
            d = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        h = d.get("herramienta") or d.get("tool")
        args = d.get("args") or d.get("arguments") or {}
        if isinstance(h, str) and isinstance(args, dict):
            out.append(Llamada(h, args))
    return out


class Ejecutor:
    """Ejecuta llamadas contra el workspace y la API de Venice."""

    def __init__(self, venice, workspace: Path):
        self.venice = venice
        self.ws = workspace

    def _segura(self, ruta: str) -> Path:
        """Ruta dentro del workspace: sin escapar hacia arriba."""
        p = (self.ws / ruta).resolve()
        if self.ws.resolve() not in p.parents and p != self.ws.resolve():
            raise ValueError(f"ruta fuera del workspace: {ruta}")
        return p

    async def ejecuta(self, l: Llamada) -> Resultado:
        try:
            f = getattr(self, f"_{l.herramienta}", None)
            if f is None or l.herramienta.startswith("_"):
                return Resultado(False, salida=f"herramienta desconocida: "
                                               f"{l.herramienta}")
            return await f(**l.args)
        except TypeError as e:
            return Resultado(False, salida=f"argumentos inválidos: {e}")
        except Exception as e:                          # noqa: BLE001
            return Resultado(False, salida=f"{type(e).__name__}: {e}")

    # ------------------------------------------------------ herramientas

    async def _write_file(self, ruta: str = "", contenido: str = "") \
            -> Resultado:
        if not ruta:
            return Resultado(False, salida="write_file sin ruta")
        p = self._segura(ruta)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenido, encoding="utf-8")
        return Resultado(True, salida=f"{len(contenido)} caracteres",
                         ruta=p)

    async def _run_python(self, codigo: str = "") -> Resultado:
        if not codigo.strip():
            return Resultado(False, salida="run_python sin código")
        p = subprocess.run(
            [sys.executable, "-I", "-c", codigo],
            capture_output=True, text=True, timeout=15, cwd=str(self.ws))
        cuerpo = (p.stdout or "") + (("\n[stderr]\n" + p.stderr)
                                     if p.stderr else "")
        return Resultado(p.returncode == 0,
                         salida=cuerpo.strip() or "(sin salida)")

    async def _generate_image(self, prompt: str = "",
                              refs: list[str] | None = None,
                              aspect_ratio: str = "16:9",
                              seed: int | None = None) -> Resultado:
        if not prompt:
            return Resultado(False, salida="generate_image sin prompt")
        rutas = [self._segura(r) for r in (refs or [])]
        ruta = await self.venice.imagen(
            prompt, refs=rutas if rutas else None,
            aspect_ratio=aspect_ratio, seed=seed)
        return Resultado(True, salida=f"imagen generada", ruta=ruta)

    async def _generate_video(self, prompt: str = "",
                              duration: str = "10s",
                              refs_urls: list[str] | None = None) \
            -> Resultado:
        if not prompt:
            return Resultado(False, salida="generate_video sin prompt")
        ruta = await self.venice.video(prompt, duration=duration,
                                       ref_urls=refs_urls)
        return Resultado(True, salida="vídeo generado", ruta=ruta)


@dataclass
class Traza:
    """Lo que hizo una ronda, para el historial y para Balthasar."""
    eventos: list[str] = field(default_factory=list)

    def anota(self, quien: str, que: str) -> None:
        self.eventos.append(f"{quien}: {que}")
