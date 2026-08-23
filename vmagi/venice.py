"""Cliente Venice SIN CLAVE: opera la página viva del Guest.

Todo pasa dentro del Edge real (la puerta): la atestación, los cupos y
los formatos los gestiona la propia web de Venice. Este módulo escribe
el prompt, espera y recoge — siempre DELEGANDO al hilo del navegador
(Playwright Sync API no puede correr dentro del bucle asyncio).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from . import config, sesion


class VeniceError(Exception):
    def __init__(self, msg: str, estado: int | None = None):
        super().__init__(msg)
        self.estado = estado


class CupoDiarioAgotado(VeniceError):
    """El Guest de Venice agotó su ración de hoy. Toca volver mañana."""


#: src, ancho, alto y clase de cada <img>: para distinguir la imagen
#: GENERADA (grande) de los iconos de la interfaz (clerk, logos, 0x0).
_JS_ATRS = ("els => els.map(e => [e.src, e.clientWidth, e.clientHeight, "
            "(e.className||'').toString()])")


@dataclass
class ChatResp:
    texto: str
    modelo: str
    ms: float


def _traduce_cierre(fn):
    """Decorador de las esperas: ventana cerrada → mensaje claro."""
    import functools

    @functools.wraps(fn)
    def envoltura(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:                            # noqa: BLE001
            if "closed" in str(e).lower() or "Target" in type(e).__name__:
                raise VeniceError(
                    "la ventana del Edge de la puerta se cerró en mitad de "
                    "la operación. Ejecuta /sesion para reabrirla y repite "
                    "la petición.") from e
            raise
    return envoltura


def _lectura_segura(p, fn, intentos: int = 3):
    """Lee de la página tolerando la navegación del primer envío.

    Enviar el primer mensaje hace que /chat/classic salte a /chat/classic/
    <id>: el contexto de ejecución anterior se destruye y un poll que caiga
    justo ahí muere con «Execution context was destroyed». Es transitorio:
    el siguiente poll ya corre sobre la página nueva.
    """
    ultimo = None
    for _ in range(intentos):
        try:
            return p.llamar(fn)
        except Exception as e:                            # noqa: BLE001
            if "destroyed" in str(e).lower() or "navigation" in str(e).lower():
                ultimo = e
                time.sleep(1.5)
                continue
            raise
    raise VeniceError(f"la página navegó y no se dejó leer: {ultimo}")


#: Caché LRU de chats: repetir la misma pregunta no gasta ración.
_CACHE: dict[tuple, str] = {}
_CACHE_MAX = 64


def cache_consulta(clave: tuple) -> str | None:
    v = _CACHE.get(clave)
    if v is not None:
        _CACHE[clave] = _CACHE.pop(clave)      # LRU: lo usado, al final
    return v


def cache_guarda(clave: tuple, valor: str) -> None:
    _CACHE[clave] = valor
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))


class Venice:
    """Cliente que habla con Venice a través de la página viva del Guest."""

    def __init__(self, progreso=None):
        self._progreso = progreso or (lambda m: None)
        self._puerta: sesion.Puerta | None = None
        #: ración vista desde fuera: cuántos chats REALES (sin caché) hoy
        self.hoy = time.strftime("%Y-%m-%d")
        self.llamadas_hoy = 0

    # ---------------------------------------------------------- puerta

    def _asegura_puerta(self) -> sesion.Puerta:
        if self._puerta is None:
            self._puerta = sesion.Puerta(self._progreso)
        return self._puerta

    async def _abrir(self) -> sesion.Puerta:
        p = self._asegura_puerta()
        if p.pg is None:
            await asyncio.to_thread(p.abrir)
        return p

    async def cerrar(self) -> None:
        if self._puerta is not None:
            await asyncio.to_thread(self._puerta.cerrar)
            self._puerta = None

    async def _tantea_cupo(self) -> None:
        p = self._asegura_puerta()
        if p.pg is not None and await asyncio.to_thread(p.cupo_agotado):
            raise CupoDiarioAgotado(
                "Venice Guest agotó su cupo de HOY (lo raciona Venice por "
                "día, no el sistema). Vuelve mañana, o usa una cuenta/clave "
                "de API para más.")

    # ------------------------------------------------------------- chat

    async def chat(self, sistema: str, usuario: str, **_) -> ChatResp:
        t0 = time.monotonic()
        p = await self._abrir()
        prompt = f"{sistema}\n\n---\n\n{usuario}"[:7000]
        # La sesión Guest caduca y el modal de login puede saltar EN CUALQUIER
        # momento (medido): se reintenta reentrando como Guest, no pidiendo
        # credenciales que no existen.
        ultimo: Exception | None = None
        for _ in range(2):
            previo = await asyncio.to_thread(
                _lectura_segura, p, lambda: p.pg.inner_text("body"))
            await asyncio.to_thread(p.llamar, lambda: p.enviar(prompt))
            try:
                respuesta = await asyncio.to_thread(
                    self._espera_respuesta, p, previo, prompt, 120.0)
                await self._tantea_cupo()
                cache_guarda(clave, respuesta)
                hoy = time.strftime("%Y-%m-%d")
                if hoy != self.hoy:
                    self.hoy = hoy
                    self.llamadas_hoy = 0
                self.llamadas_hoy += 1
                return ChatResp(texto=respuesta, modelo="venice-guest",
                                ms=(time.monotonic() - t0) * 1000)
            except sesion.ModalDeLogin as e:
                ultimo = e
        # Medido: reentrar como Guest nuevo NO recupera cupo — la ración
        # es por IP y por día. Si el modal vuelve tras reentrar, es el
        # cupo, y hay que decirlo, no pelear contra el muro.
        raise CupoDiarioAgotado(
            "Venice pidió iniciar sesión tras reintentar como Guest: el "
            "cupo diario (por IP) se ha agotado hoy. Vuelve mañana."
        ) from ultimo

    @_traduce_cierre
    def _espera_respuesta(self, p: sesion.Puerta, previo: str,
                          prompt: str, plazo_s: float) -> str:
        """CORRE EN EL HILO DEL NAVEGADOR: espera la RESPUESTA, no el eco.

        Medido: con historial acumulado, el eco del propio prompt aparece
        en el cuerpo y ESTABILIZA antes de que la respuesta empiece a
        fluir — dos lecturas iguales devolvían el eco como respuesta.
        Dos defensas: el eco se resta del candidato (y si no queda nada,
        se sigue esperando), y el fin exige TRES lecturas iguales.
        """
        limite = time.monotonic() + plazo_s
        estable = ""
        rachas = 0
        while time.monotonic() < limite:
            time.sleep(3.0)
            cuerpo = _lectura_segura(p, lambda: p.pg.inner_text("body"))
            if len(cuerpo) <= len(previo) + 40:
                continue               # aún no llega ni el eco
            if "Inicia sesión en tu cuenta" in cuerpo or                     "Email address" in cuerpo:
                raise sesion.ModalDeLogin("el modal apareció a mitad")
            if cuerpo == estable:
                rachas += 1
                if rachas >= 3:        # 3 lecturas iguales: fluyo y acabó
                    return self._sin_eco(cuerpo[len(previo):], prompt)
            else:
                rachas = 0
            estable = cuerpo
        return self._sin_eco(estable[len(previo):], prompt)

    MIN_RESPUESTA = 40

    def _sin_eco(self, nuevo: str, prompt: str) -> str:
        """Quita el eco y las marcas de UI.

        Menos de MIN_RESPUESTA caracteres útiles no es una respuesta del
        modelo — era el eco o la UI. Devolverlo hizo degenerar al enjambre
        (un rol «respondía» con su propio contrato): se lanza el error
        claro en su lugar.
        """
        texto = self._limpia(nuevo)
        if prompt and prompt.strip():
            texto = texto.replace(prompt.strip(), "").strip()
        if len(texto) < self.MIN_RESPUESTA:
            raise VeniceError(
                "Venice no contestó con una respuesta real (solo se vio el "
                "eco de la orden o nada). ¿Cupo del día agotado o respuesta "
                "en curso? Revisa la ventana del Edge y reintenta.")
        return texto

    @staticmethod
    def _limpia(t: str) -> str:
        for marca in ("Ask anything privately", "Pregunte cualquier cosa",
                      "Automático", "Auto\n", "Get Pro Access",
                      "Obtener acceso a Pro"):
            if marca in t:
                t = t.split(marca)[0]
        return t.strip()

    # ----------------------------------------------------------- imagen

    async def imagen(self, prompt: str, *, destino: Path | None = None,
                     **_) -> Path:
        """Genera una imagen pidiéndola en el chat del Guest."""
        p = await self._abrir()
        texto = (f"Genera UNA imagen, sin texto: {prompt}")
        ultimo = None
        for _ in range(2):
            # Muestrear ANTES de enviar: el Enter navega y destruye el
            # contexto de ejecución del muestreo.
            conocidas = await asyncio.to_thread(
                _lectura_segura, p, lambda: p.pg.locator("img").evaluate_all(
                    _JS_ATRS))
            await asyncio.to_thread(p.llamar, lambda: p.enviar(texto))
            try:
                ruta = await asyncio.to_thread(self._espera_imagen, p,
                                               conocidas, 240.0)
                await self._tantea_cupo()
                return ruta
            except sesion.ModalDeLogin as e:
                ultimo = e
        raise CupoDiarioAgotado(
            "Venice pidió iniciar sesión tras reintentar como Guest: el "
            "cupo diario (por IP) se ha agotado hoy. Vuelve mañana."
        ) from ultimo

    @_traduce_cierre
    def _espera_imagen(self, p: sesion.Puerta, conocidas: list,
                       plazo_s: float) -> Path:
        """CORRE EN EL HILO DEL NAVEGADOR: espera la imagen generada.

        Duro contra los iconos de UI (medido: el logo de Clerk del modal
        de login y el de Venice se cuelan como <img> nuevos): una imagen
        generada se ve GRANDE en pantalla y no viene de img.clerk.com.
        """
        def _valida(atrs) -> bool:
            src, ancho, alto, clase = atrs[0], atrs[1], atrs[2], atrs[3]
            if not src or not src.startswith(("http", "data:", "blob:")):
                return False
            if "clerk" in src or "cl-" in clase:
                return False
            if any(x in src for x in ("favicon", "logo", "icon", "sprite")):
                return False
            return ancho >= 200 and alto >= 200

        limite = time.monotonic() + plazo_s
        while time.monotonic() < limite:
            time.sleep(4.0)
            if p.modal_login_visible():
                raise sesion.ModalDeLogin("modal durante la imagen")
            actuales = _lectura_segura(
                p, lambda: p.pg.locator("img").evaluate_all(_JS_ATRS))
            nuevas = [a for a in actuales if a not in conocidas and _valida(a)]
            if nuevas:
                return self._baja(nuevas[-1][0])
        # El fallo opaco se vuelve evidencia: QUÉ mostraba la página.
        diagnostico = config.media_dir() / f"diagnostico_{int(time.time())}.png"
        try:
            p.llamar(lambda: p.pg.screenshot(path=str(diagnostico)))
        except Exception:                                # noqa: BLE001
            diagnostico = None
        donde = f" Captura de lo que mostraba la página: {diagnostico}"             if diagnostico else ""
        raise VeniceError(
            "la imagen no apareció en el plazo. ¿Cupo de imágenes agotado "
            "por hoy, o el chat pidió aclarar el modo imagen?" + donde)

    @staticmethod
    def _baja(src: str) -> Path:
        destino = config.media_dir() / f"img_{int(time.time())}.png"
        if src.startswith("data:"):
            import base64
            destino.write_bytes(base64.b64decode(src.split(",", 1)[1]))
        else:
            import httpx
            r = httpx.get(src, timeout=60, follow_redirects=True)
            destino.write_bytes(r.content)
        return destino

    # ------------------------------------------------------------ vídeo

    async def video(self, prompt: str, **_) -> Path:
        raise VeniceError(
            "Venice reserva el vídeo para cuentas Pro/clave: el Guest no "
            "lo genera. La imagen sí funciona (/imagen). Para vídeo: "
            "cuenta Venice Pro o clave de API (venice.ai/settings/api).")

    # ----------------------------------------------------------- modelos

    async def modelos(self) -> list[str]:
        await self._abrir()
        return ["venice-guest"]        # el Guest usa el modelo automático
