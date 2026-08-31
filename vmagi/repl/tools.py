"""Protocolo y ejecutor de herramientas del enjambre (v2: IDE de verdad).

Las herramientas son el hardware del usuario hecho visible: ficheros con
papelera y journal, parches quirúrgicos, ejecución con plazo, hardware
real, shell SOLO con aprobación en la GUI, y el vídeo de planos compuesto
en el PC con ffmpeg.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..venice import config

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


@dataclass
class Traza:
    eventos: list[str] = field(default_factory=list)

    def anota(self, quien: str, que: str) -> None:
        self.eventos.append(f"{quien}: {que}")


def parsea_herramientas(texto: str) -> list[Llamada]:
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


def _journal(anota: dict) -> None:
    """Diario solo-añadir de lo que toca el enjambre en tu disco."""
    with config.journal_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **anota},
                           ensure_ascii=False) + "\n")


class Ejecutor:
    def __init__(self, venice, workspace: Path, kernel=None):
        self.venice = venice
        self.ws = workspace
        self.kernel = kernel            # para pedir aprobación de shell

    def _segura(self, ruta: str) -> Path:
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

    # ------------------------------------------------------ ficheros

    async def _write_file(self, ruta: str = "", contenido: str = "") \
            -> Resultado:
        if not ruta:
            return Resultado(False, salida="write_file sin ruta")
        p = self._segura(ruta)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenido, encoding="utf-8")
        _journal({"accion": "write", "ruta": str(p),
                  "bytes": len(contenido.encode("utf-8"))})
        return Resultado(True, salida=f"{len(contenido)} caracteres",
                         ruta=p)

    async def _read_file(self, ruta: str = "", max_bytes: int = 65536) \
            -> Resultado:
        if not ruta:
            return Resultado(False, salida="read_file sin ruta")
        p = self._segura(ruta)
        if not p.exists():
            return Resultado(False, salida=f"no existe: {ruta}")
        b = p.read_bytes()[:max_bytes]
        return Resultado(True, salida=b.decode("utf-8", errors="replace"),
                         ruta=p)

    async def _list_dir(self, ruta: str = ".") -> Resultado:
        p = self._segura(ruta)
        if not p.is_dir():
            return Resultado(False, salida=f"no es directorio: {ruta}")
        lineas = []
        for hijo in sorted(p.iterdir())[:400]:
            marca = "/" if hijo.is_dir() else ""
            tam = "" if hijo.is_dir() else f" {hijo.stat().st_size}B"
            lineas.append(f"{hijo.name}{marca}{tam}")
        return Resultado(True, salida="\n".join(lineas) or "(vacío)")

    async def _patch_file(self, ruta: str = "", buscar: str = "",
                          reemplazar: str = "") -> Resultado:
        """Parche QUIRÚRGICO: buscar debe aparecer exactamente una vez."""
        if not ruta or not buscar:
            return Resultado(False, salida="patch_file sin ruta o buscar")
        p = self._segura(ruta)
        if not p.exists():
            return Resultado(False, salida=f"no existe: {ruta}")
        texto = p.read_text(encoding="utf-8")
        n = texto.count(buscar)
        if n != 1:
            return Resultado(False,
                             salida=f"'buscar' aparece {n} veces (se exige "
                                    f"exactamente 1): no se toca nada")
        p.write_text(texto.replace(buscar, reemplazar, 1),
                     encoding="utf-8")
        _journal({"accion": "patch", "ruta": str(p)})
        return Resultado(True, salida="parche aplicado (1 sustitución)",
                         ruta=p)

    async def _delete_file(self, ruta: str = "") -> Resultado:
        """BORRADO SEGURO: a la papelera, nunca rm directo."""
        if not ruta:
            return Resultado(False, salida="delete_file sin ruta")
        p = self._segura(ruta)
        if not p.exists():
            return Resultado(False, salida=f"no existe: {ruta}")
        destino = config.papelera_dir() / \
            f"{int(time.time())}_{p.name}"
        shutil.move(str(p), str(destino))
        _journal({"accion": "delete", "desde": str(p), "a": str(destino)})
        return Resultado(True, salida=f"a la papelera: {destino.name}",
                         ruta=destino)

    # ---------------------------------------------------- ejecución

    async def _run_python(self, codigo: str = "", plazo_s: float = 20.0) \
            -> Resultado:
        """Ejecuta Python en un proceso aparte, con plazo.

        NO se usa `sys.executable`, y esto solo se ve en el binario. Dentro
        de un onefile de PyInstaller `sys.executable` **es el propio .exe**,
        no un intérprete: `[sys.executable, "-I", "-c", codigo]` relanzaba
        VeniceMAGI entero —otra ventana, otro servidor— en vez de ejecutar
        el código. No daba error: daba el resultado de otro programa, que
        es peor.

        `paths.python_executable()` devuelve `None` cuando no hay ningún
        Python de verdad, y aquí se dice. Quinta regla: «no he podido
        comprobarlo» no es «está bien».
        """
        if not codigo.strip():
            return Resultado(False, salida="run_python sin código")
        from ..core.paths import python_executable
        interprete = python_executable()
        if interprete is None:
            return Resultado(
                False,
                salida="no hay ningún intérprete de Python en esta máquina "
                       "(y dentro del .exe `sys.executable` es el propio "
                       "VeniceMAGI, así que usarlo relanzaría la app). "
                       "Instala Python y vuelve a intentarlo.")
        p = subprocess.run(
            [interprete, "-I", "-c", codigo],
            capture_output=True, text=True, timeout=max(5, plazo_s),
            cwd=str(self.ws))
        cuerpo = (p.stdout or "") + (("\n[stderr]\n" + p.stderr)
                                     if p.stderr else "")
        return Resultado(p.returncode == 0,
                         salida=cuerpo.strip() or "(sin salida)")

    async def _shell(self, cmd: str = "") -> Resultado:
        """Comando del sistema SOLO con tu aprobación explícita."""
        if not cmd.strip():
            return Resultado(False, salida="shell sin comando")
        if self.kernel is None:
            return Resultado(False,
                             salida="shell no disponible sin kernel (GUI)")
        permitido = await self.kernel.pide_aprobacion(cmd)
        if not permitido:
            return Resultado(False, salida="el usuario NO aprobó el comando")
        p = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=120, cwd=str(self.ws))
        _journal({"accion": "shell", "cmd": cmd, "rc": p.returncode})
        cuerpo = (p.stdout or "") + (("\n[stderr]\n" + p.stderr)
                                     if p.stderr else "")
        return Resultado(p.returncode == 0,
                         salida=cuerpo.strip()[:8000] or "(sin salida)")

    # ------------------------------------------------------ hardware

    async def _hardware_info(self) -> Resultado:
        """Lo que TU máquina puede darle al enjambre."""
        ram_gb = _ram_gb()
        gpu = _gpu()
        libre = shutil.disk_usage(str(self.ws)).free / (1024 ** 3)
        lineas = [
            f"so: {platform.system()} {platform.release()}",
            f"cpu: {platform.processor() or platform.machine()} "
            f"({__import__('os').cpu_count()} hilos)",
            f"ram: {ram_gb:.1f} GB" if ram_gb else "ram: ?",
            f"gpu: {gpu}",
            f"disco libre (workspace): {libre:.1f} GB",
            f"python: {sys.version.split()[0]}",
            "ffmpeg: " + ("sí" if shutil.which("ffmpeg")
                          else "NO (vídeo de planos no disponible)"),
        ]
        return Resultado(True, salida="\n".join(lineas))

    # ------------------------------------------------------ generación

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
        return Resultado(True, salida="imagen generada", ruta=ruta)

    async def _generate_video(self, prompt: str = "", **_) -> Resultado:
        return Resultado(False, salida=(
            "Venice reserva el vídeo AI a cuentas Pro. Usa video_planos: "
            "genero los planos como imágenes y compongo el mp4 EN TU PC "
            "con ffmpeg."))

    async def _video_planos(self, planos: list[str] | None = None,
                            duracion_s: float = 3.0,
                            fundido_s: float = 0.6) -> Resultado:
        """Vídeo de planos: N imágenes Venice → mp4 compuesto AQUÍ.

        HONESTO: es un vídeo de planos con fundidos (motion graphics),
        no vídeo AI fluido. La potencia viene de tu ffmpeg, no de Venice.
        """
        planos = [p for p in (planos or []) if p.strip()]
        if not planos:
            return Resultado(False, salida="video_planos sin planos")
        if len(planos) > 12:
            return Resultado(False, salida="máximo 12 planos por vídeo")
        if not shutil.which("ffmpeg"):
            return Resultado(False, salida=(
                "ffmpeg no está en PATH: instálalo (winget install "
                "Gyan.FFmpeg) para componer el vídeo localmente"))
        ficheros: list[Path] = []
        for i, plano in enumerate(planos):
            if self.kernel:
                self.kernel.emite("estado",
                                  mensaje=f"plano {i + 1}/{len(planos)}…")
            ruta = await self.venice.imagen(plano, aspect_ratio="16:9")
            ficheros.append(ruta)
        destino = config.media_dir() / f"video_planos_{int(time.time())}.mp4"
        cmd = _cmd_ffmpeg(ficheros, destino, duracion_s, fundido_s)
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=300)
        if p.returncode != 0 or not destino.exists():
            return Resultado(False,
                             salida=f"ffmpeg falló: {p.stderr[-600:]}")
        _journal({"accion": "video_planos", "planos": len(ficheros),
                  "salida": str(destino)})
        return Resultado(True, salida=f"{len(ficheros)} planos → "
                                      f"{destino.name}", ruta=destino)


def _ram_gb() -> float | None:
    try:
        import ctypes

        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong)]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys / (1024 ** 3)
    except Exception:                                    # noqa: BLE001
        return None


def _gpu() -> str:
    try:
        p = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            capture_output=True, text=True, timeout=15)
        lineas = [l.strip() for l in (p.stdout or "").splitlines()
                  if l.strip() and l.strip().lower() != "name"]
        return " | ".join(lineas[:2]) if lineas else "desconocida"
    except Exception:                                    # noqa: BLE001
        return "desconocida"


def _cmd_ffmpeg(ficheros: list[Path], destino: Path,
                dur: float, fundido: float) -> list[str]:
    """Concatena imágenes con fundidos: escala, encadena xfade, exporta."""
    cmd: list[str] = ["ffmpeg", "-y"]
    for f in ficheros:
        cmd += ["-loop", "1", "-t", f"{dur + fundido:.2f}", "-i", str(f)]
    n = len(ficheros)
    filtros = [f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease"
               f",pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
               f"[v{i}]" for i in range(n)]
    if n == 1:
        previo = "v0"
    else:
        previo = "v0"
        offset = dur
        for i in range(1, n):
            salida = f"x{i}"
            filtros.append(
                f"[{previo}][v{i}]xfade=transition=fade:"
                f"duration={fundido:.2f}:offset={offset:.2f}[{salida}]")
            previo = salida
            offset += dur - fundido
    cmd += ["-filter_complex", ";".join(filtros),
            "-map", f"[{previo}]", "-r", "25", str(destino)]
    return cmd
