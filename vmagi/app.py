"""VeniceMAGI — REPL de consola. Solo Venice, sin cuenta y sin clave.

La sesión anónima la abre la puerta de navegador (vmagi/sesion.py) la
primera vez que se necesita; luego todo va por HTTP.
Comandos: /sesion /estado /historial /imagen /video /refs /salir
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from . import config, health, naoko, roles, sesion
from .media_pipeline import lee_metadata, metadata_path
from .observability import EventLogger
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
    logger = EventLogger(config.data_dir() / "events.jsonl")
    v = Venice(progreso=lambda m: _p("SYS", _dim(m)))
    orch = Orquestador(v, config.workspace())
    previa: Ronda | None = None

    _p("SYS", f"VeniceMAGI {config.VERSION} — interfaz MAGI unificada")
    if not sesion.edge_disponible():
        _p("NAOKO", "No encuentro Edge: es la puerta a Venice sin cuenta. "
                    "Instálalo desde microsoft.com/edge y vuelve a abrir.")
    await _panel_magi(v)
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

        trace_id = logger.new_trace_id()
        logger.emit(level="info", code="ROUND_START", trace_id=trace_id,
                    message="Nueva ronda", extra={"input_len": len(linea)})
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
            logger.emit(level="info", code="ROUND_OK", trace_id=trace_id,
                        message="Ronda completada",
                        extra={"artefactos": len(r.artefactos)})
        except Exception as e:                           # noqa: BLE001
            _p("NAOKO", naoko.explica_error(e))
            logger.emit(level="error", code="ROUND_ERROR", trace_id=trace_id,
                        message=str(e), extra={"error_type": type(e).__name__})

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
            "/magi          panel unificado (providers + estado)",
            "/salud         healthchecks de integración",
            "/historial [n] últimas rondas",
            "/galeria [n]   últimos artefactos",
            "/backend [automatic1111|comfyui] ver/cambiar backend de imagen",
            "/quality [draft|standard|ultra] ver/cambiar calidad de imagen",
            "/notrack show|off|URL|required on|required off",
            "/imagen [--ar 16:9] [--seed N] [--quality q] [--backend b] PROMPT",
            "/video [--duration 10s] PROMPT  (solo Seedance 2.5+)",
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
    elif cmd == "/magi":
        await _panel_magi(v)
    elif cmd == "/salud":
        s = health.estado_salud()
        _p("SYS", "\n".join([
            f"global: {'OK' if s['ok_global'] else 'REVISAR'}",
            f"edge: {'OK' if s['edge_disponible'] else 'FALLO'}",
            f"notrack: {'OK' if (s['notrack_configurado'] or not s['notrack_obligatorio']) else 'FALLO'}",
            f"backend imagen: {s['backend_imagen']} ({'OK' if s['backend_imagen_ok'] else 'FALLO'})",
            f"seedance: {s['seedance_modelo']} ({'OK' if s['seedance_ok'] else 'FALLO'})",
            f"api key vídeo: {'OK' if s['venice_api_key'] else 'NO'}",
        ]))
    elif cmd == "/historial":
        n = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 5
        filas = hist.ultimas(n)
        if not filas:
            _p("SYS", "(sin historial todavía)")
        for f in filas:
            _p("SYS", f"· {f['peticion'][:70]} → "
                      f"{len(f['artefactos'])} artefactos")
    elif cmd == "/galeria":
        n = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else 10
        n = max(1, n)
        renders = hist.ultimos_renders(n)
        if renders:
            lineas = []
            for r in renders:
                m = lee_metadata(Path(r["ruta"]))
                detalle = ""
                if m:
                    detalle = (f" · {m.get('backend', '-')}"
                               f" · {m.get('model', m.get('workflow', '-'))}")
                lineas.append(f"{r['kind']}: {r['ruta']}{detalle}")
            _p("SYS", "galería:\n  " + "\n  ".join(lineas))
            return False
        filas = hist.ultimas(n)
        rutas = [x.strip() for f in filas for x in f["artefactos"] if x.strip()]
        if not rutas:
            _p("SYS", "(sin artefactos todavía)")
        else:
            _p("SYS", "galería:\n  " + "\n  ".join(rutas[:n]))
    elif cmd == "/backend":
        if len(partes) > 1:
            try:
                b = config.guardar_backend_imagen(partes[1])
                _p("SYS", f"backend de imagen fijado: {b}")
            except ValueError as e:
                _p("NAOKO", str(e))
        else:
            _p("SYS", f"backend actual: {config.backend_imagen()}")
    elif cmd == "/quality":
        if len(partes) > 1:
            try:
                q = config.guardar_calidad_imagen(partes[1])
                _p("SYS", f"calidad de imagen fijada: {q}")
            except ValueError as e:
                _p("NAOKO", str(e))
        else:
            _p("SYS", f"calidad actual: {config.calidad_imagen()}")
    elif cmd == "/notrack":
        if len(partes) == 1 or partes[1].lower() == "show":
            _p("SYS", "\n".join([
                f"notrack proxy: {config.notrack_proxy() or '(sin configurar)'}",
                f"notrack required: {'on' if config.notrack_obligatorio() else 'off'}",
            ]))
        elif partes[1].lower() == "off":
            config.guardar_notrack_proxy(None)
            await v.cerrar()
            _p("SYS", "notrack proxy desactivado (aplicado a la próxima sesión)")
        elif partes[1].lower() == "required" and len(partes) > 2:
            val = _parse_on_off(partes[2])
            if val is None:
                _p("NAOKO", "uso: /notrack required on|off")
            else:
                config.guardar_notrack_obligatorio(val)
                _p("SYS", f"notrack required: {'on' if val else 'off'}")
        else:
            config.guardar_notrack_proxy(partes[1])
            await v.cerrar()
            _p("SYS", f"notrack proxy fijado: {partes[1]} (aplicado a la próxima sesión)")
    elif cmd == "/imagen":
        try:
            opts, prompt = _parse_flags(partes[1:], {
                "--ar": "aspect_ratio",
                "--aspect": "aspect_ratio",
                "--seed": "seed",
                "--quality": "quality",
                "--backend": "backend",
            })
            seed = _parse_int(opts.get("seed"))
            if not prompt:
                _p("NAOKO", "Falta prompt. Uso: /imagen [flags] PROMPT")
                return False
            if opts.get("seed") is not None and seed is None:
                _p("NAOKO", "seed inválido: usa un entero (ej. 42 o -1)")
                return False
            try:
                aspect_ratio = config.normaliza_aspect_ratio(
                    opts.get("aspect_ratio") or "1:1"
                )
                quality = (config.normaliza_calidad_imagen(opts["quality"])
                           if "quality" in opts else None)
                backend = (config.normaliza_backend_imagen(opts["backend"])
                           if "backend" in opts else None)
            except ValueError as e:
                _p("NAOKO", str(e))
                return False
            ruta = await v.imagen(
                prompt,
                aspect_ratio=aspect_ratio,
                seed=seed,
                quality=quality,
                backend=backend,
            )
            hist.anota_render(
                kind="image",
                prompt=prompt,
                ruta=str(ruta),
                metadata=str(metadata_path(Path(ruta))),
            )
            _p("SYS", f"imagen: {ruta}")
        except Exception as e:                           # noqa: BLE001
            _p("NAOKO", naoko.explica_error(e))
    elif cmd == "/video":
        try:
            opts, prompt = _parse_flags(partes[1:], {"--duration": "duration"})
            if not prompt:
                _p("NAOKO", "Falta prompt. Uso: /video [--duration 10s] PROMPT")
                return False
            try:
                duration = config.normaliza_duration(
                    opts.get("duration", "10s")
                )
            except ValueError as e:
                _p("NAOKO", str(e))
                return False
            ruta = await v.video(prompt, ref_urls=_REFS or None,
                                 duration=duration)
            hist.anota_render(
                kind="video",
                prompt=prompt,
                ruta=str(ruta),
                metadata=str(metadata_path(Path(ruta))),
            )
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


def _parse_flags(tokens: list[str], mapa: dict[str, str]) -> tuple[dict, str]:
    opts: dict[str, str] = {}
    rest: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in mapa and i + 1 < len(tokens):
            opts[mapa[t]] = tokens[i + 1]
            i += 2
            continue
        rest.append(t)
        i += 1
    return opts, " ".join(rest).strip()


def _parse_int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _parse_on_off(v: str | None) -> bool | None:
    s = (v or "").strip().lower()
    if s in ("on", "true", "1", "yes", "si", "sí"):
        return True
    if s in ("off", "false", "0", "no"):
        return False
    return None


async def _panel_magi(v: Venice) -> None:
    s = health.estado_salud()
    chat = v.etiqueta_provider_chat()
    _p("SYS", "\n".join([
        "=== MAGI PANEL ===",
        f"chat provider: {chat}",
        f"image backend: {config.backend_imagen()}",
        f"video backend: {config.modelo_video_seedance()}",
        f"notrack proxy: {config.notrack_proxy() or '(no configurado)'}",
        f"notrack required: {'on' if config.notrack_obligatorio() else 'off'}",
        f"image quality: {config.calidad_imagen()}",
        f"workspace: {config.workspace()}",
        f"media: {config.media_dir()}",
        f"health: {'OK' if s['ok_global'] else 'REVISAR'}",
    ]))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
