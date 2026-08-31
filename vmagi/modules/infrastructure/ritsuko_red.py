"""La salida de red de VeniceMAGI: una sola puerta, para todo, o ninguna.

ANONIMATO ABSOLUTO, Y QUE SIGNIFICA EXACTAMENTE
===============================================
El principio del sistema es anonimato absoluto en todo sentido. Eso no es
una postura: es una lista de cosas concretas que el programa hace y deja
de hacer, y cada una tiene su freno en este modulo o en el que se cita.

  1. **Sin cuenta y sin clave.** El camino principal son sitios guest.
     No hay login que filtre quien eres.   -> `venice/sitios.py`
  2. **Una sola salida de red, para TODO.** Si el usuario configura una
     VPN o un proxy, sale por ahi el trafico del enjambre, el de la
     puerta de Edge y el de las descargas. Una sola puerta.  -> aqui
  3. **Nada de trafico partido.** Media aplicacion por la VPN y la otra
     media por la linea de casa correlaciona las dos y anula la VPN. Con
     `RITSUKO_VPN_ESTRICTA=1` no se sale por ninguna otra parte.  -> aqui
  4. **Sin telemetria.** El programa no manda nada a nadie sobre su uso.
     Lo que se mide se queda en `%LOCALAPPDATA%`.  -> `core/obs/`
  5. **Sin huella entre sesiones.** Perfil de navegador efimero opcional,
     historial y cache borrables de un comando.  -> `purga()` aqui abajo
  6. **Credenciales fuera de los informes.** Un proxy con usuario y
     contrasena se enmascara antes de escribirse.  -> `_enmascarada()`

QUIEN LA GOBIERNA, Y POR QUE ES RITSUKO
=======================================
Ritsuko es la auditora: no escribe codigo, no toca el reparto del
enjambre y no ejecuta nada. Justamente por eso es quien puede llevar la
salida de red — es la unica pieza del sistema cuyo trabajo es mirar el
conjunto, y la salida de red es una propiedad del conjunto, no de un
nodo. Ponerla en el enjambre habria dado tres puertas distintas.

LO QUE NO SE HACE AUTOMATICAMENTE, Y NO ES UN PRINCIPIO SINO INGENIERIA
=======================================================================
La salida la fija el usuario y no cambia sola al recibir un 429 o un
bloqueo. No es una regla moral del proyecto: es que hacerlo automatico
convierte una VPN en una herramienta de fuerza bruta contra la racion de
un servicio gratuito, y lo que se gana —unas llamadas mas hoy— se paga
con la IP quemada y el proveedor cerrando el guest para todos. El usuario
puede cambiar de salida cuando quiera, por el motivo que quiera, con
`/vpn`. Lo que no hay es un bucle que lo haga por su cuenta.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["SalidaDeRed", "SalidaNoDisponible", "salida_de_ritsuko",
           "ESQUEMAS", "aplica_a_httpx", "aplica_a_navegador",
           "variables_de_entorno"]

#: Esquemas admitidos. Un esquema fuera de esta lista se rechaza al fijarlo,
#: no al usarlo: un proxy mal escrito que solo falla en la primera llamada
#: real es un fallo que aparece justo cuando no puedes depurarlo.
ESQUEMAS = ("http", "https", "socks5", "socks5h", "socks4")

#: Salidas gratuitas que funcionan sin registrarse, para el mensaje de ayuda.
#: No es una lista de proxys publicos que el programa vaya a probar solo —eso
#: seria elegir por el usuario por donde sale su trafico, que es lo contrario
#: del anonimato— sino las formas conocidas de tener una.
SALIDAS_CONOCIDAS = (
    ("Tor",       "socks5://127.0.0.1:9050",
     "gratis, sin cuenta; arranca Tor Browser o el servicio `tor`"),
    ("WireGuard", "(ninguna)",
     "el cliente enruta la maquina entera: aqui no hace falta configurar nada"),
    ("Proxy propio", "http://127.0.0.1:8080",
     "cualquier proxy HTTP o SOCKS5 que tengas levantado"),
)

_RE_URL = re.compile(r"^(?P<esquema>[a-z0-9]+)://(?P<resto>[^\s/]+)/?$", re.I)


class SalidaNoDisponible(RuntimeError):
    """Modo estricto activo y no hay salida configurada."""


@dataclass
class SalidaDeRed:
    """La puerta de red del sistema entero. Se fija a mano."""

    url: str = ""
    origen: str = "sin configurar"
    #: Modo estricto: sin salida configurada, NO se sale a la red. Es la
    #: diferencia entre «uso VPN» y «uso VPN salvo cuando falle», que para
    #: el anonimato es la diferencia entre servir y no servir.
    estricta: bool = False
    #: Cada cambio queda apuntado. El informe de Ritsuko lo publica: una
    #: politica de red que nadie puede leer no es una politica.
    bitacora: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------- estado

    @property
    def configurada(self) -> bool:
        return bool(self.url)

    def httpx_kwargs(self) -> dict:
        """Lo que se le pasa a httpx. Vacio si no hay salida propia.

        En modo estricto, no haber salida es un ERROR y no un «sal por
        donde puedas»: caer a la linea de casa sin avisar es justo la
        fuga que el modo estricto existe para impedir.
        """
        if self.url:
            return {"proxy": self.url}
        if self.estricta:
            raise SalidaNoDisponible(
                "modo estricto: no hay salida de red configurada y el "
                "sistema no sale por la linea directa. Fija una con "
                "`/vpn socks5://127.0.0.1:9050` o desactiva el modo "
                "estricto con `/vpn estricto off`.")
        return {}

    def estado(self) -> dict:
        return {
            "configurada": self.configurada,
            "salida": self._enmascarada(),
            "origen": self.origen,
            "estricta": self.estricta,
            "alcance": "todo el sistema (enjambre, puerta de Edge y descargas)",
            "cambios": len(self.bitacora),
        }

    def _enmascarada(self) -> str:
        """La URL sin credenciales.

        Un proxy con usuario y contrasena dentro del informe seria una
        fuga de credenciales en el fichero que existe precisamente para
        que el usuario lo descargue y lo comparta.
        """
        if not self.url:
            return ""
        return re.sub(r"//[^@/]+@", "//***@", self.url)

    # -------------------------------------------------------------- fijar

    @staticmethod
    def valida(url: str) -> str:
        u = (url or "").strip()
        if not u:
            return ""
        m = _RE_URL.match(u)
        if not m or m.group("esquema").lower() not in ESQUEMAS:
            ejemplos = "\n".join(f"    {n:<14} {u_}   ({q})"
                                 for n, u_, q in SALIDAS_CONOCIDAS)
            raise ValueError(
                f"salida invalida: {url!r}. Formato: esquema://host:puerto "
                f"con esquema en {', '.join(ESQUEMAS)}.\n"
                f"Salidas gratuitas conocidas:\n{ejemplos}")
        return u

    def fija(self, url: str | None, *, origen: str = "usuario") -> str:
        """Fija (o borra con None) la salida. La decide el usuario."""
        nueva = self.valida(url or "")
        anterior = self.url
        self.url = nueva
        self.origen = origen if nueva else "sin configurar"
        self.bitacora.append({"de": anterior, "a": nueva, "motivo": origen})
        del self.bitacora[:-50]
        logger.info("[red] salida fijada por %s: %s",
                    origen, self._enmascarada() or "(ninguna)")
        return nueva

    def fija_estricta(self, valor: bool) -> bool:
        self.estricta = bool(valor)
        self.bitacora.append({"de": self.url, "a": self.url,
                              "motivo": f"estricta={self.estricta}"})
        return self.estricta

    # ------------------------------------------------------ configuracion

    @classmethod
    def desde_entorno(cls) -> SalidaDeRed:
        """Lee la salida configurada. En orden, gana el primero.

        1. `RITSUKO_VPN`   — la salida del sistema
        2. `ritsuko_vpn`   en config.json
        3. `NOTRACK_PROXY` / `notrack_proxy` — se hereda, porque tener una
           salida es mejor que no tenerla y este es el ajuste que ya
           existia.
        """
        s = cls()
        s.estricta = _verdad(os.environ.get("RITSUKO_VPN_ESTRICTA")
                             or _config().get("ritsuko_vpn_estricta"))
        for valor, origen in (
            (os.environ.get("RITSUKO_VPN"), "entorno RITSUKO_VPN"),
            (_config().get("ritsuko_vpn"), "config.json ritsuko_vpn"),
            (os.environ.get("NOTRACK_PROXY"), "entorno NOTRACK_PROXY"),
            (_config().get("notrack_proxy"), "config.json notrack_proxy"),
        ):
            if (valor or "").strip():
                s.fija(valor.strip(), origen=origen)
                break
        return s

    def guarda(self) -> None:
        d = _config()
        if self.url:
            d["ritsuko_vpn"] = self.url
        else:
            d.pop("ritsuko_vpn", None)
        d["ritsuko_vpn_estricta"] = self.estricta
        _escribe_config(d)

    # ------------------------------------------------------------- huella

    @staticmethod
    def purga(incluye_perfiles: bool = True) -> dict:
        """Borra la huella local: perfiles de navegador, cache y logs.

        Anonimato no es solo hacia fuera. Un perfil de Edge persistente
        guarda cookies y almacenamiento local del sitio guest entre
        sesiones, que es una huella estable aunque el trafico salga por
        una VPN: el sitio te reconoce sin necesidad de tu IP.
        """
        from vmagi.core.paths import cache_dir, data_dir, logs_dir

        borrado = {"perfiles": 0, "cache": 0, "logs": 0}
        base = Path(data_dir())
        if incluye_perfiles:
            for p in base.glob("perfil-edge*"):
                shutil.rmtree(p, ignore_errors=True)
                borrado["perfiles"] += 1
        for etiqueta, carpeta in (("cache", cache_dir()), ("logs", logs_dir())):
            for f in Path(carpeta).glob("*"):
                try:
                    if f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
                    else:
                        f.unlink()
                    borrado[etiqueta] += 1
                except OSError:
                    pass
        logger.info("[red] huella purgada: %s", borrado)
        return borrado


def _verdad(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "on", "si", "yes")


def _ruta_config() -> Path:
    from vmagi.core.paths import data_dir
    return Path(data_dir()) / "config.json"


def _config() -> dict:
    f = _ruta_config()
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _escribe_config(d: dict) -> None:
    _ruta_config().write_text(json.dumps(d, indent=1, ensure_ascii=False),
                              encoding="utf-8")


#: La salida del proceso. Una sola: dos instancias con URLs distintas harian
#: que «la salida del sistema» dependiese de quien preguntase, que es
#: exactamente el trafico partido que el punto 3 de la cabecera prohibe.
_SALIDA: SalidaDeRed | None = None


def salida_de_ritsuko(recargar: bool = False) -> SalidaDeRed:
    global _SALIDA
    if _SALIDA is None or recargar:
        _SALIDA = SalidaDeRed.desde_entorno()
    return _SALIDA


# ------------------------------------------------- como la usa cada capa
#
# Tres funciones y no una porque cada capa quiere la misma salida en un
# formato distinto: httpx la quiere como kwarg, Playwright como diccionario
# de lanzamiento, y un subproceso como variables de entorno. Escribirlas
# aqui juntas es lo que impide que una de las tres se quede atras — que es
# como se llega al trafico partido sin que nadie lo decida.

def aplica_a_httpx() -> dict:
    """kwargs de proxy para httpx/requests. Todo el HTTP del sistema."""
    return salida_de_ritsuko().httpx_kwargs()


def aplica_a_navegador() -> dict:
    """kwargs de proxy para el lanzamiento de Playwright (la puerta)."""
    s = salida_de_ritsuko()
    if s.url:
        return {"proxy": {"server": s.url}}
    if s.estricta:
        raise SalidaNoDisponible(
            "modo estricto: la puerta de Edge no se abre sin salida de red "
            "configurada, porque saldria por la linea directa y delataria "
            "la IP que la VPN oculta en el resto del sistema.")
    return {}


def variables_de_entorno() -> dict[str, str]:
    """`HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` para los subprocesos.

    Sin esto, un subproceso lanzado por una herramienta (git, pip, un
    script del usuario) sale por la linea directa mientras el resto del
    sistema va por la VPN. Eso es trafico partido, y basta una vez para
    correlacionar las dos rutas.
    """
    s = salida_de_ritsuko()
    if not s.url:
        return {}
    return {"HTTP_PROXY": s.url, "HTTPS_PROXY": s.url, "ALL_PROXY": s.url,
            "http_proxy": s.url, "https_proxy": s.url, "all_proxy": s.url}
