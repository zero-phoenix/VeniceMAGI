"""Las herramientas que el manifiesto de VeniceMAGI promete por su nombre.

POR QUE UN MODULO APARTE Y NO SEIS LINEAS EN builtin.py
=======================================================
El README de VeniceMAGI promete, literalmente: Â«IDE real: `read_file`,
`list_dir`, `patch_file` quirurgico, `delete_file` a papelera con journal,
`hardware_info` (CPU/RAM/GPU/disco), `run_python` con plazo y `shell` solo
con tu aprobacion clic a clicÂ».

El nucleo portado trae equivalentes con otros nombres â€”`edit_file`,
`delete_path`, `python_exec`, `run_command`â€” y no traia `hardware_info` en
absoluto. Un README que promete un nombre que no existe es una promesa
incumplida aunque la capacidad este: quien lea la documentacion y escriba
`patch_file` recibe Â«herramienta desconocidaÂ», y con razon concluye que el
documento miente.

Aqui se cierran las dos mitades:

- Los **alias** exponen los nombres prometidos apuntando a la
  implementacion real. No duplican logica: si `edit_file` mejora,
  `patch_file` mejora con el, porque es el mismo objeto con otro nombre.
- `hardware_info` es codigo nuevo, porque esa capacidad no existia.

QUE NO CAMBIA
=============
Los permisos. Un alias hereda `access` y `dangerous` del original: llamar
`shell` en vez de `run_command` no salta la aprobacion clic a clic, y
`delete_file` deja la misma entrada en el journal que `delete_path` â€” la
papelera y el `undo` son los del nucleo, no una copia.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import replace

from .registry import Tool, ToolResult

logger = logging.getLogger(__name__)

__all__ = ["ALIAS", "hardware_info", "registra"]

#: nombre prometido en el README -> herramienta que ya existe
ALIAS: dict[str, str] = {
    "patch_file": "edit_file",
    "delete_file": "delete_path",
    "run_python": "python_exec",
    "shell": "run_command",
}


def _instala_alias(reg) -> list[str]:
    """Registra los nombres del README apuntando a lo que ya hay.

    Devuelve los alias instalados. Un alias cuyo original no existe se
    SALTA con un aviso en vez de reventar: el registro de herramientas se
    construye al arrancar, y un nombre que cambie en el nucleo no puede
    dejar el sistema sin arrancar â€” deja el sistema sin ese alias, que es
    un fallo mucho mas pequeno y visible en el log.
    """
    puestos = []
    for alias, original in ALIAS.items():
        base: Tool | None = reg.get(original)
        if base is None:
            logger.warning(
                "[manifiesto] '%s' promete a '%s', que no existe en el "
                "registro. El alias no se instala.", alias, original)
            continue
        if reg.get(alias) is not None:
            continue
        reg.register(replace(
            base,
            name=alias,
            description=f"{base.description} (alias de `{original}`)",
        ))
        puestos.append(alias)
    return puestos


def _gpus() -> list[str]:
    """Las GPU que se puedan enumerar. Lista vacia = no se pudo, y se dice.

    No se inventa un Â«GPU: desconocidaÂ»: una respuesta vaga sobre el
    hardware es peor que ninguna, porque el enjambre la usa para decidir
    si un trabajo cabe en la maquina.
    """
    salida: list[str] = []
    if sys.platform == "win32":
        exe = shutil.which("wmic")
        if exe:
            try:
                r = subprocess.run(
                    [exe, "path", "win32_VideoController", "get", "name"],
                    capture_output=True, text=True, timeout=12)
                salida = [linea.strip() for linea in r.stdout.splitlines()[1:]
                          if linea.strip()]
            except Exception:                            # noqa: BLE001
                pass
        if not salida and shutil.which("powershell"):
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_VideoController).Name"],
                    capture_output=True, text=True, timeout=15)
                salida = [linea.strip() for linea in r.stdout.splitlines() if linea.strip()]
            except Exception:                            # noqa: BLE001
                pass
    elif sys.platform.startswith("linux") and shutil.which("lspci"):
        try:
            r = subprocess.run(["lspci"], capture_output=True, text=True,
                               timeout=12)
            salida = [linea.split(": ", 1)[-1] for linea in r.stdout.splitlines()
                      if "VGA" in linea or "3D controller" in linea]
        except Exception:                                # noqa: BLE001
            pass
    if not salida and shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=12)
            salida = [linea.strip() for linea in r.stdout.splitlines() if linea.strip()]
        except Exception:                                # noqa: BLE001
            pass
    return salida


def _memoria_gb() -> float | None:
    try:
        import psutil
        return round(psutil.virtual_memory().total / 1024 ** 3, 1)
    except ImportError:
        pass
    try:                                                 # Linux, sin psutil
        paginas = os.sysconf("SC_PHYS_PAGES")
        tam = os.sysconf("SC_PAGE_SIZE")
        return round(paginas * tam / 1024 ** 3, 1)
    except (ValueError, AttributeError, OSError):
        return None


def hardware_info() -> dict:
    """CPU, RAM, GPU y disco de ESTA maquina. Sin adivinar nada.

    Cada campo que no se puede medir sale como `None` o lista vacia y se
    resume en `no_verificado`. Es la quinta regla del proyecto: Â«no he
    podido comprobarloÂ» no es Â«esta bienÂ», y aqui tampoco es Â«8 GBÂ».
    """
    no_verificado: list[str] = []

    ram = _memoria_gb()
    if ram is None:
        no_verificado.append(
            "RAM total: no se pudo medir (instala psutil para tenerla)")

    gpus = _gpus()
    if not gpus:
        no_verificado.append(
            "GPU: no se pudo enumerar ninguna en esta plataforma")

    discos = []
    for punto in ({"C:\\"} if sys.platform == "win32"
                  else {"/", os.path.expanduser("~")}):
        try:
            u = shutil.disk_usage(punto)
            discos.append({
                "punto": punto,
                "total_gb": round(u.total / 1024 ** 3, 1),
                "libre_gb": round(u.free / 1024 ** 3, 1),
            })
        except OSError:
            no_verificado.append(f"disco {punto}: no accesible")

    return {
        "cpu": {
            "modelo": platform.processor() or platform.machine() or None,
            "arquitectura": platform.machine(),
            "nucleos_logicos": os.cpu_count(),
        },
        "ram_total_gb": ram,
        "gpu": gpus,
        "discos": discos,
        "so": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "no_verificado": no_verificado,
    }


def registra(reg) -> list[str]:
    """Instala `hardware_info` y los alias del README. Devuelve los nombres."""

    @reg.tool(
        "hardware_info",
        "Informa del hardware de esta maquina: CPU, RAM, GPU y discos. "
        "Lo que no se pueda medir sale en 'no_verificado', nunca inventado.",
        {"type": "object", "properties": {}},
        access={"read"},
    )
    def _hardware_info(ctx=None):
        datos = hardware_info()
        lineas = [
            f"CPU: {datos['cpu']['modelo'] or '?'} "
            f"({datos['cpu']['nucleos_logicos']} nucleos logicos, "
            f"{datos['cpu']['arquitectura']})",
            f"RAM: {datos['ram_total_gb']} GB" if datos["ram_total_gb"]
            else "RAM: no medida",
            "GPU: " + (", ".join(datos["gpu"]) if datos["gpu"] else "no enumerada"),
        ]
        for d in datos["discos"]:
            lineas.append(f"Disco {d['punto']}: {d['libre_gb']} GB libres "
                          f"de {d['total_gb']} GB")
        lineas.append(f"SO: {datos['so']} Â· Python {datos['python']}")
        for x in datos["no_verificado"]:
            lineas.append(f"[no verificado] {x}")
        return ToolResult(True, "\n".join(lineas), meta=datos)

    return ["hardware_info", *_instala_alias(reg)]
