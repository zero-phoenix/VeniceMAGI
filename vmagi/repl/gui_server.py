"""Servidor local de la GUI: HTTP + JSON sobre el kernel. Sin dependencias.

Escucha SOLO en 127.0.0.1 con puerto libre. La GUI pregunta por eventos
(polling: en local es instantáneo y evita un websocket entero) y manda
peticiones/aprobaciones/toggles.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..venice import config

WEB = Path(__file__).parent / "web"
_MIME = {".html": "text/html; charset=utf-8",
         ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".svg": "image/svg+xml",
         ".ico": "image/x-icon"}


class GuiServer:
    def __init__(self, kernel, loop):
        self.kernel = kernel
        self.loop = loop            # loop del kernel (asyncio)
        self.httpd: ThreadingHTTPServer | None = None
        self.hilo: threading.Thread | None = None
        self.puerto = 0

    # ------------------------------------------------------------ ciclo

    def arranca(self) -> int:
        servidor = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):      # silencio: la GUI no es un log
                pass

            def _json(self, obj, estado=200):
                b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(estado)
                self.send_header("Content-Type",
                                 "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                u = urlparse(self.path)
                if u.path == "/" or u.path == "/index.html":
                    return self._static("index.html")
                if u.path.startswith("/api/"):
                    return self._api_get(u.path, parse_qs(u.query))
                return self._static(u.path.lstrip("/"))

            def do_POST(self):
                u = urlparse(self.path)
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = {}
                if largo:
                    try:
                        cuerpo = json.loads(
                            self.rfile.read(largo).decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        return self._json({"error": "cuerpo inválido"}, 400)
                return self._api_post(u.path, cuerpo)

            # ------------------------------------------------ estáticos

            def _static(self, nombre: str):
                f = (WEB / nombre).resolve()
                if not str(f).startswith(str(WEB.resolve())) or not f.exists():
                    return self._json({"error": "no existe"}, 404)
                b = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type",
                                 _MIME.get(f.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            # ------------------------------------------------------ GET

            def _api_get(self, ruta: str, q):
                k = servidor.kernel
                if ruta == "/api/eventos":
                    desde = int((q.get("desde") or ["0"])[0])
                    return self._json({"eventos": k.eventos_desde(desde),
                                       "trabajando": k.trabajando})
                if ruta == "/api/estado":
                    return self._json({
                        "version": config.VERSION,
                        "hoy": k.hoy,
                        "llamadas_hoy": k.llamadas_hoy,
                        "puerta_visible": config.puerta_visible(),
                        "proxy": config.proxy(),
                        "permitir_shell": config.permitir_shell(),
                        "cola": k.cola.qsize(),
                        "trabajando": k.trabajando,
                    })
                if ruta == "/api/workspace":
                    return self._json(_arbol(config.workspace()))
                if ruta == "/api/fichero":
                    rel = (q.get("ruta") or [""])[0]
                    p = (config.workspace() / rel).resolve()
                    if not str(p).startswith(
                            str(config.workspace().resolve())):
                        return self._json({"error": "fuera del workspace"},
                                           400)
                    if not p.exists():
                        return self._json({"error": "no existe"}, 404)
                    return self._json({"ruta": rel,
                                       "contenido": p.read_text(
                                           encoding="utf-8",
                                           errors="replace")[:200_000]})
                if ruta == "/api/medios":
                    return self._json({"medios": _medios()})
                if ruta == "/api/historial":
                    return self._json({"filas": k.hist.ultimas(
                        int((q.get("n") or ["8"])[0]))})
                if ruta == "/api/aprobaciones":
                    return self._json({"pendientes": [
                        {"id": a.id, "cmd": a.cmd}
                        for a in k.aprobaciones.values()]})
                return self._json({"error": "ruta desconocida"}, 404)

            # ----------------------------------------------------- POST

            def _api_post(self, ruta: str, cuerpo):
                k = servidor.kernel
                if ruta == "/api/peticion":
                    texto = (cuerpo.get("texto") or "").strip()
                    if not texto:
                        return self._json({"error": "vacío"}, 400)
                    if k.trabajando:
                        k.cola.put_nowait(texto)
                        return self._json({"ok": True, "encolada": True})
                    k.cola.put_nowait(texto)
                    return self._json({"ok": True, "encolada": False})
                if ruta == "/api/aprobar":
                    ok = k.resuelve_aprobacion(
                        cuerpo.get("id", ""), bool(cuerpo.get("ok")),
                        servidor.loop)
                    return self._json({"ok": ok})
                if ruta == "/api/puerta":
                    visible = bool(cuerpo.get("visible"))
                    config.fijar_puerta_visible(visible)
                    import asyncio
                    def _reinicia():
                        asyncio.run_coroutine_threadsafe(
                            k.v.cerrar(), servidor.loop)
                    _reinicia()
                    return self._json({"ok": True, "visible": visible})
                if ruta == "/api/shell":
                    valor = bool(cuerpo.get("permitir"))
                    config.fijar_permitir_shell(valor)
                    return self._json({"ok": True, "permitir": valor})
                if ruta == "/api/guardar_fichero":
                    rel = cuerpo.get("ruta") or ""
                    contenido = cuerpo.get("contenido") or ""
                    p = (config.workspace() / rel).resolve()
                    if not str(p).startswith(
                            str(config.workspace().resolve())):
                        return self._json({"error": "fuera del workspace"},
                                           400)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(contenido, encoding="utf-8")
                    with config.journal_path().open("a",
                                                    encoding="utf-8") as f:
                        f.write(json.dumps({"ts": __import__("time").time(),
                                            "accion": "gui_write",
                                            "ruta": str(p)}) + "\n")
                    return self._json({"ok": True})
                return self._json({"error": "ruta desconocida"}, 404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.puerto = self.httpd.server_address[1]
        self.hilo = threading.Thread(target=self.httpd.serve_forever,
                                     daemon=True)
        self.hilo.start()
        return self.puerto

    def para(self) -> None:
        if self.httpd:
            self.httpd.shutdown()


def _arbol(raiz: Path, profundidad: int = 2) -> dict:
    def nodo(p: Path, prof: int) -> dict:
        d: dict = {"nombre": p.name, "ruta": str(p.relative_to(raiz)),
                   "dir": p.is_dir()}
        if p.is_dir() and prof > 0:
            d["hijos"] = [nodo(h, prof - 1)
                          for h in sorted(p.iterdir(),
                                          key=lambda x: (x.is_file(),
                                                         x.name.lower()))
                          ][:200]
        elif p.is_dir():
            d["hijos"] = []
        return d
    return nodo(raiz, profundidad) if raiz.exists() else {"nombre": "?",
                                                          "hijos": []}


def _medios() -> list[dict]:
    out = []
    m = config.media_dir()
    if m.exists():
        for f in sorted(m.iterdir(), key=lambda x: -x.stat().st_mtime):
            if f.suffix.lower() in (".png", ".jpg", ".webp", ".mp4"):
                out.append({"nombre": f.name,
                            "tipo": "video" if f.suffix == ".mp4" else "imagen",
                            "ruta": str(f),
                            "ts": f.stat().st_mtime})
            if len(out) >= 60:
                break
    return out
