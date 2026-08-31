"""La racion visible: cuantas llamadas van hoy, y que no se repita ninguna.

POR QUE ES VISIBLE Y NO UN DETALLE INTERNO
==========================================
Los proveedores guest racionan por dia y por IP. Un sistema que gasta esa
racion sin ensenarla convierte el limite en una sorpresa: el usuario
descubre que se acabo cuando ya no puede trabajar. Aqui el contador se
consulta (`/salud`, la GUI) y el numero que sale es el de llamadas REALES
— las servidas por cache no cuentan, porque no gastaron nada.

LO QUE ESTE MODULO NO HACE, A PROPOSITO
=======================================
No rota IPs, no rota perfiles, no reintenta contra el muro cuando el sitio
dice que se acabo. Medido en la v1: reentrar como Guest nuevo NO recupera
cupo, porque la racion es por IP y por dia. Pelear contra eso seria burlar
la racion de quien nos da el servicio gratis, y es la linea que el
proyecto no cruza. Cuando se acaba, se dice y se espera a manana.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field

#: Cuantas respuestas se recuerdan por sitio. 64 entradas ocupan poco y
#: cubren el patron que mas gasta: el enjambre repreguntando lo mismo en
#: la misma ronda.
CACHE_MAX = 64


def _hoy() -> str:
    return time.strftime("%Y-%m-%d")


@dataclass
class Racion:
    """Contador diario + cache LRU de UN sitio guest."""

    sitio: str
    dia: str = field(default_factory=_hoy)
    llamadas: int = 0
    aciertos_cache: int = 0
    _cache: OrderedDict = field(default_factory=OrderedDict, repr=False)

    # ------------------------------------------------------- contador

    def _rueda_el_dia(self) -> None:
        """El contador es DIARIO: a medianoche vuelve a cero solo.

        Sin esto el numero crecia para siempre y dejaba de significar
        nada: «312 llamadas» no dice si hoy queda racion o no.
        """
        h = _hoy()
        if h != self.dia:
            self.dia = h
            self.llamadas = 0
            self.aciertos_cache = 0

    def apunta_llamada(self) -> int:
        """Una llamada REAL al proveedor. Devuelve el total de hoy."""
        self._rueda_el_dia()
        self.llamadas += 1
        return self.llamadas

    def estado(self) -> dict:
        self._rueda_el_dia()
        return {
            "sitio": self.sitio,
            "dia": self.dia,
            "llamadas_hoy": self.llamadas,
            "servidas_por_cache": self.aciertos_cache,
            "entradas_en_cache": len(self._cache),
        }

    # ---------------------------------------------------------- cache

    def consulta(self, clave: tuple) -> str | None:
        v = self._cache.get(clave)
        if v is None:
            return None
        self._cache.move_to_end(clave)      # LRU: lo usado, al final
        self._rueda_el_dia()
        self.aciertos_cache += 1
        return v

    def guarda(self, clave: tuple, valor: str) -> None:
        self._cache[clave] = valor
        self._cache.move_to_end(clave)
        while len(self._cache) > CACHE_MAX:
            self._cache.popitem(last=False)

    def vacia_cache(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        return n


#: Una racion por sitio. Compartirla entre sitios mentia: gastar el cupo
#: de Venice no gasta el de notrack, y un contador comun los sumaba.
_RACIONES: dict[str, Racion] = {}


def racion_de(sitio: str) -> Racion:
    """La ración de un sitio, creándola la primera vez.

    Se llama `racion_de` y no `racion` a propósito. Exportar una función
    llamada `racion` desde `venice/__init__.py` la dejaba encima del
    submódulo `venice.racion` en el espacio de nombres del paquete: a
    partir de ese momento `import vmagi.venice.racion` devolvía la
    FUNCIÓN, no el módulo, y cualquier acceso a `racion.CACHE_MAX` o
    `racion.reinicia()` moría con AttributeError. Un nombre distinto
    cuesta cinco letras; el choque cuesta una tarde.
    """
    r = _RACIONES.get(sitio)
    if r is None:
        r = _RACIONES[sitio] = Racion(sitio=sitio)
    return r


def estado_global() -> list[dict]:
    """Lo que `/salud` y la GUI muestran. Vacio si no se llamo a nadie."""
    return [r.estado() for r in _RACIONES.values()]


def reinicia() -> None:
    """Solo para tests: deja el registro como recien arrancado."""
    _RACIONES.clear()
