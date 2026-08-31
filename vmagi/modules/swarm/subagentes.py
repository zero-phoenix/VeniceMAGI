"""Subagentes: un nodo abre varios frentes a la vez, dentro de su familia.

EL PROBLEMA
===========
Un nodo del enjambre es un solo hilo de pensamiento. Cuando el encargo
tiene tres partes separables —«un ping pong de 32 bits a todo color en un
exe portable» son cuatro promesas—, Melchior las aborda en fila dentro de
una respuesta, y las ultimas salen peor que las primeras porque llegan con
el contexto ya gastado.

Y mientras tanto los ocho nucleos de la maquina estan parados: el enjambre
espera respuestas de RED, no de CPU. Medido en la maquina del proyecto:
tres esperas independientes tardan **1,50 s en serie y 0,51 s en abanico**,
un 66 % menos, sin tocar el hardware.

QUE ES UN SUBAGENTE
===================
Una consulta acotada que un nodo lanza **en su propia familia**, en
paralelo con sus hermanas, con un contrato de una sola frase y un
presupuesto que no puede pasarse. No es otro nodo del enjambre: no debate,
no tiene herramientas propias, y su respuesta vuelve al nodo que lo lanzo
para que este decida que hacer con ella.

POR QUE EN SU PROPIA FAMILIA, Y NO EN LA MEJOR DISPONIBLE
=========================================================
Podria parecer mejor repartir los subagentes entre familias distintas —mas
diversidad, mejores respuestas—. Seria un error, y de los que no dan error:

El enjambre construye su valor sobre que Melchior, Balthasar y Casper
tengan sesgos DISTINTOS. Si los subagentes de Melchior salen por la familia
de Balthasar, la tesis llega a la antitesis ya contaminada con el sesgo de
quien tiene que refutarla, y la refutacion encuentra menos porque parte de
lo mismo. La diversidad esta entre nodos; dentro de un nodo, la coherencia
vale mas.

LO QUE ESTO NO HACE
===================
No paraleliza lo que depende. Balthasar no puede refutar una tesis que aun
no existe, y ningun abanico arregla eso. Los subagentes solapan lo que es
independiente **dentro de un turno**, no los turnos entre si.

Y no se lanzan siempre: un encargo de una sola pieza abre un frente, que es
lo mismo que no abrir ninguno. El abanico cuesta llamadas —y en VeniceMAGI
las llamadas son racion diaria por IP—, asi que se abre cuando hay algo que
repartir y no porque se pueda.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = ["Frente", "Reparto", "Abanico", "reparte_encargo",
           "MAX_FRENTES", "MIN_FRENTES_PARA_ABRIR"]

#: Techo de frentes simultaneos. Cuatro no es magico: es lo que cabe sin que
#: la racion diaria de un sitio guest se note en una sola ronda, y por encima
#: de tres el retorno cae —las partes se solapan y las respuestas repiten—.
MAX_FRENTES = 4

#: Por debajo de esto no se abre abanico. Un frente es una llamada normal
#: con pasos de mas.
MIN_FRENTES_PARA_ABRIR = 2

#: Presupuesto de cada subagente. Corto a proposito: un subagente que puede
#: escribir largo deja de ser una consulta acotada y se convierte en otro
#: nodo, con lo que el nodo que lo lanzo tiene que leerse una respuesta tan
#: larga como la suya y no ha ganado nada.
PLAZO_FRENTE_S = 60.0


@dataclass
class Frente:
    """Una parte separable del encargo, con su respuesta."""

    contrato: str                 # que se le pide, en una frase
    texto: str = ""
    proveedor: str = ""
    ms: float = 0.0
    error: str = ""

    @property
    def util(self) -> bool:
        return bool(self.texto.strip()) and not self.error


@dataclass
class Reparto:
    """Como se troceo el encargo. Vacio significa «no habia que trocear»."""

    frentes: list[str] = field(default_factory=list)
    motivo: str = ""

    def __bool__(self) -> bool:
        return len(self.frentes) >= MIN_FRENTES_PARA_ABRIR


_SEPARADORES = re.compile(
    r"\s*(?:;|\n\s*[-*•]\s*|\n\s*\d+[.)]\s*|\s+y adem[aá]s\s+)\s*", re.I)


def reparte_encargo(encargo: str, maximo: int = MAX_FRENTES) -> Reparto:
    """Trocea el encargo en partes separables. SIN llamar a ningun modelo.

    Se hace con reglas y no preguntandole a la nube por dos motivos, y el
    segundo importa mas que el primero:

      1. Cuesta una llamada de la racion averiguar como gastar la racion.
      2. Si el troceo lo decide un modelo, el reparto cambia entre corridas
         identicas y deja de poder compararse. La compuerta de la fase
         —«la ronda tarda menos con la misma calidad»— exige poder repetir
         la misma ronda dos veces, y con un troceo no determinista eso no
         se puede.
    """
    texto = (encargo or "").strip()
    if not texto:
        return Reparto(motivo="encargo vacio")

    partes = [p.strip(" .,\t") for p in _SEPARADORES.split(texto)]
    partes = [p for p in partes if len(p) >= 12]

    # Las comas solo trocean si NO hubo separadores fuertes: «rojo, de
    # noche» son matices de una sola imagen, no dos encargos. Con puntos y
    # coma o vinetas de por medio, la intencion de separar es explicita.
    if len(partes) < MIN_FRENTES_PARA_ABRIR:
        trozos = [p.strip(" .,\t") for p in re.split(r"\.\s+", texto)]
        partes = [p for p in trozos if len(p) >= 20]

    if len(partes) < MIN_FRENTES_PARA_ABRIR:
        return Reparto(motivo="el encargo es una sola pieza")
    if len(partes) > maximo:
        # Las que sobran se pegan a la ultima en vez de tirarse: perder una
        # promesa del encargo es peor que un frente algo mas gordo.
        partes = partes[:maximo - 1] + [" · ".join(partes[maximo - 1:])]
    return Reparto(frentes=partes, motivo=f"{len(partes)} partes separables")


class Abanico:
    """Lanza los frentes de UN nodo, en paralelo y en su familia."""

    def __init__(self, llm, familia: str, *, rol: str = "",
                 plazo_s: float = PLAZO_FRENTE_S):
        self._llm = llm
        self.familia = familia
        self.rol = rol or "?"
        self.plazo_s = plazo_s
        self.ultimo_ms = 0.0

    async def abrir(self, sistema: str, reparto: Reparto) -> list[Frente]:
        """Un subagente por frente, todos a la vez. Devuelve lo que volvio.

        `return_exceptions` NO se usa: cada frente atrapa lo suyo y vuelve
        con `error` puesto. Un frente que revienta no puede llevarse por
        delante a los otros tres, que ya han gastado racion.
        """
        if not reparto:
            return []
        t0 = time.monotonic()
        frentes = await asyncio.gather(
            *(self._uno(sistema, c) for c in reparto.frentes))
        self.ultimo_ms = (time.monotonic() - t0) * 1000
        vivos = [f for f in frentes if f.util]
        logger.info("[subagentes] %s abrio %d frentes en %s: %d utiles, %.0f ms",
                    self.rol, len(frentes), self.familia, len(vivos),
                    self.ultimo_ms)
        return frentes

    async def _uno(self, sistema: str, contrato: str) -> Frente:
        f = Frente(contrato=contrato)
        t0 = time.monotonic()
        instruccion = (
            f"{sistema}\n\n"
            "Estas atendiendo UNA parte de un encargo mayor, no el encargo "
            "entero. Responde solo a lo que se te pide aqui, en pocas lineas, "
            "y no repitas el contexto ni resumas lo que ya sabes."
        )
        try:
            texto, prov = await asyncio.wait_for(
                self._llm.generate(instruccion, contrato,
                                   family=self.familia,
                                   hedge=False,
                                   tag=f"subagente/{self.rol}"),
                timeout=self.plazo_s,
            )
        except asyncio.TimeoutError:
            f.error = f"sin respuesta en {self.plazo_s:.0f}s"
            f.ms = (time.monotonic() - t0) * 1000
            return f
        except Exception as e:                           # noqa: BLE001
            f.error = f"{type(e).__name__}: {e}"
            f.ms = (time.monotonic() - t0) * 1000
            return f

        # UN FALLO QUE VIENE COMO TEXTO SIGUE SIENDO UN FALLO. `cloud.py`
        # devuelve «[Inferencia no disponible: ...]» con proveedor
        # SYSTEM_ERROR, y quien no mire el proveedor se lo traga como
        # contenido bueno — que es como se acaba sintetizando sobre un error.
        from vmagi.core.providers.base import es_degradada
        if es_degradada(texto, prov):
            f.error = f"respuesta degradada de {prov}"
        else:
            f.texto = (texto or "").strip()
        f.proveedor = prov
        f.ms = (time.monotonic() - t0) * 1000
        return f

    @staticmethod
    def funde(frentes: list[Frente]) -> str:
        """Junta lo que volvio, marcando de que frente sale cada cosa.

        Se etiqueta cada bloque porque el nodo que lo lee tiene que poder
        decir «esta parte no la cubrio nadie». Un texto fundido sin costuras
        esconde justamente el frente que fallo.
        """
        vivos = [f for f in frentes if f.util]
        if not vivos:
            return ""
        bloques = [f"### {f.contrato}\n{f.texto}" for f in vivos]
        caidos = [f for f in frentes if not f.util]
        if caidos:
            bloques.append("### sin cubrir\n" + "\n".join(
                f"- {f.contrato} — {f.error}" for f in caidos))
        return "\n\n".join(bloques)


async def abanico_para(agente, sistema: str, encargo: str) -> tuple[str, dict | None]:
    """Abre frentes para UN agente y devuelve (encargo enriquecido, medida).

    VIVE AQUI Y NO EN `agents.py` A PROPOSITO. La primera version la puso
    como metodo de `SwarmAgentBase` y el trinquete de lineas la caza al
    instante: `agents.py` paso de 1230 a 1262 lineas. El techo no se sube —
    se adelgaza el modulo, y este es el sitio natural: todo lo que sabe de
    frentes esta en este fichero, y `agents.py` solo tiene que llamar.

    Devuelve el encargo TAL CUAL cuando no hay nada que repartir, que es el
    caso normal. Y un fallo del abanico nunca tumba el turno: se apunta y el
    nodo sigue con su encargo original — una optimizacion que puede dejarte
    sin respuesta no es una optimizacion.
    """
    if not getattr(agente, "subagentes", True):
        return encargo, None
    try:
        reparto = reparte_encargo(encargo)
        if not reparto:
            return encargo, None
        ab = Abanico(agente.llm, agente.family,
                     rol=getattr(agente, "role_name", "?"))
        frentes = await ab.abrir(sistema, reparto)
        fundido = ab.funde(frentes)
        medida = resumen(frentes, ab.ultimo_ms)
        if not fundido:
            return encargo, medida
        return (f"{encargo}\n\n"
                f"--- LO QUE YA HAN MIRADO TUS SUBAGENTES ---\n"
                f"(cada bloque es una parte del encargo; lo que figure como "
                f"«sin cubrir» sigue siendo tuyo)\n\n{fundido}"), medida
    except Exception as e:                               # noqa: BLE001
        logger.warning("[subagentes] %s: abanico no disponible: %s",
                       getattr(agente, "role_name", "?"), e)
        return encargo, None


def resumen(frentes: list[Frente], ms_total: float) -> dict:
    """Lo que la traza y la compuerta de la fase necesitan medir."""
    vivos = [f for f in frentes if f.util]
    serie = sum(f.ms for f in frentes)
    return {
        "frentes": len(frentes),
        "utiles": len(vivos),
        "ms_abanico": round(ms_total, 1),
        "ms_si_fuera_en_serie": round(serie, 1),
        # Lo que la fase promete. Si esto no sale positivo de forma
        # sostenida, el mecanismo se retira: esa es la compuerta.
        "ahorro_pct": (round((1 - ms_total / serie) * 100, 1)
                       if serie > 0 else 0.0),
        "por_frente": [
            {"contrato": f.contrato[:60], "ok": f.util,
             "ms": round(f.ms, 1), "proveedor": f.proveedor,
             "error": f.error}
            for f in frentes
        ],
    }
