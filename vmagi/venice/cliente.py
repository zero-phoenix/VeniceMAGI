"""Cliente Venice SIN CLAVE: opera la página viva del Guest.

Todo pasa dentro del Edge real (la puerta): la atestación, los cupos y
los formatos los gestiona la propia web de Venice. Este módulo escribe
el prompt, espera y recoge — siempre DELEGANDO al hilo del navegador
(Playwright Sync API no puede correr dentro del bucle asyncio).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from . import puerta as sesion
from .contenedor import CloudModelContainer
from .medios import ImagePipelineService, SeedanceVideoService
from .privacidad import NotrackProvider
from .racion import racion_de
from .sitios import VENICE, SitioGuest


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
    #: Caracteres que NO llegaron al proveedor porque el prompt excedía el
    #: límite. Cero es la respuesta normal. Distinto de cero significa que
    #: el modelo contestó sobre un encargo incompleto, y quien lea la
    #: respuesta tiene derecho a saberlo antes de creérsela.
    recortado: int = 0


#: Tope de caracteres que se le manda de una vez a un sitio guest. No es una
#: cifra teórica: por encima de esto la caja de texto de la web se atraganta.
LIMITE_PROMPT = 7000

#: Cuánto del final se conserva cuando hay que recortar. El final es donde
#: viven las restricciones y la evidencia; la cabecera suele ser rol y estilo,
#: que el modelo puede inferir. Si hay que perder algo, que sea de en medio.
COLA_PROMPT = 2200


def recorta_prompt(texto: str, limite: int = LIMITE_PROMPT,
                   cola: int = COLA_PROMPT) -> tuple[str, int]:
    """Ajusta un prompt al límite del sitio guest SIN decapitarlo en silencio.

    EL FALLO QUE ESTO CIERRA
    ========================
    La línea era `prompt = f"{sistema}\\n\\n---\\n\\n{usuario}"[:7000]`. Un
    corte por el final, sin aviso, sin registro y sin que nadie se enterase.
    Ya figura en `docs/AUTOMODELO.json` como afirmación **refutada**: «El
    prompt llega entero al proveedor guest».

    Lo que se perdía no era relleno. En este sistema, lo que viaja al final
    de un prompt es justo lo que más pesa: la evidencia que Balthasar usa
    para refutar, la lista de promesas incumplidas del reintento dirigido
    del taller, y —en cuanto haya biblia de estilo— las restricciones de
    dirección artística. El nodo contestaba sobre medio encargo creyendo
    que lo tenía entero, y la respuesta salía coherente consigo misma, que
    es exactamente el modo de fallo que no se ve.

    Tres cambios sobre el `[:7000]`:

    1. **Se conserva la cola.** Cabeza y final; lo que se sacrifica es el
       centro, que es donde suele estar el desarrollo redundante.
    2. **Se dice, dentro del propio prompt.** El modelo lee un marcador
       explícito de cuánto falta. Un texto fundido sin costuras esconde
       justo el trozo que falló — la misma regla que ya aplican los
       subagentes.
    3. **Se devuelve el número.** El llamador lo propaga en `ChatResp` y
       queda en la traza. «No he podido comprobarlo» no es «está bien».
    """
    n = len(texto)
    if n <= limite:
        return texto, 0

    cola = max(0, min(cola, limite // 2))

    def _marca(perdidos: int) -> str:
        return (f"\n\n[... RECORTADO: {perdidos} caracteres del centro no "
                f"caben en el límite de {limite} de este proveedor. Responde "
                f"solo con lo que sí tienes y di qué te falta. ...]\n\n")

    # EL FALLO QUE ESTA CUENTA CIERRA, y lo cazó su propio test.
    #
    # El primer intento descontaba del presupuesto un marcador de ejemplo
    # («[... RECORTADO: 0 caracteres del centro ...]», 48 caracteres) y luego
    # insertaba el de verdad, que con la frase entera pasa de 160. Resultado
    # medido: con 7001 caracteres de entrada salían 7096, es decir, la función
    # que existe para respetar el tope lo rebasaba — y lo rebasaba justo por
    # el texto que avisa de que no lo rebasa.
    #
    # Se descuenta el marcador CON el número más ancho posible, que es el de
    # perder el texto entero. El real solo puede tener los mismos dígitos o
    # menos, así que el resultado nunca crece por encima de lo presupuestado.
    reserva = len(_marca(n))
    hueco = limite - cola - reserva
    if hueco <= 0:
        # Límite tan pequeño que no cabe ni el aviso: se corta y se dice.
        return texto[:limite], n - limite

    cabeza = texto[:hueco]
    final = texto[n - cola:] if cola else ""
    perdidos = n - len(cabeza) - len(final)
    return cabeza + _marca(perdidos) + final, perdidos


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


# Aquí vivían `cache_consulta` y `cache_guarda`, dos envoltorios «de
# compatibilidad con la v1». No los llamaba nadie: la v1 no sobrevive a este
# repositorio, así que la compatibilidad era con un pasado que no existe. Los
# cazó el trinquete de huérfanos y se borraron en el mismo commit.
#
# La caché vive en `racion.py`, una por sitio, y se usa desde `Venice.chat`.


class Venice:
    """Cliente que opera un sitio guest a través de su página viva.

    Se llama `Venice` por historia y porque Venice es el camino principal,
    pero el sitio es un parámetro: la misma clase opera notrack.ai. Lo
    que cambia entre uno y otro está en `sitios.py`, no aquí.
    """

    def __init__(self, progreso=None, sitio: SitioGuest | None = None):
        self._progreso = progreso or (lambda m: None)
        self._puerta: sesion.Puerta | None = None
        self.sitio = sitio or VENICE
        self.racion = racion_de(self.sitio.nombre)
        # servicios del pipeline HQ del usuario (A1111/ComfyUI + Seedance)
        self._privacy = NotrackProvider()
        self._image = ImagePipelineService(self._privacy)
        self._video = SeedanceVideoService(self._privacy)
        self._cloud = CloudModelContainer(self)

    # ------------------------------- ración vista desde fuera (compat v1)

    @property
    def hoy(self) -> str:
        return self.racion.estado()["dia"]

    @property
    def llamadas_hoy(self) -> int:
        return self.racion.estado()["llamadas_hoy"]

    # ---------------------------------------------------------- puerta

    def _asegura_puerta(self) -> sesion.Puerta:
        if self._puerta is None:
            self._puerta = sesion.Puerta(self._progreso, sitio=self.sitio)
        return self._puerta

    def sesion_activa(self) -> bool:
        return self._puerta is not None and self._puerta.pg is not None

    def etiqueta_provider_chat(self) -> str:
        estado = "activo" if self.sesion_activa() else "inactivo"
        return f"{self.sitio.nombre}-guest ({estado})"

    def etiqueta_container(self) -> str:
        if config.cloud_only_mode():
            return self._cloud.etiqueta_container()
        return "hybrid-local-cloud"

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
                f"{self.sitio.nombre} Guest agotó su cupo de HOY (lo raciona "
                "el proveedor por día, no el sistema). Vuelve mañana. El "
                "sistema no rota IP ni perfiles para esquivarlo.")

    # ------------------------------------------------------------- chat

    async def chat(self, sistema: str, usuario: str, **kw) -> ChatResp:
        """Una pregunta al sitio guest. La caché SE CONSULTA primero.

        EL FALLO QUE ESTO CIERRA. La v1 llamaba a `cache_guarda(clave, ...)`
        con `clave` sin definir en ningún sitio y sin consultar la caché
        jamás: cada chat correcto moría con `NameError` justo después de
        haber gastado la ración, y la caché LRU que el README anuncia no
        se usaba ni una vez. Ahora la clave se calcula, se consulta antes
        de abrir la puerta —repetir no gasta cupo, que es todo el punto— y
        solo se guarda lo que de verdad contestó el modelo.
        """
        t0 = time.monotonic()
        clave = (self.sitio.nombre, sistema.strip(), usuario.strip())
        guardada = self.racion.consulta(clave)
        if guardada is not None:
            return ChatResp(texto=guardada,
                            modelo=f"{self.sitio.nombre}-guest (caché)",
                            ms=(time.monotonic() - t0) * 1000)

        p = await self._abrir()
        prompt, recortado = recorta_prompt(f"{sistema}\n\n---\n\n{usuario}")
        if recortado:
            logging.getLogger(__name__).warning(
                "[%s] prompt recortado: %d caracteres del centro no viajaron",
                self.sitio.nombre, recortado)
        # La sesión Guest caduca y el modal de login puede saltar EN CUALQUIER
        # momento (medido): se reintenta reentrando como Guest, no pidiendo
        # credenciales que no existen.
        ultimo: Exception | None = None
        for _intento in range(2):
            previo = await asyncio.to_thread(
                _lectura_segura, p, lambda: p.pg.inner_text("body"))
            await asyncio.to_thread(p.llamar, lambda: p.enviar(prompt))
            try:
                respuesta = await asyncio.to_thread(
                    self._espera_respuesta, p, previo, prompt, 120.0)
                await self._tantea_cupo()
                self.racion.guarda(clave, respuesta)
                self.racion.apunta_llamada()
                return ChatResp(texto=respuesta,
                                modelo=f"{self.sitio.nombre}-guest",
                                ms=(time.monotonic() - t0) * 1000,
                                recortado=recortado)
            except sesion.ModalDeLogin as e:
                ultimo = e
        # Medido: reentrar como Guest nuevo NO recupera cupo — la ración
        # es por IP y por día. Si el modal vuelve tras reentrar, es el
        # cupo, y hay que decirlo, no pelear contra el muro.
        raise CupoDiarioAgotado(
            f"{self.sitio.nombre} pidió iniciar sesión tras reintentar como "
            "Guest: el cupo diario (por IP) se ha agotado hoy. Vuelve mañana."
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
            if any(m in cuerpo for m in self.sitio.marcas_modal):
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
                f"{self.sitio.nombre} no contestó con una respuesta real "
                "(solo se vio el eco de la orden o nada). ¿Cupo del día "
                "agotado o respuesta en curso? Revisa la ventana del Edge "
                "y reintenta.")
        return texto

    def _limpia(self, t: str) -> str:
        """Recorta los adornos de la interfaz DEL SITIO, no de Venice.

        Eran seis constantes de la web de Venice metidas en un
        `@staticmethod`: aplicadas a notrack.ai no recortaban nada y su
        pie de página se colaba dentro de la respuesta.
        """
        for marca in self.sitio.marcas_ui:
            if marca in t:
                t = t.split(marca)[0]
        return t.strip()

    # ----------------------------------------------------------- imagen

    async def imagen(self, prompt: str, *, refs: list[Path] | None = None,
                     aspect_ratio: str = "1:1", seed: int | None = None,
                     **_) -> Path:
        """Genera imagen en modo cloud-only o híbrido según configuración."""
        if config.cloud_only_mode():
            return await self._cloud.imagen(
                prompt, aspect_ratio=aspect_ratio, seed=seed
            )
        return await self._image.generar(prompt, refs=refs,
                                         aspect_ratio=aspect_ratio, seed=seed,
                                         quality=_.get("quality"),
                                         backend=_.get("backend"))

    async def _imagen_guest(self, prompt: str, *, aspect_ratio: str = "1:1",
                            seed: int | None = None) -> Path:
        """Pide una imagen a la página viva del sitio.

        Un sitio que no genera imagen lo dice en `sitios.py` y aquí se
        rechaza con su nombre. Antes se intentaba igual y el fallo salía
        240 s más tarde como «la imagen no apareció en el plazo», que es
        la respuesta correcta a la pregunta equivocada.
        """
        if not self.sitio.imagen:
            raise VeniceError(
                f"{self.sitio.nombre} no genera imágenes ({self.sitio.nota}). "
                "Para imagen usa un sitio que la declare, o `/modo hybrid` "
                "con un backend local.")
        p = await self._abrir()
        texto = (f"Genera UNA imagen, sin texto, aspect ratio {aspect_ratio}: {prompt}")
        if seed is not None:
            texto += f" (seed {seed})"
        ultimo = None
        for _intento in range(2):
            conocidas = await asyncio.to_thread(
                _lectura_segura, p, lambda: p.pg.locator("img").evaluate_all(
                    _JS_ATRS))
            await asyncio.to_thread(p.llamar, lambda: p.enviar(texto))
            try:
                ruta = await asyncio.to_thread(self._espera_imagen, p,
                                               conocidas, 240.0)
                await self._tantea_cupo()
                self.racion.apunta_llamada()
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
            px = config.notrack_proxy()
            kw = {"proxy": px} if px else {}
            r = httpx.get(src, timeout=60, follow_redirects=True, **kw)
            destino.write_bytes(r.content)
        return destino

    # ------------------------------------------------------------ vídeo

    async def video(self, prompt: str, **_) -> Path:
        if config.cloud_only_mode():
            return await self._cloud.video(prompt, **_)
        return await self._video.generar(
            prompt,
            duration=_.get("duration", "10s"),
            ref_urls=_.get("ref_urls"),
        )

    @staticmethod
    def _error_video_cloud_only() -> VeniceError:
        return VeniceError(
            "Modo cloud-only activo: vídeo gratis sin key/login no está "
            "disponible en el proveedor guest actual. "
            "El sistema no usa modelos locales ni bypass de cuotas."
        )

    # ----------------------------------------------------------- modelos

    async def modelos(self) -> list[str]:
        await self._abrir()
        # El Guest usa el modelo automático del sitio: no hay lista que
        # pedirle. Se devuelve el nombre real para que la traza diga qué
        # respondió de verdad, que es la regla de la interfaz.
        return [f"{self.sitio.nombre}-guest"]

    def estado(self) -> dict:
        """Lo que `/salud` enseña de este cliente, sin interpretar."""
        return {
            "sitio": self.sitio.nombre,
            "familia": self.sitio.familia,
            "url": self.sitio.url,
            "capacidades": list(self.sitio.capacidades()),
            "sesion_activa": self.sesion_activa(),
            "contenedor": self.etiqueta_container(),
            "racion": self.racion.estado(),
            "nota": self.sitio.nota,
        }
