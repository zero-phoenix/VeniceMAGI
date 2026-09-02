"""
EL BUCLE DE AUTOCORRECCIÓN, con una medición de verdad detrás.

QUÉ ESTABA MAL
==============
`loop.py` implementa el bucle del plan —generar, medir, criticar, repetir
hasta converger o hasta meseta— y su propio docstring lo confiesa:

    measurement_function es un mock de Measure() determinista.

O sea: el mecanismo de convergencia existía y no medía nada. `spec.py` igual,
y `rights.py` igual. Tres módulos correctos, con tests, sin un solo llamador.
El trinquete de huérfanos los venía señalando desde su creación, que es
exactamente para lo que existe.

QUÉ HACE ESTE MÓDULO
====================
Ser el cable. Une las cuatro piezas que ya estaban y nunca se habían tocado:

    RightsGate      →  no se genera nada que suplante a nadie
    MediaSpec       →  el encargo se vuelve criterios medibles duros
    MedidorDeEstilo →  la medición REAL sustituye al mock
    AutoCorrectionLoop → convergencia y meseta

POR QUÉ LA MESETA IMPORTA MÁS QUE LA CONVERGENCIA
=================================================
Un bucle que solo sabe parar cuando gana no para nunca cuando pierde: gasta
las cuatro pasadas, y la ración de un proveedor guest, para entregar lo mismo
que tenía en la primera. `AutoCorrectionLoop` ya distinguía las dos salidas;
lo que le faltaba era que el número que compara entre pasadas viniera de
medir un fichero y no de un doble.

LA GENERACIÓN SE INYECTA, NO SE IMPORTA
=======================================
El bucle recibe una función que produce un vídeo y devuelve su ruta. Así el
mismo bucle sirve para el montador FFmpeg de hoy y para el generativo del día
que exista, sin tocarlo — y, sobre todo, se puede probar entero con vídeos
sintéticos, sin red, sin modelo y sin ración.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from .estilo import BibliaDeEstilo, MedidaEstilo, Tolerancia, compara, medir
from .loop import AutoCorrectionLoop
from .rights import RightsBlockedError, RightsGate
from .spec import MediaSpec, SpecError

logger = logging.getLogger(__name__)

#: Se reexportan `BibliaDeEstilo` y `Tolerancia` a propósito: quien usa el
#: bucle necesita reconstruir una biblia desde su JSON, y obligarle a importar
#: de dos módulos para una sola operación es la clase de costura que acaba en
#: dos formas distintas de cargar lo mismo.
__all__ = ["ResultadoBucle", "criterios_desde_biblia", "rueda_hasta_cumplir",
           "BibliaDeEstilo", "Tolerancia", "SpecError", "RightsBlockedError"]


def criterios_desde_biblia(biblia: BibliaDeEstilo) -> list[dict]:
    """Convierte las tolerancias de la biblia en criterios DUROS de `MediaSpec`.

    Duros todos, y no por dureza: `MediaSpec` se niega a construirse sin al
    menos uno (`SpecError`), y con razón — un encargo cuyos criterios son
    todos blandos no se puede suspender, así que el bucle convergería en la
    primera pasada por definición.
    """
    return [{"eje": t.eje, "objetivo": t.objetivo, "margen": t.margen,
             "hard": True} for t in biblia.tolerancias]


@dataclass
class ResultadoBucle:
    estado: str = ""                       # convergido | meseta | agotado | bloqueado
    version: int = 0
    ruta: str = ""
    historial: list[dict] = field(default_factory=list)
    ultimo_reintento: list[str] = field(default_factory=list)
    motivo: str = ""
    medida: MedidaEstilo | None = None

    @property
    def ok(self) -> bool:
        return self.estado == "convergido"

    def render(self) -> str:
        lineas = [f"estado: {self.estado} (pasadas: {self.version})"]
        for h in self.historial:
            lineas.append(
                f"  v{h['version']}: {h['failed']} ejes incumplidos"
                + (f" · {h['nota']}" if h.get("nota") else ""))
        if self.motivo:
            lineas.append(f"motivo: {self.motivo}")
        if self.ultimo_reintento:
            lineas.append("qué seguía fallando al final:")
            lineas += [f"  - {f}" for f in self.ultimo_reintento]
        return "\n".join(lineas)


async def rueda_hasta_cumplir(
    encargo: str,
    biblia: BibliaDeEstilo,
    generar: Callable[[int, list[str]], Awaitable[Path | str | None]],
    *,
    max_versiones: int = 4,
) -> ResultadoBucle:
    """Genera, mide contra la biblia, y reintenta con la lista de fallos.

    `generar(version, correcciones)` recibe el número de pasada y la lista
    concreta de ejes incumplidos de la pasada anterior —vacía en la primera—
    y devuelve la ruta del vídeo producido.

    Que reciba las correcciones y no un «hazlo mejor» es la misma regla que el
    reintento dirigido del taller de arte: un veredicto negativo sin la lista
    de lo que falló solo pide suerte.
    """
    res = ResultadoBucle()

    # 1. Derechos ANTES de gastar nada. Comprobar después de generar es
    #    comprobar cuando el daño de generar ya está hecho.
    try:
        RightsGate().check_spec(encargo)
    except RightsBlockedError as e:
        res.estado, res.motivo = "bloqueado", str(e)
        return res

    # 2. El encargo se vuelve contrato medible. Si la biblia no trae ni un
    #    eje, `MediaSpec` lo dice en vez de dejar rodar un bucle sin juez.
    try:
        MediaSpec(encargo, criterios_desde_biblia(biblia))
    except SpecError as e:
        res.estado, res.motivo = "bloqueado", str(e)
        return res

    ultima_medida: MedidaEstilo | None = None
    ultimas_correcciones: list[str] = []
    rutas: dict[int, str] = {}

    async def _mide(version: int) -> int:
        """La medición REAL que sustituye al mock de `loop.py`."""
        nonlocal ultima_medida, ultimas_correcciones
        destino = await generar(version, list(ultimas_correcciones))
        if destino is None:
            ultimas_correcciones = ["la generación no produjo ningún fichero"]
            # Se devuelve el peor resultado posible en vez de una excepción:
            # una pasada fallida es información para la meseta, no el final
            # del bucle. Si falla dos veces seguidas, la meseta lo corta sola.
            return len(biblia.tolerancias) or 1
        p = Path(destino)
        rutas[version] = str(p)
        ultima_medida = await medir(p, procedencia="generado")
        veredicto = compara(ultima_medida, biblia)
        ultimas_correcciones = veredicto.lista_para_reintento()

        # SE CUENTAN LOS INCUMPLIDOS, NO LOS «SIN JUZGAR», Y LA DIFERENCIA
        # IMPORTA. La primera versión sumaba los dos, con el argumento de que
        # «no he podido comprobarlo» no es «está bien». El argumento es bueno
        # y la aplicación estaba mal: `sin_juzgar` recoge TODO lo que el
        # instrumento no midió, incluidos ejes que ni siquiera están en el
        # contrato —que el fichero no tenga pista de audio cuando la biblia no
        # habla de audio, que no haya detector de rostros cuando la biblia no
        # pide escala de plano.
        #
        # Medido: un vídeo comparado contra la biblia sacada de ÉL MISMO daba
        # 3 incumplidos y entraba en meseta. Un bucle que suspende a su propia
        # referencia no puede converger nunca, y entonces la meseta no protege
        # la ración: la gasta entera siempre.
        #
        # La quinta regla se sigue cumpliendo donde toca, y la cumple
        # `compara()`: un eje que SÍ está en la biblia y no se pudo medir ya
        # sale como `Desvio` incumplido. Lo de fuera del contrato es
        # información, y viaja en `sin_juzgar` para que se lea, no para que
        # suspenda.
        return len(veredicto.incumplidos)

    # `AutoCorrectionLoop` es síncrono y esto es asíncrono, así que se recorre
    # su misma lógica de convergencia y meseta con su instancia delante: los
    # topes salen de ella, no de números repetidos aquí.
    motor = AutoCorrectionLoop(max_versions=max_versiones)
    duros = len(biblia.tolerancias)
    ultimo_fallo, meseta = duros, 0

    for v in range(1, motor.max_versions + 1):
        fallos = await _mide(v)
        res.historial.append({"version": v, "failed": fallos})
        res.version, res.ruta = v, rutas.get(v, res.ruta)
        res.medida, res.ultimo_reintento = ultima_medida, ultimas_correcciones

        if fallos == 0:
            res.estado = "convergido"
            return res

        meseta = meseta + 1 if fallos >= ultimo_fallo else 0
        ultimo_fallo = fallos
        if meseta >= 2:
            res.estado = "meseta"
            res.motivo = (
                "dos pasadas seguidas sin mejorar ningún eje medible. Seguir "
                "gastaría ración para entregar lo mismo.")
            res.historial[-1]["nota"] = "meseta"
            return res

    res.estado = "agotado"
    res.motivo = f"se agotaron las {motor.max_versions} pasadas sin converger"
    return res
