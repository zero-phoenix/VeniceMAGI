"""
LA BIBLIA DE ESTILO Y EL VEREDICTO: la mitad que JUZGA.

POR QUÉ VIVE APARTE DE `estilo.py`
==================================
El docstring del medidor ya defendía esta separación antes de que existiera el
fichero: «`medir()` no sabe nada de biblias ni de tolerancias. Devuelve números
crudos. `compara()` es quien enfrenta dos medidas, y es una función aparte y
pura.»

Lo que forzó a cumplirlo fue el trinquete de líneas: `estilo.py` llegó a 1036
con un techo de 800. Se podía subir el techo —el mecanismo lo permite si se
explica— pero el argumento para partirlo ya estaba escrito dentro del propio
módulo. Un fichero que mide y juzga acaba mezclando las dos cosas, y entonces
el instrumento empieza a tener opinión.

La frontera es dura: aquí NO se abre un fichero, no se llama a ffmpeg y no se
toca la red. Todo lo de este módulo son funciones puras sobre una `MedidaEstilo`
ya hecha, y por eso se puede comprobar entero sin generar un solo vídeo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # pragma: no cover - solo para el tipado
    from .estilo import MedidaEstilo

# EL IMPORT VA BAJO `TYPE_CHECKING`, Y NO ES COSMÉTICA: SIN ESO ESTE MÓDULO NO
# SE PUEDE IMPORTAR EL PRIMERO.
#
# `estilo.py` reexporta al final lo de aquí —`BibliaDeEstilo`, `compara`— para
# que quien mide y juzga importe de un solo sitio. Con un `from .estilo import
# MedidaEstilo` en tiempo de ejecución, eso es un ciclo: importar `biblia`
# antes que `estilo` reventaba con «partially initialized module».
#
# No se veía porque TODOS los llamadores del repositorio importan `estilo`
# primero, que es el orden que deshace el ciclo por casualidad. Lo destapó el
# primer test que importó `biblia` directamente. Un ciclo que solo aguanta
# porque nadie ha probado el otro orden no está resuelto: está sin tocar.
#
# Aquí `MedidaEstilo` solo aparece en anotaciones, y con `from __future__
# import annotations` esas no se evalúan. Así que el import sobra en ejecución.

# ------------------------------------------------------------- biblia y juicio

#: Ejes que NO sobreviven a un tráiler: los decide el montador del tráiler,
#: no el director de la película.
EJES_SOLO_OBRA = frozenset({"duracion_media_plano", "planos",
                            "fraccion_silencio", "rango_dinamico_db",
                            "fraccion_banda_voz",
                            # El ritmo de los turnos de un tráiler es el del
                            # montador del tráiler, que corta el diálogo en
                            # frases sueltas con música encima. Justo lo
                            # contrario de la película que promociona.
                            "turnos_por_minuto", "duracion_media_turno",
                            "pausa_media", "pausa_maxima"})


@dataclass
class Tolerancia:
    """Cuánto se puede desviar un eje antes de declararlo incumplido."""
    eje: str
    objetivo: float
    margen: float
    #: Si es True, basta con estar POR DEBAJO del objetivo más el margen.
    #: Sirve para «la cámara no debe moverse más de X», donde quedarse corto
    #: no es un fallo.
    solo_maximo: bool = False


@dataclass
class Dominio:
    """De qué material salió la biblia, y por tanto qué puede juzgar.

    POR QUÉ HACE FALTA
    ==================
    Una biblia sacada de un plano suelto de seis segundos trae un
    `duracion_media_plano` perfectamente medido: seis. Y si con ella se juzga
    una película de tres minutos, la suspende entera — no porque la película
    esté mal, sino porque la referencia no tenía ni un corte que medir. El
    número era correcto; la extrapolación no.

    Es el mismo error que el tráiler, un escalón más abajo, y por eso se
    resuelve igual: en vez de prohibirlo, se DECLARA. `EJES_SOLO_OBRA` ya
    resolvía el caso del tráiler con una lista escrita a mano; esto lo resuelve
    con las cifras del propio material, que es lo que este proyecto prefiere
    siempre que puede.

    Todo lo de aquí son MEDIDAS, no etiquetas. «Interior», «doméstico» o
    «contemplativo» serían opiniones con aspecto de dato.
    """
    duracion_s: float = 0.0
    planos: int = 0
    con_audio: bool = False
    con_rostros: bool = False

    #: Por debajo de estos, un eje medido no habla del estilo: habla del
    #: trozo. Dos cortes no son un montaje y cuatro segundos no son un ritmo.
    PLANOS_MINIMOS = 3
    DURACION_MINIMA_S = 20.0

    def objeciones(self, ejes: list[str]) -> list[str]:
        """Qué ejes de esta biblia NO están respaldados por su material."""
        fuera = []
        if self.planos < self.PLANOS_MINIMOS:
            for e in ("duracion_media_plano", "planos"):
                if e in ejes:
                    fuera.append(
                        f"{e}: la referencia tiene {self.planos} plano(s). "
                        f"Con menos de {self.PLANOS_MINIMOS} no hay montaje "
                        f"que medir, solo un trozo.")
        if self.duracion_s and self.duracion_s < self.DURACION_MINIMA_S:
            for e in ("turnos_por_minuto", "pausa_media", "duracion_media_turno",
                      "fraccion_silencio"):
                if e in ejes:
                    fuera.append(
                        f"{e}: la referencia dura {self.duracion_s:.1f}s. El "
                        f"ritmo del diálogo no se mide en menos de "
                        f"{self.DURACION_MINIMA_S:.0f}s.")
        if not self.con_rostros and "escala_plano" in ejes:
            fuera.append(
                "escala_plano: no se detectó ni un rostro en la referencia, "
                "así que la escala de plano de la biblia no salió de mirar a "
                "nadie.")
        return fuera


@dataclass
class Conflicto:
    """Dos referencias que se contradicen en un eje. NO se promedia."""
    eje: str
    intervalos: list[tuple[str, float, float]] = field(default_factory=list)

    def render(self) -> str:
        trozos = ", ".join(f"{n} pide [{a:.4g}, {b:.4g}]"
                           for n, a, b in self.intervalos)
        return f"{self.eje}: {trozos} — no hay ningún valor que cumpla las dos"


@dataclass
class BibliaDeEstilo:
    """La dirección artística, en números, con su procedencia.

    Se construye desde una `MedidaEstilo` de la REFERENCIA. No se escribe a
    mano: una biblia escrita a mano son las suposiciones de quien la escribe
    con aspecto de dato.
    """
    nombre: str = ""
    origen: str = ""
    procedencia: str = "desconocida"
    tolerancias: list[Tolerancia] = field(default_factory=list)
    dominio: Dominio = field(default_factory=Dominio)
    #: Ejes que dos referencias se disputaban y que por eso NO entran al
    #: contrato. Viajan dentro de la biblia para que quien la use lo sepa sin
    #: tener que ir a buscar el informe de la combinación.
    conflictos: list[Conflicto] = field(default_factory=list)

    @property
    def ejes(self) -> list[str]:
        return [t.eje for t in self.tolerancias]

    def avisos_de_dominio(self) -> list[str]:
        avisos = self.dominio.objeciones(self.ejes)
        if self.procedencia == "sintetica":
            # EL AVISO MÁS IMPORTANTE DE TODOS, y va el primero.
            #
            # Una biblia sintética es un contrato perfectamente medido sobre un
            # fichero que fabriqué yo. Sirve para probar la tubería entera sin
            # depender de nadie —y para eso es exactamente lo correcto—, pero
            # sus números NO son los de ninguna película: son los que yo elegí
            # al construir el material. Sin esta línea, dentro de dos semanas
            # sería un JSON con cifras de aspecto medido y nadie recordaría de
            # dónde salieron. Es la definición de «suposiciones con aspecto de
            # dato», que es lo que el docstring de esta clase promete no hacer.
            avisos.insert(0, (
                "PROCEDENCIA SINTÉTICA: esta biblia salió de un vídeo "
                "fabricado a propósito, no de una obra. Los números están bien "
                "medidos y no describen la dirección artística de nadie. Sirve "
                "para probar la tubería; para dirigir, sustitúyela por la "
                "medida de un material real."))
        return avisos

    @classmethod
    def desde(cls, medida: MedidaEstilo, *, nombre: str = "referencia",
              holgura: float = 0.15) -> BibliaDeEstilo:
        """Deriva tolerancias de una medida real.

        `holgura` es la fracción del propio valor que se admite de desvío.
        Relativa y no absoluta porque un margen absoluto que vale para la
        saturación (0-1) no vale para la duración de plano (segundos).
        """
        b = cls(nombre=nombre, origen=medida.ruta,
                procedencia=medida.procedencia,
                dominio=Dominio(
                    duracion_s=float(medida.duracion or 0.0),
                    planos=int(medida.planos or 0),
                    con_audio=bool(medida.tiene_audio),
                    con_rostros=bool(medida.fraccion_con_rostro)))
        pares = [
            ("aspecto", medida.aspecto, False),
            ("duracion_media_plano", medida.duracion_media_plano, False),
            ("camara_px", medida.camara_px, True),
            ("fraccion_camara_fija", medida.fraccion_camara_fija, False),
            ("saturacion", medida.saturacion, False),
            ("luma", medida.luma, False),
            ("contraste", medida.contraste, False),
            ("escala_plano", medida.escala_plano, False),
            ("fraccion_silencio", medida.fraccion_silencio, False),
            ("turnos_por_minuto", medida.turnos_por_minuto, False),
            ("duracion_media_turno", medida.duracion_media_turno, False),
            ("pausa_media", medida.pausa_media, False),
        ]
        for eje, valor, solo_max in pares:
            if valor is None:
                continue
            if medida.procedencia == "trailer" and eje in EJES_SOLO_OBRA:
                continue
            b.tolerancias.append(Tolerancia(
                eje=eje, objetivo=float(valor),
                margen=abs(float(valor)) * holgura or holgura,
                solo_maximo=solo_max))
        return b

    def to_json(self) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def desde_json(cls, crudo: str) -> BibliaDeEstilo:
        """La vuelta de `to_json`. Aquí porque estaba escrita CUATRO veces.

        Las mismas nueve líneas vivían copiadas en `animatica_hasta_cumplir`,
        `auditar_medidor`, `juzgar_estilo` y la búsqueda. Cuatro copias de un
        lector no son cuatro lectores: son cuatro sitios donde arreglar el día
        que la biblia gane un campo, y tres de ellos se van a olvidar.
        """
        d = json.loads(crudo)
        dom = d.get("dominio") or {}
        return cls(
            nombre=d.get("nombre", ""), origen=d.get("origen", ""),
            procedencia=d.get("procedencia", "desconocida"),
            tolerancias=[Tolerancia(**t) for t in d.get("tolerancias", [])],
            # Los campos de clase (PLANOS_MINIMOS y compañía) NO viajan en el
            # JSON aunque `asdict` no los meta: se filtra igual por si una
            # biblia vieja o escrita a mano trae de más. Un `Dominio(**d)` con
            # una clave desconocida revienta la carga entera.
            dominio=Dominio(**{k: v for k, v in dom.items()
                               if k in ("duracion_s", "planos", "con_audio",
                                        "con_rostros")}),
            conflictos=[Conflicto(eje=c.get("eje", ""),
                                  intervalos=[tuple(i) for i
                                              in c.get("intervalos", [])])
                        for c in d.get("conflictos", [])])


@dataclass
class Desvio:
    eje: str
    objetivo: float
    obtenido: float | None
    margen: float
    cumple: bool
    motivo: str = ""


@dataclass
class Veredicto:
    """Qué cumple, qué no, y qué no se pudo juzgar. Las tres cosas."""
    desvios: list[Desvio] = field(default_factory=list)
    sin_juzgar: list[str] = field(default_factory=list)
    #: Ejes que la biblia exige y su propio material no respalda.
    #:
    #: NO suspenden y NO se descuentan: se AVISAN. Descontarlos seria decidir
    #: por quien juzga —a lo mejor sabe algo que el dominio no recoge— y
    #: callarlos seria dejarle perseguir toda la noche un objetivo que salio de
    #: un plano suelto de seis segundos. La tercera salida, avisar, es la unica
    #: que respeta las dos cosas.
    avisos_de_dominio: list[str] = field(default_factory=list)

    @property
    def incumplidos(self) -> list[Desvio]:
        return [d for d in self.desvios if not d.cumple]

    @property
    def aprueba(self) -> bool:
        """Cumple el CONTRATO: ningún eje de la biblia incumplido.

        EL FALLO QUE ESTO CIERRA, ENCONTRADO EJECUTÁNDOLO
        =================================================
        La primera versión exigía además `not self.sin_juzgar`, con el
        argumento de que un eje sin medir no puede aprobar por omisión. El
        argumento es bueno; la aplicación estaba mal, y la prueba de extremo a
        extremo del 2026-09-02 lo enseñó en una línea:

            NO APRUEBA · 0 incumplidos, 2 sin juzgar

        Eso era la REFERENCIA comparada contra la biblia sacada de ella misma.
        Los dos «sin juzgar» eran «OpenCV no está» y «el fichero no tiene pista
        de audio» — dos cosas que ni siquiera aparecen en el contrato. Con esa
        regla, en una máquina sin OpenCV **no aprueba nada, nunca**, y un
        enjambre que reintente contra ese veredicto no para jamás.

        La quinta regla se sigue cumpliendo, y la cumple `compara()`: un eje
        que SÍ está en la biblia y no se pudo medir ya sale como `Desvio`
        incumplido. Lo de fuera del contrato es información, no un suspenso, y
        para eso está `sin_dudas`.
        """
        return not self.incumplidos

    @property
    def sin_dudas(self) -> bool:
        """Cumple el contrato Y no quedó nada sin mirar en todo el fichero.

        Se separa de `aprueba` porque son dos preguntas distintas y quien
        decide necesita las dos: «¿cumple lo que le pedí?» y «¿hay algo que
        este instrumento no ha llegado a ver?». Fundirlas es lo que hacía que
        la respuesta a la primera dependiera de una carencia de la máquina.
        """
        return self.aprueba and not self.sin_juzgar

    def render(self) -> str:
        lineas = []
        for d in self.desvios:
            marca = "OK  " if d.cumple else "FALLA"
            obt = "sin medir" if d.obtenido is None else f"{d.obtenido:.4g}"
            lineas.append(
                f"  {marca} {d.eje:<22} objetivo {d.objetivo:.4g} "
                f"±{d.margen:.4g} · obtenido {obt}")
        for s in self.sin_juzgar:
            lineas.append(f"  ????  {s}")
        for a in self.avisos_de_dominio:
            lineas.append(f"  OJO  fuera del dominio de la biblia: {a}")
        if self.aprueba:
            cab = "APRUEBA" if self.sin_dudas else (
                f"APRUEBA el contrato · {len(self.sin_juzgar)} cosas del "
                f"fichero quedaron sin mirar (fuera del contrato)")
        else:
            cab = (f"NO APRUEBA · {len(self.incumplidos)} incumplidos, "
                   f"{len(self.sin_juzgar)} sin juzgar")
        return cab + "\n" + "\n".join(lineas)

    def lista_para_reintento(self) -> list[str]:
        """Los incumplimientos, en frases que se le pueden dar a un modelo.

        Un veredicto negativo no manda «hazlo mejor»: manda la lista concreta
        de lo que falló, igual que el reintento dirigido del taller de arte.
        """
        fuera = []
        for d in self.incumplidos:
            if d.obtenido is None:
                fuera.append(f"{d.eje}: no se pudo medir ({d.motivo})")
            elif d.obtenido > d.objetivo:
                fuera.append(
                    f"{d.eje}: salió {d.obtenido:.4g} y el objetivo es "
                    f"{d.objetivo:.4g}. Hay que BAJARLO.")
            else:
                fuera.append(
                    f"{d.eje}: salió {d.obtenido:.4g} y el objetivo es "
                    f"{d.objetivo:.4g}. Hay que SUBIRLO.")
        return fuera


def combina(biblias: list[BibliaDeEstilo], *,
            nombre: str = "combinada") -> BibliaDeEstilo:
    """Une varias biblias en una. POR INTERSECCIÓN, NUNCA POR PROMEDIO.

    EL FALLO QUE ESTA FUNCIÓN EXISTE PARA NO COMETER
    ================================================
    Promediar es lo primero que se le ocurre a cualquiera y está mal por el
    mismo motivo por el que fusionar dos LoRAs promediando sus pesos está mal:
    el punto medio entre dos direcciones no apunta a ninguna de las dos.

    Con números: una referencia pide planos de 8±1 segundos y otra de 2±0,3.
    El promedio es 5, un valor que **no describe ninguna de las dos películas**
    y que ninguna de las dos aprobaría. Peor todavía: el resultado tiene el
    aspecto de un dato medido, y nadie que lea la biblia combinada podrá saber
    que ese 5 no salió de mirar nada.

    Una biblia es un CONTRATO, y unir contratos es quedarse con lo que los dos
    exigen a la vez — la intersección de los intervalos. Si la intersección
    está vacía, las dos referencias se contradicen, y eso **se declara**: el
    eje sale del contrato y entra en `conflictos` con los dos intervalos
    dentro, para que una persona decida cuál de las dos películas está
    haciendo. Un contrato imposible de cumplir no es exigente: es un bucle que
    no para nunca.

    Los ejes `solo_maximo` no pueden dar conflicto y por eso se tratan aparte:
    la intersección de «no más de a» y «no más de b» es «no más del menor de
    los dos». Siempre existe, y siempre es el más estricto.
    """
    vivas = [b for b in biblias if b and b.tolerancias]
    if not vivas:
        return BibliaDeEstilo(nombre=nombre)
    if len(vivas) == 1:
        return vivas[0]

    por_eje: dict[str, list[tuple[BibliaDeEstilo, Tolerancia]]] = {}
    for b in vivas:
        for t in b.tolerancias:
            por_eje.setdefault(t.eje, []).append((b, t))

    fuera = BibliaDeEstilo(
        nombre=nombre,
        origen=" + ".join(b.origen or b.nombre or "?" for b in vivas),
        procedencia="+".join(sorted({b.procedencia for b in vivas})),
        dominio=Dominio(
            # El dominio combinado es el MÁS POBRE, no la suma. Unir un plano
            # de 6 s con una película de 3 min no da una referencia de 3 min:
            # da una en la que la mitad de los ejes siguen sin respaldo.
            duracion_s=min(b.dominio.duracion_s for b in vivas),
            planos=min(b.dominio.planos for b in vivas),
            con_audio=all(b.dominio.con_audio for b in vivas),
            con_rostros=all(b.dominio.con_rostros for b in vivas)))

    for eje, pares in sorted(por_eje.items()):
        solo_max = any(t.solo_maximo for _, t in pares)
        if solo_max:
            techo = min(t.objetivo + t.margen for _, t in pares)
            base = min(t.objetivo for _, t in pares)
            fuera.tolerancias.append(Tolerancia(
                eje=eje, objetivo=base, margen=max(0.0, techo - base),
                solo_maximo=True))
            continue

        bajo = max(t.objetivo - t.margen for _, t in pares)
        alto = min(t.objetivo + t.margen for _, t in pares)
        if bajo > alto:
            fuera.conflictos.append(Conflicto(
                eje=eje,
                intervalos=[(b.nombre or "?", t.objetivo - t.margen,
                             t.objetivo + t.margen) for b, t in pares]))
            continue
        fuera.tolerancias.append(Tolerancia(
            eje=eje, objetivo=(bajo + alto) / 2.0, margen=(alto - bajo) / 2.0))

    # El centro del intervalo resultante NO es un promedio de objetivos: es el
    # centro de la franja que las dos admiten, y por construcción las dos lo
    # aprueban. La diferencia con promediar se ve en cuanto los márgenes son
    # distintos, que es siempre.
    return fuera


def compara(medida: MedidaEstilo, biblia: BibliaDeEstilo) -> Veredicto:
    """Enfrenta una medida contra la biblia. Función pura, sin red ni disco.

    Pura a propósito, igual que `build_filtergraph` en `video.py`: así se
    puede comprobar en un test sin generar un vídeo ni esperar dos minutos,
    que es la diferencia entre tener tests de esto y no tenerlos.
    """
    v = Veredicto()
    for tol in biblia.tolerancias:
        obtenido = getattr(medida, tol.eje, None)
        if obtenido is None:
            v.desvios.append(Desvio(
                eje=tol.eje, objetivo=tol.objetivo, obtenido=None,
                margen=tol.margen, cumple=False,
                motivo="el instrumento no pudo medir este eje"))
            continue
        obtenido = float(obtenido)
        if tol.solo_maximo:
            cumple = obtenido <= tol.objetivo + tol.margen
        else:
            cumple = abs(obtenido - tol.objetivo) <= tol.margen
        v.desvios.append(Desvio(
            eje=tol.eje, objetivo=tol.objetivo, obtenido=obtenido,
            margen=tol.margen, cumple=cumple))
    # Lo que el instrumento declaró que no pudo medir viaja al veredicto. Si
    # se quedara en la medida, un corte cuyo movimiento de cámara no se pudo
    # medir aprobaría por no tener ningún desvío en contra.
    v.sin_juzgar = list(medida.no_medido)
    v.avisos_de_dominio = biblia.avisos_de_dominio()
    if biblia.conflictos:
        v.avisos_de_dominio += [
            f"eje retirado del contrato por contradicción: {c.render()}"
            for c in biblia.conflictos]
    return v
