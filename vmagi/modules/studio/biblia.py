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

from .estilo import MedidaEstilo

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

    @classmethod
    def desde(cls, medida: MedidaEstilo, *, nombre: str = "referencia",
              holgura: float = 0.15) -> BibliaDeEstilo:
        """Deriva tolerancias de una medida real.

        `holgura` es la fracción del propio valor que se admite de desvío.
        Relativa y no absoluta porque un margen absoluto que vale para la
        saturación (0-1) no vale para la duración de plano (segundos).
        """
        b = cls(nombre=nombre, origen=medida.ruta,
                procedencia=medida.procedencia)
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

    @property
    def incumplidos(self) -> list[Desvio]:
        return [d for d in self.desvios if not d.cumple]

    @property
    def aprueba(self) -> bool:
        """Aprueba solo si TODO lo comprobable cumple y no falta nada.

        Un eje que no se pudo medir NO aprueba por omisión. Es la quinta
        regla del proyecto, y es la que se saltó `observe_video` cuando sin
        Pillow devolvía «correcto» sobre una captura que nunca abrió.
        """
        return not self.incumplidos and not self.sin_juzgar

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
        cab = ("APRUEBA" if self.aprueba
               else f"NO APRUEBA · {len(self.incumplidos)} incumplidos, "
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
    return v
