"""
BÚSQUEDA: la técnica correcta cuando el cómputo es gratis y no hay gradientes.

EL RAZONAMIENTO, QUE ES LO ÚNICO QUE IMPORTA AQUÍ
=================================================
El modelo de recursos real de esta máquina es raro y conviene decirlo entero,
porque es lo que decide la técnica:

    dinero .............. CERO, y firme
    cómputo local ....... ilimitado (electricidad propia, GTX 1050 propia)
    VRAM ................ 2 GB, y eso no se negocia
    ración de nube ...... escasa, sin llave, sin cuenta

Con 2 GB no cabe un modelo de vídeo, así que **no hay gradientes**: entrenar
está fuera de la mesa por memoria, no por dinero. Y afinar con LoRA en la nube
cuesta unos diez dólares, que aquí es infinito.

Pero hay una tercera vía que nadie usa porque casi nunca es la barata: si
generar es barato y **medir es automático**, se puede *buscar*. Generar, medir,
mutar, quedarse con lo mejor, repetir. Sin gradientes, sin retropropagación,
sin VRAM. Solo tiempo de máquina — que es justo el recurso que aquí sobra.

Esto no es un truco: es la familia de métodos que se usa cuando la función que
se optimiza no es derivable. Y la de aquí no lo es: entre «los parámetros de
generación» y «el estilo medido del vídeo» hay un ffmpeg entero.

LA FUNCIÓN DE APTITUD ES EL MEDIDOR
===================================
`compara()` ya sabe decir cuánto se aleja un vídeo de la biblia. Eso es
exactamente una función de aptitud, y lleva escrita desde hace seis módulos
sin que nadie la usara para otra cosa que aprobar o suspender.

LA CUENTA DE INCUMPLIDOS NO SIRVE COMO APTITUD, Y ESTE ES EL PUNTO FINO
=======================================================================
`Veredicto.incumplidos` es un ENTERO, y un entero es una escalera. Dos
candidatos que fallan los mismos tres ejes puntúan igual aunque uno esté al
borde de cumplirlos y el otro a diez márgenes de distancia. Una búsqueda sobre
una escalera es una búsqueda ciega: no hay cuesta que subir.

Por eso aquí la aptitud es **continua**: la distancia de cada eje medida EN
UNIDADES DE SU PROPIO MARGEN. Así la saturación (0-1) y la duración de plano
(segundos) pesan lo mismo sin inventarse factores, y el paisaje tiene
pendiente. El bucle sigue usando el entero para decidir cuándo parar; la
búsqueda usa el número real para decidir hacia dónde ir. Son dos preguntas
distintas y merecen dos números distintos.

QUÉ IMPIDE QUE ESTO SE ENGAÑE A SÍ MISMO
========================================
Una búsqueda optimiza lo que se le mide, no lo que se quería. Si el medidor
tuviera un punto ciego, la búsqueda encontraría ese punto ciego — no por
malicia, sino porque es el óptimo barato, y una búsqueda con mil evaluaciones
es mucho mejor que una persona encontrando agujeros.

Por eso este módulo **no es soberano**: `adversario.ataca()` es su condición
previa. Un medidor que no ha pasado la auditoría no puede ser función de
aptitud, y `busca()` lo dice en el informe en vez de dar por hecho que quien
llama se acordó.

REFUTABLE
=========
«La búsqueda supera a las reglas escritas a mano.» Se refuta si mil
evaluaciones no bajan de la distancia que consiguen las cuatro pasadas de
`bucle.rueda_hasta_cumplir`. Si eso pasa, este módulo sobra y hay que decirlo.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .biblia import BibliaDeEstilo, Veredicto, compara
from .estilo import MedidaEstilo

logger = logging.getLogger(__name__)

#: Distancia que se le asigna a un eje que la biblia exige y el instrumento NO
#: pudo medir. Es también la ASÍNTOTA de la distancia de un eje medido: ningún
#: eje que se haya llegado a medir puede alcanzar este valor.
#:
#: EL FALLO QUE ESTE PAR DE LÍNEAS CIERRA, ENCONTRADO POR SU PROPIO TEST
#: ====================================================================
#: La primera versión ponía esta pena en 12 y dejaba la distancia medida
#: crecer sin tope. `test_un_eje_sin_medir_penaliza_mucho_en_vez_de_salir_
#: gratis` la tumbó en la primera ejecución: una saturación de 1.0 contra un
#: objetivo de 0.30±0.03 puntúa 23.3, o sea que **cegar al medidor puntuaba
#: mejor que medir fatal**. Una búsqueda con cientos de evaluaciones habría
#: aprendido en una tarde a producir vídeos imposibles de medir —en negro, sin
#: audio, de dos fotogramas— porque lo que no se mide no penaliza.
#:
#: El argumento («un eje sin medir tiene que doler») era correcto; la
#: aplicación estaba mal, y es exactamente el mismo error que cometió
#: `Veredicto.aprueba` en su día con `sin_juzgar`. Da que pensar que la quinta
#: regla del proyecto se haya vuelto a incumplir por tercera vez en el mismo
#: repositorio: no basta con creérsela, hay que dejar escrito el test que la
#: comprueba.
PENA_SIN_MEDIR = 10.0

#: Por debajo de esta amplitud de zoom se apaga el Ken Burns del todo.
#:
#: `VideoSpec.ken_burns` es un booleano, así que el gen tiene que caer a un
#: lado o al otro en algún punto. Se hace explícito aquí y no dentro del
#: generador porque es un ESCALÓN en el paisaje de búsqueda, y quien lea un
#: salto raro en el historial tiene derecho a saber dónde está el escalón.
UMBRAL_ZOOM = 0.012

#: Cómo se abre y se cierra el paso de mutación. Es la regla de un quinto de
#: Rechenberg, que tiene sesenta años y sigue siendo lo primero que hay que
#: poner.
#:
#: POR QUÉ, MEDIDO EN ESTE PROYECTO
#: ================================
#: La primera versión mutaba con un paso FIJO del 12% del rango de cada gen.
#: Con eso, 242 evaluaciones dejaban la distancia en 0,6023 contra el 0,7847 de
#: las reglas a mano: ganaba, pero **no convergía** aunque el óptimo existiera
#: y fuera alcanzable. El motivo es geométrico, no de suerte: la ventana que
#: cumple la saturación mide 0,10 de ancho y el paso valía 0,26, así que la
#: búsqueda saltaba por encima del sitio al que quería llegar, una y otra vez.
#: Un paso grande explora; para afinar hace falta uno pequeño, y no se puede
#: elegir de antemano cuál toca.
#:
#: La regla: si la generación mejoró, se abre el paso —vamos bien, sigamos
#: lejos—; si no mejoró, se cierra —estamos cerca, midamos más fino.
APERTURA, CIERRE = 1.18, 0.80
ESCALA_MIN, ESCALA_MAX = 0.02, 2.5

#: Rangos de cada gen. Fuera de esto no se muta: no por elegancia, sino porque
#: `VideoSpec.validate()` rechaza planos más cortos que el fundido y un
#: `eq=contrast=0` produce un fotograma plano que el medidor lee como negro.
#: Una búsqueda que gasta la mitad de sus evaluaciones en candidatos inválidos
#: es media búsqueda.
LIMITES: dict[str, tuple[float, float]] = {
    "segundos_plano": (0.8, 30.0),
    "crossfade": (0.0, 2.5),
    "zoom": (0.0, 0.30),
    "brillo": (-0.35, 0.35),
    "contraste": (0.55, 1.9),
    "saturacion": (0.0, 2.2),
}


# ------------------------------------------------------------------ el genoma

@dataclass(frozen=True)
class Genoma:
    """Los mandos que la búsqueda puede tocar. Nada más.

    Congelado (`frozen=True`) para que un candidato no pueda mutar por debajo
    después de haber sido evaluado: si el genoma cambiara tras la medición, el
    historial diría que la puntuación X salió de unos parámetros que ya no son
    los que se usaron, y el registro entero dejaría de valer.
    """
    segundos_plano: float = 4.0
    crossfade: float = 0.5
    zoom: float = 0.06
    brillo: float = 0.0
    contraste: float = 1.0
    saturacion: float = 1.0

    @property
    def ken_burns(self) -> bool:
        return self.zoom >= UMBRAL_ZOOM

    @property
    def grado(self) -> str:
        """La cadena `eq=` de FFmpeg. Vacía si no hay nada que corregir: un
        `eq=` neutro sigue costando una pasada de filtro por fotograma."""
        trozos = []
        if abs(self.brillo) > 0.005:
            trozos.append(f"brightness={self.brillo:.3f}")
        if abs(self.contraste - 1.0) > 0.01:
            trozos.append(f"contrast={self.contraste:.3f}")
        if abs(self.saturacion - 1.0) > 0.01:
            trozos.append(f"saturation={self.saturacion:.3f}")
        return ":".join(trozos)

    @property
    def firma(self) -> str:
        """Identidad estable del genoma. Sirve para no reevaluar dos veces el
        mismo candidato, que en una población pequeña pasa constantemente
        porque el cruce de dos padres parecidos devuelve al padre."""
        crudo = (f"{self.segundos_plano:.4f}|{self.crossfade:.4f}|"
                 f"{self.zoom:.4f}|{self.brillo:.4f}|"
                 f"{self.contraste:.4f}|{self.saturacion:.4f}")
        return hashlib.sha1(crudo.encode("ascii")).hexdigest()[:12]

    def render(self) -> str:
        return (f"plano {self.segundos_plano:.2f}s · fundido "
                f"{self.crossfade:.2f}s · "
                f"{'ken burns ' + format(self.zoom, '.3f') if self.ken_burns else 'cámara fija'}"
                f" · {self.grado or 'sin gradación'}")


def _acota(nombre: str, valor: float) -> float:
    bajo, alto = LIMITES[nombre]
    return max(bajo, min(alto, valor))


# ----------------------------------------------------------------- la aptitud

def distancia(medida: MedidaEstilo, biblia: BibliaDeEstilo) -> float:
    """Cuánto se aleja esta medida de la biblia. MENOR ES MEJOR. Cero = clavado.

    En unidades del margen de cada eje: `1.0` es «justo en el borde de lo
    admitido». Así un vídeo que falla la saturación por el doble de su margen
    y otro que falla la duración de plano por el doble del suyo puntúan igual,
    que es lo correcto — la biblia ya dijo cuánto vale cada margen.

    Función pura sobre una medida ya hecha, igual que `compara()`, y por el
    mismo motivo: se comprueba entera sin generar un solo vídeo.
    """
    v = compara(medida, biblia)
    return distancia_de_veredicto(v)


def _satura(d: float) -> float:
    """Comprime [0, inf) en [0, PENA_SIN_MEDIR) sin perder la pendiente.

    Un tope duro daría una meseta —entre 8 y 20 márgenes de desvío la búsqueda
    no distinguiría nada— y las mesetas son justo lo que este módulo quiere
    evitar. Esta curva es estrictamente creciente en todo el recorrido y nunca
    llega a la asíntota, así que se cumplen las dos cosas a la vez:

      · un eje medido, por horrible que salga, SIEMPRE puntúa mejor que un eje
        que no se pudo medir;
      · y sigue habiendo cuesta que bajar en todo el espacio.

    De regalo, un eje imposible —una biblia que pide 1.85:1 a una animática
    16:9— deja de aplastar a los demás: aporta un sumando acotado en vez de
    inundar la aptitud y volver irrelevante todo lo que sí se puede arreglar.
    """
    return PENA_SIN_MEDIR * d / (d + PENA_SIN_MEDIR)


def distancia_de_veredicto(v: Veredicto) -> float:
    if not v.desvios:
        # Sin contrato no hay distancia que medir, y devolver 0.0 —«perfecto»—
        # sería la peor respuesta posible: haría ganar a cualquier candidato.
        return PENA_SIN_MEDIR
    total = 0.0
    for d in v.desvios:
        if d.obtenido is None:
            total += PENA_SIN_MEDIR
            continue
        if d.cumple:
            # Dentro del margen NO se puntúa la distancia al centro. Perseguir
            # el centro de un eje ya cumplido gasta evaluaciones en algo que la
            # biblia declaró indiferente, y peor: empuja a empeorar otro eje
            # para ganar unas centésimas en este.
            continue
        margen = abs(d.margen) or 1e-6
        total += _satura(abs(d.obtenido - d.objetivo) / margen)
    return round(total / len(v.desvios), 6)


# ------------------------------------------------------------------ candidato

@dataclass
class Candidato:
    genoma: Genoma
    distancia: float = float("inf")
    ruta: str = ""
    incumplidos: int = -1
    generacion: int = 0
    motivo: str = ""            # por qué no se pudo evaluar, si no se pudo

    @property
    def evaluado(self) -> bool:
        return self.distancia < float("inf")


# ------------------------------------------------------------- los operadores

class _Dados:
    """Azar reproducible y local.

    No se usa `random` del módulo: arrastra estado global, así que dos
    búsquedas lanzadas en el mismo proceso se interfieren y ninguna de las dos
    se puede repetir. Una búsqueda que no se puede repetir no se puede
    comparar con otra, y comparar es todo lo que hace este módulo.
    """

    def __init__(self, semilla: int = 0):
        import random
        self._r = random.Random(semilla)

    def normal(self, sigma: float) -> float:
        return self._r.gauss(0.0, sigma)

    def uniforme(self, a: float, b: float) -> float:
        return self._r.uniform(a, b)

    def moneda(self) -> bool:
        return self._r.random() < 0.5

    def elige(self, cosas):
        return self._r.choice(list(cosas))


def muta(g: Genoma, dados: _Dados, *, escala: float = 1.0) -> Genoma:
    """Empuja cada gen un poco, en proporción a su propio rango.

    Proporcional al rango y no un valor fijo porque los genes viven en escalas
    distintas: sumar 0,05 a la saturación es un ajuste y sumarle 0,05 a los
    segundos por plano no se nota. Es la misma corrección que el margen
    relativo de la biblia, por el mismo motivo.
    """
    campos = {}
    for nombre, (bajo, alto) in LIMITES.items():
        sigma = (alto - bajo) * 0.12 * escala
        campos[nombre] = _acota(nombre, getattr(g, nombre)
                                + dados.normal(sigma))
    return replace(g, **campos)


def cruza(a: Genoma, b: Genoma, dados: _Dados) -> Genoma:
    """Cada gen se toma de uno de los dos padres. NO se promedian.

    Promediar dos buenas soluciones da una mala con una frecuencia
    incómoda —el punto medio entre «plano largo con cámara fija» y «plano
    corto con paneo» no es ninguna de las dos cosas—, y es exactamente el
    mismo error que fusionar dos LoRAs promediando sus pesos: el resultado no
    apunta a donde apuntaba ninguno de los dos.
    """
    campos = {n: (getattr(a, n) if dados.moneda() else getattr(b, n))
              for n in LIMITES}
    return replace(a, **campos)


def siembra(base: Genoma, biblia: BibliaDeEstilo, dados: _Dados,
            cuantos: int) -> list[Genoma]:
    """La población inicial: el genoma base, lo que diga la biblia, y ruido.

    Sembrar desde la biblia y no desde el azar puro es lo que aprendió la
    prueba de extremo a extremo: el Ken Burns se descubrió a base de probar,
    cuando la biblia ya traía escrito `fraccion_camara_fija` y por tanto ya
    sabía si esa referencia tenía la cámara clavada o no. Empezar ignorando lo
    que ya se sabe es tirar la primera generación entera.
    """
    # La siembra la hace `reglas.py` y NO se reimplementa aquí. Import tardío
    # porque `reglas` importa el genoma de este módulo: la dependencia va en
    # los dos sentidos porque las dos cosas mueven los mismos mandos, que es
    # justamente lo que hace comparable el experimento.
    from .reglas import siembra_desde_biblia
    guiado, _ = siembra_desde_biblia(biblia, base)

    poblacion = [base, guiado]
    while len(poblacion) < cuantos:
        semilla_g = dados.elige(poblacion[:2])
        poblacion.append(muta(semilla_g, dados, escala=1.6))
    return poblacion[:cuantos]


# -------------------------------------------------------------------- informe

@dataclass
class Frontera:
    """Lo que la búsqueda encontró, y cuánto le costó."""
    mejor: Candidato | None = None
    evaluaciones: int = 0
    generaciones: int = 0
    segundos: float = 0.0
    historial: list[dict] = field(default_factory=list)
    fallos_de_generacion: int = 0
    #: Distancia de referencia contra la que se compara. La pone quien llama:
    #: normalmente, la que consiguen las cuatro pasadas de reglas a mano.
    liston: float | None = None
    aviso_auditoria: str = ""

    @property
    def supera_al_liston(self) -> bool | None:
        """None = no había liston, que NO es «lo superó»."""
        if self.liston is None or self.mejor is None:
            return None
        return self.mejor.distancia < self.liston

    def render(self) -> str:
        if self.mejor is None:
            causa = (self.historial[-1].get("motivo", "sin motivo")
                     if self.historial else "no llegó a empezar")
            cola = ""
            if self.fallos_de_generacion:
                # EL DIAGNÓSTICO TIENE QUE APUNTAR AL SITIO CORRECTO. Es el
                # mismo fallo que el bucle aprendió midiendo: informaba
                # «meseta» cuando lo que pasaba es que no se había generado
                # nada, y quien lo leía se iba a tocar la dirección artística.
                cola = (f"\n  Lo que hay que mirar es el GENERADOR, no la "
                        f"dirección artística: {self.fallos_de_generacion} "
                        f"candidatos no produjeron fichero. No hubo corte que "
                        f"medir.")
            return f"la búsqueda no evaluó ningún candidato: {causa}{cola}"
        lineas = [
            f"mejor distancia {self.mejor.distancia:.4f} "
            f"({self.mejor.incumplidos} ejes incumplidos) tras "
            f"{self.evaluaciones} evaluaciones en "
            f"{self.generaciones} generaciones · {self.segundos:.0f}s",
            f"  genoma: {self.mejor.genoma.render()}",
        ]
        if self.liston is not None:
            veredicto = ("SUPERA" if self.supera_al_liston else "NO SUPERA")
            lineas.append(
                f"  {veredicto} al liston de las reglas a mano "
                f"({self.liston:.4f})")
        if self.fallos_de_generacion:
            lineas.append(
                f"  AVISO: {self.fallos_de_generacion} candidatos no llegaron "
                f"a generarse. Eso es el generador, no la dirección artística.")
        if self.aviso_auditoria:
            lineas.append(f"  AVISO: {self.aviso_auditoria}")
        return "\n".join(lineas)


# ------------------------------------------------------------------ el motor

async def busca(
    biblia: BibliaDeEstilo,
    generar: Callable[[Genoma, int], Awaitable[Path | str | None]],
    *,
    poblacion: int = 8,
    generaciones: int = 12,
    semilla: int = 0,
    presupuesto_s: float | None = None,
    base: Genoma | None = None,
    liston: float | None = None,
    medidor=None,
    auditado: bool = False,
) -> Frontera:
    """Genera, mide, muta y se queda con lo mejor. Hasta que se acabe el plazo.

    `generar(genoma, indice)` produce un vídeo con esos parámetros y devuelve
    su ruta. Se inyecta, igual que en `bucle.py`: así el mismo motor sirve para
    el montador FFmpeg de hoy y para el generativo del día que exista, y —lo
    que importa más— la búsqueda entera se prueba con vídeos sintéticos, sin
    red, sin modelo y sin gastar ración.

    `presupuesto_s` es el plazo real de esta máquina: aquí se regala
    electricidad, así que lo que limita no son las evaluaciones sino la noche
    que dura la corrida.
    """
    from .estilo import medir as medir_real
    medidor = medidor or medir_real

    f = Frontera(liston=liston)
    if not auditado:
        f.aviso_auditoria = (
            "el medidor que hace de aptitud NO ha pasado por `auditar_medidor` "
            "en esta corrida. Una búsqueda optimiza lo que se le mide: si el "
            "medidor tiene un punto ciego, esto lo encontrará. Pasa el "
            "adversario antes de creerte el resultado.")

    if not biblia.tolerancias:
        f.historial.append({"motivo": "la biblia no trae ni un eje: sin "
                                      "contrato no hay nada que optimizar"})
        return f

    dados = _Dados(semilla)
    arranque = time.monotonic()
    vistos: dict[str, float] = {}
    escala = 1.0
    actual = [Candidato(g) for g in siembra(
        base or Genoma(), biblia, dados, poblacion)]

    async def _evalua(c: Candidato, idx: int) -> None:
        clave = c.genoma.firma
        if clave in vistos:
            c.distancia = vistos[clave]      # ya se pagó por este candidato
            return
        destino = await generar(c.genoma, idx)
        if destino is None:
            f.fallos_de_generacion += 1
            c.motivo = "el generador no produjo fichero"
            return
        c.ruta = str(destino)
        m = await medidor(destino, procedencia="generado")
        v = compara(m, biblia)
        c.distancia = distancia_de_veredicto(v)
        c.incumplidos = len(v.incumplidos)
        vistos[clave] = c.distancia
        f.evaluaciones += 1

    for gen in range(1, generaciones + 1):
        for i, c in enumerate(actual):
            c.generacion = gen
            await _evalua(c, i)
            if presupuesto_s and time.monotonic() - arranque > presupuesto_s:
                break

        vivos = [c for c in actual if c.evaluado]
        mejoro = False
        if vivos:
            vivos.sort(key=lambda c: c.distancia)
            if f.mejor is None or vivos[0].distancia < f.mejor.distancia:
                f.mejor, mejoro = vivos[0], True

        # El paso se abre cuando encontramos algo y se cierra cuando no. Sin
        # esto la búsqueda gana a las reglas pero no converge: salta por encima
        # del sitio al que quiere llegar porque su zancada es más ancha que la
        # ventana que cumple.
        escala = max(ESCALA_MIN, min(
            ESCALA_MAX, escala * (APERTURA if mejoro else CIERRE)))

        f.generaciones = gen
        f.historial.append({
            "generacion": gen,
            "mejor": None if f.mejor is None else f.mejor.distancia,
            "evaluados": len(vivos),
            "escala": round(escala, 4),
            "evaluaciones": f.evaluaciones})

        if f.mejor is not None and f.mejor.distancia <= 0.0:
            break                                   # clavado; seguir es gastar
        if presupuesto_s and time.monotonic() - arranque > presupuesto_s:
            break
        if not vivos:
            # Nada se generó en toda la generación. Insistir con más mutaciones
            # es gastar la noche en un generador roto — el mismo diagnóstico
            # que `sin_generar` en el bucle, y por la misma razón.
            f.historial[-1]["motivo"] = (
                "ningún candidato llegó a generarse en esta generación")
            break

        # ÉLITE + hijos. La élite pasa INTACTA: sin ella, una generación con
        # mala suerte pierde el mejor resultado encontrado y la búsqueda puede
        # terminar peor de lo que ya estaba, que es la avería clásica de estos
        # métodos y la más difícil de ver desde fuera.
        elite = vivos[:max(1, poblacion // 4)]
        cria: list[Candidato] = [Candidato(c.genoma) for c in elite]
        while len(cria) < poblacion:
            padre = dados.elige(elite)
            madre = dados.elige(vivos[:max(2, poblacion // 2)])
            hijo = cruza(padre.genoma, madre.genoma, dados)
            cria.append(Candidato(muta(hijo, dados, escala=escala)))
        actual = cria

    f.segundos = round(time.monotonic() - arranque, 2)
    return f
