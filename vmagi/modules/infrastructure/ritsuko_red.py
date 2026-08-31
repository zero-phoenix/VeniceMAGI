"""La salida de red propia de Ritsuko: VPN o proxy, suyo y solo suyo.

POR QUE UNA AUDITORA NECESITA SU PROPIA PUERTA
==============================================
Ritsuko usa una familia de modelo que no comparte con nadie, y ese es
medio argumento. El otro medio es la red. Si su trafico sale por la misma
IP que el del enjambre, comparte con el auditado exactamente lo que mas
duele compartir:

- **La racion.** Venice y notrack racionan por IP y por dia. Con una
  salida comun, la tarea que agota el cupo deja muda a la auditora en el
  mismo instante — y ese instante, una tarea que agoto tres proveedores,
  es justo cuando hace falta un veredicto independiente. Ya paso: la
  auditoria del 20-ago encontro a Naoko declarando «deriva del modelo» en
  dos familias enteras justo despues de una tarea que habia agotado la
  cuota de esos mismos proveedores. Estaba midiendo su propia
  interferencia y llamandola averia. Una auditora que se cae con el
  auditado no sirve el dia que hace falta.
- **El bloqueo.** Si un proveedor corta esa IP, corta las dos.

Por eso Ritsuko puede tener su propia salida: VPN gratuita del usuario,
Tor, o un proxy HTTP/SOCKS. Es una puerta, no un disfraz.

LA LINEA QUE ESTE MODULO NO CRUZA, Y COMO SE HACE CUMPLIR
=========================================================
El manifiesto de VeniceMAGI dice, con todas las letras: **sin evasion de
cuotas (no rotacion automatica de IP/VPN)**. Una salida de red separada
es compatible con eso; rotarla cuando el proveedor dice «hoy no» NO lo es
— eso es exactamente burlar la racion de quien nos da el servicio gratis.

La diferencia no se deja a la buena voluntad de quien llame. Esta en el
codigo:

1. La salida se **configura a mano** (variable de entorno, config.json o
   el comando `/vpn`). El sistema nunca la elige ni la descubre solo.
2. `rota_por(motivo)` **rechaza** cualquier motivo relacionado con cuota,
   limite o bloqueo, y lo registra. No hay parametro que lo desactive.
3. La salida es de Ritsuko. No se aplica al enjambre, ni a la puerta de
   Edge, ni al trafico general: eso convertiria una medida de
   independencia en una de evasion.

`test_ritsuko_no_rota_por_cuota` comprueba las tres.

QUE VALE COMO SALIDA
====================
Cualquier cosa que hable HTTP o SOCKS5 en local. Lo normal:

    Tor Browser / tor          socks5://127.0.0.1:9050   (gratis)
    WireGuard / OpenVPN        el cliente enruta; aqui no hace falta nada
    Proxy del usuario          http://host:puerto
    El proxy de /notrack       se hereda si no hay uno propio

No hay listas de proxys publicos gratuitos embebidas, y es deliberado:
son inestables, a menudo hostiles (inyectan o registran trafico), y una
lista que rota sola es la rotacion automatica por la puerta de atras.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["SalidaDeRed", "RotacionProhibida", "salida_de_ritsuko",
           "MOTIVOS_PROHIBIDOS", "ESQUEMAS"]

#: Esquemas admitidos. Un esquema fuera de esta lista se rechaza al fijarlo,
#: no al usarlo: un proxy mal escrito que solo falla en la primera auditoria
#: es un fallo que aparece justo cuando no puedes depurarlo.
ESQUEMAS = ("http", "https", "socks5", "socks5h", "socks4")

#: Motivos por los que NUNCA se cambia de salida. Son subcadenas: se busca
#: cualquiera de ellas dentro del motivo, en minusculas y sin acentos.
MOTIVOS_PROHIBIDOS = (
    "cuota", "cupo", "racion", "quota", "rate limit", "ratelimit",
    "429", "too many requests", "limite", "limit exceeded", "throttl",
    # RAICES, no palabras enteras. La primera version listaba "bloqueo" y
    # dejaba pasar "la IP quedo bloqueada", que es como se escribe de
    # verdad en un log. Una lista de prohibiciones que solo caza la forma
    # de diccionario no prohibe nada.
    "bloque", "blocked", "block", "ban", "captcha", "atestacion",
    "attestation", "403", "denegad", "denied", "prohibid", "forbidden",
    "agotad", "exhaust",
)

_RE_URL = re.compile(r"^(?P<esquema>[a-z0-9]+)://(?P<resto>[^\s/]+)/?$", re.I)


class RotacionProhibida(RuntimeError):
    """Se intento cambiar la salida por un motivo de cuota o bloqueo."""


def _normaliza(texto: str) -> str:
    t = (texto or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        t = t.replace(a, b)
    return t


@dataclass
class SalidaDeRed:
    """La puerta de red de Ritsuko. Se fija a mano y no rota sola."""

    url: str = ""
    origen: str = "sin configurar"
    #: Cada intento de rotacion, permitido o no, queda apuntado. El informe
    #: de Ritsuko lo publica: una medida antievasion que nadie puede leer
    #: no es una medida, es una intencion.
    bitacora: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------- estado

    @property
    def configurada(self) -> bool:
        return bool(self.url)

    def httpx_kwargs(self) -> dict:
        """Lo que se le pasa a httpx. Vacio si no hay salida propia.

        Vacio NO es un error: significa que Ritsuko sale por donde salga
        el sistema, que es el modo por defecto. La independencia de red es
        una mejora opcional, no un requisito para auditar.
        """
        return {"proxy": self.url} if self.url else {}

    def estado(self) -> dict:
        return {
            "configurada": self.configurada,
            "salida": self._enmascarada(),
            "origen": self.origen,
            "rotaciones_rechazadas": sum(
                1 for e in self.bitacora if not e["permitida"]),
            "politica": ("salida fija, elegida por el usuario; no rota por "
                         "cuota, limite ni bloqueo"),
        }

    def _enmascarada(self) -> str:
        """La URL sin credenciales. Un proxy con user:pass en el informe
        seria una fuga de credenciales dentro del fichero que existe para
        que el usuario lo descargue y lo comparta."""
        if not self.url:
            return ""
        return re.sub(r"//[^@/]+@", "//***@", self.url)

    # -------------------------------------------------------- fijar/rotar

    @staticmethod
    def valida(url: str) -> str:
        u = (url or "").strip()
        if not u:
            return ""
        m = _RE_URL.match(u)
        if not m or m.group("esquema").lower() not in ESQUEMAS:
            raise ValueError(
                f"salida invalida: {url!r}. Formato: esquema://host:puerto "
                f"con esquema en {', '.join(ESQUEMAS)}. "
                "Ejemplo de VPN gratuita: socks5://127.0.0.1:9050 (Tor).")
        return u

    def fija(self, url: str | None, *, origen: str = "usuario") -> str:
        """Fija (o borra con None) la salida. Solo lo llama el usuario."""
        nueva = self.valida(url or "")
        anterior = self.url
        self.url = nueva
        self.origen = origen if nueva else "sin configurar"
        self.bitacora.append({"de": anterior, "a": nueva, "motivo": origen,
                              "permitida": True})
        logger.info("[ritsuko/red] salida fijada por %s: %s",
                    origen, self._enmascarada() or "(ninguna)")
        return nueva

    def rota_por(self, motivo: str, url: str | None = None) -> str:
        """Cambio de salida CON motivo. Rechaza los motivos de evasion.

        Existe para que ningun sitio del sistema pueda cambiar la salida
        «sin querer» al manejar un 429: cualquier ruta que quiera rotar
        tiene que pasar por aqui y declarar por que, y la mitad de los
        porques estan prohibidos.
        """
        m = _normaliza(motivo)
        prohibido = next((p for p in MOTIVOS_PROHIBIDOS if p in m), None)
        if prohibido:
            self.bitacora.append({"de": self.url, "a": url or "",
                                  "motivo": motivo, "permitida": False,
                                  "regla": prohibido})
            logger.warning(
                "[ritsuko/red] RECHAZADA rotacion por %r (coincide con %r). "
                "El sistema no esquiva raciones: si el proveedor limita, se "
                "informa y se espera.", motivo, prohibido)
            raise RotacionProhibida(
                f"no se cambia de salida de red por {motivo!r}. VeniceMAGI "
                "no rota IP ni VPN para esquivar cuotas ni bloqueos: cuando "
                "el proveedor raciona, se dice y se espera. Si quieres otra "
                "salida por un motivo legitimo, fijala a mano con /vpn.")
        return self.fija(url, origen=f"rotacion: {motivo}")

    # ------------------------------------------------------ configuracion

    @classmethod
    def desde_entorno(cls) -> "SalidaDeRed":
        """Lee la salida configurada. En orden, gana el primero.

        1. `RITSUKO_VPN`  — la propia de la auditora
        2. `ritsuko_vpn`  en config.json
        3. `NOTRACK_PROXY`/`notrack_proxy` — se hereda, avisando de que NO
           es una salida independiente: es la misma puerta que usa el
           trafico compatible del sistema, asi que comparte IP con el
           auditado y no cumple el proposito. Se usa porque tener algo es
           mejor que nada, y se dice porque callarlo seria vender
           independencia que no hay.
        """
        s = cls()
        bruto = (os.environ.get("RITSUKO_VPN") or "").strip()
        if bruto:
            s.fija(bruto, origen="entorno RITSUKO_VPN")
            return s
        propio = (_config().get("ritsuko_vpn") or "").strip()
        if propio:
            s.fija(propio, origen="config.json ritsuko_vpn")
            return s
        heredado = (os.environ.get("NOTRACK_PROXY")
                    or _config().get("notrack_proxy") or "").strip()
        if heredado:
            s.fija(heredado, origen="heredada de /notrack (NO independiente: "
                                    "misma IP que el resto del sistema)")
        return s

    def guarda(self) -> None:
        """Persiste la salida en config.json, junto al resto de ajustes."""
        d = _config()
        if self.url:
            d["ritsuko_vpn"] = self.url
        else:
            d.pop("ritsuko_vpn", None)
        _escribe_config(d)


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


#: La salida del proceso. Una sola: dos instancias con URLs distintas
#: harian que «la salida de Ritsuko» dependiese de quien preguntase.
_SALIDA: SalidaDeRed | None = None


def salida_de_ritsuko(recargar: bool = False) -> SalidaDeRed:
    global _SALIDA
    if _SALIDA is None or recargar:
        _SALIDA = SalidaDeRed.desde_entorno()
    return _SALIDA
