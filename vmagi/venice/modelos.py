"""Que modelo usa cada nodo, y como cambiarlo sin recompilar nada.

EL PROBLEMA QUE ESTO RESUELVE
============================
El reparto del enjambre vivia en el catalogo (`reparto_enjambre`) y solo
podia decir una cosa: que FAMILIA le toca a cada nodo. Eso deja fuera dos
preguntas que el usuario hace constantemente:

  · «quiero que Casper vaya por Venice hoy, que gemini esta lento»
  · «que modelos tengo disponibles sin cuenta, exactamente?»

La primera exigia editar un JSON y reiniciar. La segunda no tenia
respuesta: la lista estaba repartida entre `sitios.py`, el catalogo y las
constantes de g4f, y nadie la juntaba.

QUE HACE
========
Una capa fina encima del catalogo y de `sitios.py` que:

  1. **Enumera** todo lo que hay, guest y g4f, con su capacidad y la fecha
     de su ultima medida. Es lo que `/modelos` imprime.
  2. **Permite fijar la familia de un nodo** en caliente, guardandola en
     `config.json`. Lo que el usuario fija gana sobre el catalogo.
  3. **Defiende la invariante que sostiene el debate**: dos nodos del
     enjambre no pueden compartir familia. Si el usuario lo intenta, se
     dice por que en vez de aceptarlo y devolver ecos.

LO QUE NO HACE
==============
No elige por su cuenta. El sistema ya tiene una sonda que mide latencias y
un cortacircuitos que aparta a los caidos; esto es el mando del usuario,
no un segundo cerebro compitiendo con el primero.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = ["ModeloDisponible", "NODOS", "ROLES", "catalogo_de_modelos",
           "familia_de", "fijar_familia", "informe", "reparto_efectivo",
           "FamiliaRepetida"]

#: Los nodos cuyo modelo se puede cambiar. Naoko y Ritsuko NO estan aqui:
#: Naoko rota a proposito entre varias familias y Ritsuko tiene prohibido
#: usar cualquiera de las auditadas, asi que dejar tocarlas seria ofrecer un
#: mando que rompe una garantia. Ver ritsuko.py.
NODOS = ("MELCHIOR", "BALTHASAR", "CASPER")

#: Que aporta cada nodo, para que la lista sea legible sin abrir el codigo.
ROLES = {
    "MELCHIOR": "construye la tesis",
    "BALTHASAR": "refuta ejecutando",
    "CASPER": "sintetiza y te habla",
}


class FamiliaRepetida(ValueError):
    """Dos nodos del enjambre apuntando a la misma familia."""


@dataclass(frozen=True)
class ModeloDisponible:
    familia: str
    via: str                  # "guest" | "g4f"
    candidatos: int
    capacidades: tuple[str, ...]
    verificado: str = ""
    nota: str = ""

    @property
    def sin_cuenta(self) -> bool:
        """Todos lo son. La propiedad existe para que el dia que entre uno
        que no lo sea, haya donde decirlo en vez de tener que acordarse."""
        return True

    def linea(self) -> str:
        caps = "+".join(self.capacidades)
        fecha = self.verificado or "sin medir"
        return (f"{self.familia:<12} {self.via:<6} {caps:<14} "
                f"{self.candidatos:>2} cand.  {fecha}")


def catalogo_de_modelos() -> list[ModeloDisponible]:
    """Todo lo que se puede usar hoy, guest y g4f, en una sola lista.

    Los guest van delante porque son el camino principal del proyecto, y
    porque son los unicos que ademas generan imagen.
    """
    from vmagi.venice.sitios import SITIOS

    salida = [
        ModeloDisponible(
            familia=s.familia, via="guest", candidatos=1,
            capacidades=s.capacidades(), verificado=s.verificado, nota=s.nota)
        for s in SITIOS.values()
    ]
    try:
        from vmagi.core.providers.backends.g4f_backend import (
            FAMILY_SPECS,
            ROTOS,
            VERIFIED_FAMILIES,
        )
    except Exception as e:                               # noqa: BLE001
        logger.warning("[modelos] catalogo g4f no disponible: %s", e)
        return salida

    for fam, cands in FAMILY_SPECS.items():
        vivos = [c for c in cands if c[0] not in ROTOS]
        salida.append(ModeloDisponible(
            familia=fam, via="g4f", candidatos=len(vivos),
            capacidades=("chat",),
            verificado="verificada" if fam in VERIFIED_FAMILIES else "",
            nota="" if vivos else "sin candidatos vivos hoy"))
    return salida


def _familias_validas() -> set[str]:
    """Privada a propósito: la usa `fijar_familia` y nadie más.

    Como pública era un huérfano — el trinquete la cazó. Quien quiera la
    lista tiene `catalogo_de_modelos()`, que además dice de dónde sale cada
    familia y qué sabe hacer.
    """
    return {m.familia for m in catalogo_de_modelos()}


# ------------------------------------------------------- reparto efectivo

def _config() -> dict:
    from vmagi.venice import config
    return config._lee_config()


def _guarda(d: dict) -> None:
    from vmagi.venice import config
    config._escribe_config(d)


def reparto_efectivo() -> dict[str, str]:
    """El reparto que MANDA: catalogo primero, y encima lo que fijo el usuario.

    Se resuelve aqui y no en cada llamante porque un reparto que cada
    consumidor recompone a su manera acaba siendo dos repartos distintos —
    y eso es exactamente el fallo de diversidad que el registro existe para
    impedir.
    """
    from vmagi.core.providers.backends.g4f_backend import DEFAULT_SWARM_FAMILIES

    reparto = dict(DEFAULT_SWARM_FAMILIES)
    fijadas = _config().get("familias_por_nodo") or {}
    for nodo, fam in fijadas.items():
        if nodo in NODOS and isinstance(fam, str):
            reparto[nodo] = fam
    return reparto


def familia_de(nodo: str) -> str:
    return reparto_efectivo().get(nodo.upper(), "auto")


def fijar_familia(nodo: str, familia: str | None) -> dict[str, str]:
    """Fija (o suelta con None) la familia de un nodo. Devuelve el reparto.

    LA INVARIANTE QUE ESTO NO DEJA ROMPER
    =====================================
    Dos nodos en la misma familia no debaten: se hacen eco. Es el eje
    entero del metodo, y un mando que deja romperlo en caliente lo rompe
    en silencio — el sistema seguiria funcionando, dando respuestas
    peores, sin un solo error en el log.
    """
    nodo = nodo.upper()
    if nodo not in NODOS:
        raise ValueError(
            f"nodo desconocido: {nodo!r}. Se puede fijar: {', '.join(NODOS)}. "
            "Naoko rota a proposito y Ritsuko tiene prohibidas las familias "
            "que audita, asi que no se tocan desde aqui.")

    d = _config()
    fijadas = dict(d.get("familias_por_nodo") or {})
    if familia is None or not familia.strip():
        fijadas.pop(nodo, None)
    else:
        fam = familia.strip().lower()
        validas = _familias_validas()
        if fam not in validas:
            raise ValueError(
                f"familia desconocida: {fam!r}. Hay: "
                f"{', '.join(sorted(validas))}")
        propuesto = reparto_efectivo()
        propuesto[nodo] = fam
        repetidas = [n for n, f in propuesto.items()
                     if f == fam and n != nodo]
        if repetidas:
            raise FamiliaRepetida(
                f"{nodo} no puede ir en {fam!r}: ya la usa "
                f"{', '.join(repetidas)}. Dos nodos con la misma familia no "
                "se critican, se hacen eco — y el sistema seguiria "
                "respondiendo, peor, sin dar un solo error.")
        fijadas[nodo] = fam

    d["familias_por_nodo"] = fijadas
    _guarda(d)
    nuevo = reparto_efectivo()
    logger.info("[modelos] reparto: %s", nuevo)
    return nuevo


def informe() -> str:
    """Lo que imprime `/modelos`. Sin interpretar nada."""
    lineas = ["DISPONIBLES (todos sin cuenta y sin clave)",
              f"  {'familia':<12} {'via':<6} {'capacidades':<14} "
              f"{'cand.':>7}  medido"]
    for m in catalogo_de_modelos():
        marca = "  " if m.candidatos else "! "
        lineas.append(f"{marca}{m.linea()}")
    lineas.append("")
    lineas.append("REPARTO ACTUAL")
    fijadas = _config().get("familias_por_nodo") or {}
    for nodo, fam in reparto_efectivo().items():
        origen = "fijado por ti" if nodo in fijadas else "del catalogo"
        lineas.append(f"  {nodo:<10} {fam:<12} {ROLES.get(nodo, ''):<24} "
                      f"({origen})")
    lineas.append("")
    lineas.append("  NAOKO      rota entre command/gpt/claude segun la peticion")
    lineas.append("  RITSUKO    razonamiento/grok/perplexity — nunca una que audita")
    return "\n".join(lineas)
