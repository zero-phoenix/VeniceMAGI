"""La puerta de sesión: Venice Guest, sin cuenta y sin clave.

VERIFICADO EN VIVO EL 2026-08-16
================================
- La API oficial exige clave; el flujo «auth/anon» legacy está muerto
  («Bad request») y el FAPI de Clerk pide captcha (Turnstile).
- El Guest de la web SÍ existe («Venice Guest», «O prueba Venice sin una
  cuenta»), pero outerface solo atiende sus peticiones desde un navegador
  REAL: con Chromium headless responde 403 (client attestation); con el
  Edge real de la máquina responde 200.
- Por eso la puerta es: Edge del usuario (channel msedge), CON VENTANA
  VISIBLE (así pasa la atestación), perfil propio bajo los datos de la
  app, y modo Guest. La ventana es parte del contrato: es literalmente
  «Venice en tu Edge, manejado por el enjambre».

HILO PROPIO
===========
El REPL corre en asyncio y Playwright Sync API se niega a convivir con un
bucle («Sync API inside the asyncio loop»). La puerta tiene therefore un
hilo DEDICADO que es el único dueño del navegador: el código async delega
cada operación con `llamar(fn)` (bloqueante, para usar con
asyncio.to_thread) y el navegador nunca se toca desde otro hilo.

LÍMITE REAL (dicho claro)
=========================
El Guest tiene cupo DIARIO por IP. Agotado, la UI dice «Has superado el
número de solicitudes de Chat que puedes hacer hoy». Eso no se esquiva
rotando perfiles (sería burlar su ración): Naoko lo explica y toca
volver mañana. «Sin raciones nuestras» = el sistema no añade límites
encima de los de Venice.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from . import config
from .sitios import VENICE, SitioGuest

#: Compatibilidad con la v1, que solo sabia de Venice.
URL_CLASSIC = VENICE.url
PLAZO_ARRANQUE_S = 90.0


class SesionNoDisponible(Exception):
    """La puerta no pudo abrirse, con el motivo."""


class ModalDeLogin(Exception):
    """Apareció el modal de sesión a mitad de operación.

    La sesión Guest de Clerk caduca y Venice la repone pidiendo login en
    CUALQUIER momento — no solo al abrir. La respuesta es volver a entrar
    como Guest y repetir la petición, no pedirle credenciales al usuario
    (no las hay: el sistema es sin cuenta).
    """


def perfil_dir(sitio: SitioGuest | None = None) -> Path:
    """Perfil de Edge PROPIO de cada sitio guest.

    Compartirlo fue un fallo real en cuanto entro el segundo sitio: las
    cookies de sesion de uno tumbaban las del otro, y la puerta reportaba
    «la sesion Guest caduco» sobre un sitio que estaba perfectamente. Un
    perfil por sitio no es higiene, es aislamiento.
    """
    nombre = (sitio or VENICE).nombre
    sufijo = "perfil-edge" if nombre == "venice" else f"perfil-edge-{nombre}"
    p = config.data_dir() / sufijo
    p.mkdir(parents=True, exist_ok=True)
    return p


def edge_disponible() -> bool:
    """Edge presente en disco. Instantáneo: NO lanza ventanas.

    Lanzar el navegador solo para comprobar era lento y frágil (la ventana
    parpadeaba al arrancar y cualquier timeout se leía como «no hay Edge»).
    La comprobación real de que la puerta ARRANCA sigue en Puerta.abrir(),
    que ya lanza de verdad cuando toca.
    """
    rutas = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    return any(p.exists() for p in rutas)


class Puerta:
    """Un hilo dueño del Edge vivo; todo se le delega con `llamar`."""

    def __init__(self, progreso=None, sitio: SitioGuest | None = None):
        self.pg = None
        self._ctx = None
        self._pw = None
        self.sitio = sitio or VENICE
        self._progreso = progreso or (lambda m: None)
        self._cola: queue.Queue = queue.Queue()
        self._hecho = threading.Event()
        self._hilo: threading.Thread | None = None
        self._resultado = None

    # ------------------------------------------------- hilo del navegador

    def _bucle(self) -> None:
        """Vive en su hilo: ejecuta encargos hasta que llegue None."""
        while True:
            fn = self._cola.get()
            if fn is None:
                return
            try:
                self._resultado = (True, fn())
            except Exception as e:                        # noqa: BLE001
                self._resultado = (False, e)
            finally:
                self._hecho.set()

    def llamar(self, fn):
        """Ejecuta fn EN el hilo del navegador y devuelve su resultado.

        Bloqueante: para usar desde asyncio, `await asyncio.to_thread(...)`.
        """
        if self._hilo is None or not self._hilo.is_alive():
            raise SesionNoDisponible("el hilo de la puerta no está vivo")
        self._hecho.clear()
        self._cola.put(fn)
        self._hecho.wait()
        ok, valor = self._resultado
        if not ok:
            raise valor
        return valor

    # ---------------------------------------------------------- apertura

    def abrir(self) -> None:
        """Abre Edge en modo Guest. Bloqueante (hilo aparte o to_thread)."""
        if self.pg is not None:
            return
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()
        self.llamar(self._arranca_navegador)

    @staticmethod
    def _kwargs_lanzamiento() -> dict:
        """Argumentos de lanzamiento del Edge de la puerta.

        Factorizados para poder TESTEARLOS sin lanzar nada: el proxy del
        usuario (si lo configuró) viaja AQUÍ y solo aquí — la ventana del
        Guest se enruta por él; el resto del sistema no se toca.
        """
        args = ["--disable-blink-features=AutomationControlled"]
        if not config.puerta_visible():
            # Puerta APARCADA: el Edge es real y su atestación se resuelve
            # igual (la atestación mira el navegador, no el escritorio),
            # pero fuera de pantalla para no estorbar la ventana propia.
            args.append("--window-position=-32000,-32000")
        kwargs: dict = {
            "channel": "msedge", "headless": False,
            "viewport": {"width": 1100, "height": 800},
            "args": args,
        }
        px = config.proxy() or config.notrack_proxy()
        if px:
            kwargs["proxy"] = {"server": px}
        return kwargs

    def _arranca_navegador(self) -> None:
        """CORRE EN EL HILO DEL NAVEGADOR."""
        from playwright.sync_api import Error as PWError
        try:
            self._pw = __import__(
                "playwright.sync_api", fromlist=["sync_playwright"]
            ).sync_playwright().start()
            if config.proxy():
                self._progreso(f"[puerta] usando proxy {config.proxy()}")
            self._ctx = self._pw.chromium.launch_persistent_context(
                str(perfil_dir(self.sitio)), **self._kwargs_lanzamiento())
            self.pg = self._ctx.new_page()
            self._progreso(
                f"[puerta] abriendo {self.sitio.nombre} (Edge, modo Guest)…")
            self.pg.goto(self.sitio.url, wait_until="domcontentloaded",
                         timeout=60_000)
            self._entra_guest()
            self._espera_chat()
            self._progreso(f"[puerta] {self.sitio.nombre} Guest listo")
        except PWError as e:
            self._apaga()
            raise SesionNoDisponible(
                f"la puerta no pudo abrirse: {e}. ¿Está Edge instalado? "
                "(la puerta usa el Edge real de la máquina)") from e
        except Exception as e:                            # noqa: BLE001
            self._apaga()
            raise SesionNoDisponible(f"la puerta no pudo abrirse: {e}") from e

    def _apaga(self) -> None:
        for cierre in (lambda: self._ctx and self._ctx.close(),
                       lambda: self._pw and self._pw.stop()):
            try:
                cierre()
            except Exception:                            # noqa: BLE001
                pass
        self.pg = self._ctx = self._pw = None

    def _entra_guest(self) -> None:
        """Pulsa el enlace de invitado del sitio, si lo tiene.

        Un sitio sin `entradas_guest` (notrack.ai) ya entra sin pedir
        nada: no encontrar el enlace NO es un fallo, es el caso normal.
        """
        for texto in self.sitio.entradas_guest:
            for frame in self.pg.frames:
                try:
                    frame.get_by_text(texto, exact=False).last.click(
                        timeout=2500)
                    return
                except Exception:                        # noqa: BLE001
                    continue

    # ------------------------------------------- el modal puede volver

    #: Compatibilidad con la v1. Lo que manda es `self.sitio.marcas_modal`.
    MODALES = VENICE.marcas_modal

    def modal_login_visible(self) -> bool:
        try:
            cuerpo = self.pg.inner_text("body")
        except Exception:                                # noqa: BLE001
            return False
        return any(m in cuerpo for m in self.sitio.marcas_modal)

    def asegurar_guest(self) -> None:
        """Si el modal de sesión está, se vuelve a entrar como Guest."""
        if not self.modal_login_visible():
            return
        self._progreso("[puerta] la sesión Guest caducó; reentrando…")
        self._entra_guest()
        self._espera_chat()

    def enviar(self, texto: str) -> None:
        """Asegura Guest, escribe y envía. Corre en el hilo navegador."""
        self.asegurar_guest()
        ta = self.pg.locator(self.sitio.selector_entrada).first
        ta.fill(texto)
        ta.press("Enter")

    def _espera_chat(self) -> None:
        limite = time.monotonic() + PLAZO_ARRANQUE_S
        while time.monotonic() < limite:
            if self.pg.locator(self.sitio.selector_entrada).count() > 0:
                return
            time.sleep(1.5)
        cuerpo = self.pg.inner_text("body")[:300]
        raise SesionNoDisponible(
            f"el chat no apareció en {PLAZO_ARRANQUE_S:.0f}s. "
            f"Lo visible: {cuerpo!r}")

    # ------------------------------------------------------------ cierre

    def cerrar(self) -> None:
        """Bloqueante (hilo aparte o to_thread). Idempotente."""
        if self._hilo is None:
            return
        try:
            self.llamar(self._apaga)
        except Exception:                                # noqa: BLE001
            self._apaga()
        self._cola.put(None)
        self._hilo.join(timeout=10)
        self._hilo = None

    # --------------------------------------------------------- tanteo

    def cupo_agotado(self) -> bool:
        """Bloqueante. ¿Dice la página que hoy no queda ración?"""
        try:
            cuerpo = self.pg.inner_text("body")
        except Exception:                                # noqa: BLE001
            return False
        return any(m.lower() in cuerpo.lower()
                   for m in self.sitio.marcas_cupo)
