"""VeniceMAGI — REPL de consola. Solo Venice, sin cuenta y sin clave.

La sesión anónima la abre la puerta de navegador (vmagi/sesion.py) la
primera vez que se necesita; luego todo va por HTTP.
Comandos: /sesion /estado /historial /imagen /video /refs /salir
"""
from __future__ import annotations

import asyncio
import sys

from . import config, naoko, roles, sesion
from .orchestrator import Orquestador, Ronda
from .store import Historial
from .venice import Venice

C = {"NAOKO": "\033[95m", "MELCHIOR": "\033[93m",
     "BALTHASAR": "\033[91m", "CASPER": "\033[92m",
     "SYS": "\033[96m", "FIN": "\033[0m", "DIM": "\033[2m"}

#: URLs de diseños de referencia para vídeo.
_REFS: list[str] = []


def _p(quien: str, texto: str) -> None:
    print(f"\n{C[quien]}[{quien}]{C['FIN']} {texto}", flush=True)


def _recorta(t: str, n: int = 1200) -> str:
    return t if len(t) <= n else t[:n] + f"\n… ({len(t) - n} caracteres más)"


def _dim(t: str) -> str:
    return f"{C['DIM']}{t}{C['FIN']}"


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Las tareas internas de playwright a veces terminan en el loop del
    # REPL cuando su hilo ya se apaga ("Cannot switch to a different
    # thread"): ruido de cierre, no fallos del enjambre. Se silencia SOLO
    # eso; cualquier otra excepción del loop sigue contándose entera.
    def _filtro_playwright(loop, ctx):
        msg = str(ctx.get("message", "")) + str(ctx.get("exception", ""))
        if "playwright" in msg.lower() or "greenlet" in msg.lower()                 or "Task finished" in msg:
            return
        loop.default_exception_handler(ctx)

    asyncio.get_event_loop().set_exception_handler(_filtro_playwright)
    hist = Historial(config.data_dir() / "historial.db")
    v = Venice(progreso=lambda m: _p("SYS", _dim(m)))
    orch = Orquestador(v, config.workspace())
    previa: Ronda | None = None

    _p("SYS", f"VeniceMAGI {config.VERSION} — solo Venice, sin cuenta y "
              f"sin clave")
    if not sesion.edge_disponible():
        _p("NAOKO", "No encuentro Edge: es la puerta a Venice sin cuenta. "
                    "Instálalo desde microsoft.com/edge y vuelve a abrir.")
    _p("SYS", "Escribe tu petición, o /ayuda.")

    bucle = asyncio.get_event_loop()
    while True:
        try:
            linea = await bucle.run_in_executor(
                None, input, f"\n{C['DIM']}tú>{C['FIN']} ")
        except (EOFError, KeyboardInterrupt):
            break
        linea = linea.strip()
        if not linea:
            continue

        if linea.startswith("/"):
            if await _comando(linea, v, hist):
                break
            continue

        try:
            if previa is not None:
                _p("SYS", _dim("( segunda ronda: tu mensaje es feedback "
                               "sobre la síntesis anterior )"))
            r = await orch.ronda(linea, feedback=linea if previa else "",
                                 previa=previa)
            previa = r
            hist.anota(linea, r.sintesis, r.artefactos)
            if r.nota_naoko:
                _p("NAOKO", r.nota_naoko)
            if r.tesis:
                _p("MELCHIOR", _recorta(r.tesis))
                _p("SYS", _dim("  " + (r.evidencia or
                                       "").replace("\n", "\n  ")))
            if r.antitesis:
                _p("BALTHASAR", _recorta(r.antitesis))
            _p("CASPER", r.sintesis or "(sin síntesis)")
            if r.artefactos:
                _p("SYS", "artefactos:\n  " + "\n  ".join(r.artefactos))
        except Exception as e:                           # noqa: BLE001
            _p("NAOKO", naoko.explica_error(e))

    # La puerta (ventana de Edge) no puede quedar huérfana al salir.
    # Al cerrar, playwright deja callbacks verdes que el loop del REPL
    # intenta ejecutar cuando ya no tienen hilo ("Cannot switch to a
    # different thread"): es ruido de apagado, no un fallo — y ya nos
    # vamos, así que el loop deja de contarlo.
    asyncio.get_event_loop().set_exception_handler(lambda loop, ctx: None)
    try:
        await v.cerrar()
    except Exception:                                    # noqa: BLE001
        pass
    hist.close()
    _p("SYS", "hasta luego.")
    return 0


async def _comando(linea: str, v: Venice, hist: Historial) -> bool:
    partes = linea.split()
    cmd = partes[0].lower()

    if cmd in ("/salir", "/exit", "/quit"):
        return True
    if cmd == "/ayuda":
        _p("SYS", "\n".join([
            "/sesion        reabre la puerta (renueva la sesión anónima)",
            "/estado        modo, navegador de la puerta y rutas",
            "/historial [n] últimas rondas",
            "/imagen PROMPT genera una imagen (sesión anónima)",
            "/video PROMPT  genera un vídeo (Venice puede exigir cuenta)",
            "/refs add|clear|list  URLs de diseño de referencia para vídeo",
            "/proxy URL|off    enruta la ventana del Guest por TU proxy/VPN",
            "/salir"]))
    elif cmd == "/sesion":
        await v.cerrar()
        try:
            await v.modelos()
            _p("SYS", "puerta reabierta: Venice Guest de nuevo en línea")
        except Exception as e:                           # noqa: BLE001
            _p("NAOKO", naoko.explica_error(e))
    elif cmd == "/estado":
        _p("NAOKO", naoko.estado_legible())
    elif cmd == "/historial":
        n = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 5
        filas = hist.ultimas(n)
        if not filas:
            _p("SYS", "(sin historial todavía)")
        for f in filas:
            _p("SYS", f"· {f['peticion'][:70]} → "
                      f"{len(f['artefactos'])} artefactos")
    elif cmd == "/imagen":
        try:
            ruta = await v.imagen(" ".join(partes[1:]), aspect_ratio="1:1")
            _p("SYS", f"imagen: {ruta}")
        except Exception as e:                           # noqa: BLE001
            _p("NAOKO", naoko.explica_error(e))
    elif cmd == "/video":
        try:
            ruta = await v.video(" ".join(partes[1:]), ref_urls=_REFS or None)
            _p("SYS", f"vídeo: {ruta}")
        except Exception as e:                           # noqa: BLE001
            _p("NAOKO", naoko.explica_error(e))
    elif cmd == "/refs":
        _refs(partes)
    elif cmd == "/proxy":
        if len(partes) > 1 and partes[1].lower() not in ("off", ""):
            config.guardar_proxy(partes[1])
            await v.cerrar()          # la puerta se reabre ya con el proxy
            _p("SYS", f"proxy fijado: {partes[1]} (solo la ventana del "
                      f"Guest). La próxima petición lo usará.")
        elif len(partes) > 1:
            config.guardar_proxy(None)
            await v.cerrar()
            _p("SYS", "proxy quitado: la puerta vuelve a tu red normal")
        else:
            actual = config.proxy() or "(sin proxy)"
            _p("SYS", f"proxy actual: {actual}\n"
                      "uso: /proxy socks5://127.0.0.1:9050 · /proxy off")
    else:
        _p("NAOKO", f"comando desconocido: {cmd} (prueba /ayuda)")
    return False


def _refs(partes):
    global _REFS
    if len(partes) < 2 or partes[1] == "list":
        _p("SYS", "refs de vídeo:\n  " +
           ("\n  ".join(_REFS) or "(ninguna)"))
    elif partes[1] == "add" and len(partes) > 2:
        _REFS.extend(partes[2:])
        _p("SYS", f"{len(_REFS)} referencias: el vídeo copiará estos diseños")
    elif partes[1] == "clear":
        _REFS = []
        _p("SYS", "referencias borradas")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
