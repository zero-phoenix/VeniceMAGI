"""
EL ADVERSARIO: material fabricado para que el medidor lo suspenda.

QUÉ HUECO CIERRA
================
El medidor de estilo se calibró contra vídeos sintéticos escritos a mano por
quien lo estaba construyendo. Eso comprueba que responde bien a los ataques
que a esa persona se le ocurrieron, que es un conjunto más pequeño y más
sesgado de lo que parece: nadie escribe el caso que no se le ha ocurrido.

Y el sesgo tiene una forma concreta y conocida. Los cuatro fallos que la
prueba de extremo a extremo del 2026-09-02 encontró —el veredicto que no
aprobaba ni su propia referencia, el encadenado contado como varios cortes, el
bucle descubriendo por ensayo lo que estaba en el contrato, el etalonaje que
borraba los cortes— **no los encontró ningún test**. Los encontró ejecutar el
sistema contra material que no estaba hecho para que pasara.

Este módulo convierte eso en una capacidad del propio sistema: fabricar el
material adverso, pasarlo por el medidor, y comprobar que lo suspende **por el
eje que se estaba atacando**. Un medidor al que nadie ataca no está medido:
está descrito.

LA REGLA QUE HACE QUE ESTO SIGNIFIQUE ALGO
==========================================
**Cada contraejemplo viola UN solo eje.** Si un vídeo sale desaturado *y*
oscuro *y* con la cámara moviéndose, y el veredicto lo suspende, no se ha
aprendido nada: no se sabe cuál de los tres ejes lo detectó, ni si los otros
dos habrían pasado desapercibidos. Un test que no puede fallar por un motivo
concreto no comprueba nada concreto.

De ahí que cada ataque sea una transformación mínima de la propia referencia
—un filtro de FFmpeg sobre el fichero original— en vez de un vídeo nuevo. Lo
que no se toca queda idéntico por construcción, no por buena intención.

DE QUIÉN ES ESTE TRABAJO
========================
De Ritsuko. Audita, no arregla: fabrica el ataque, mira el veredicto y emite
un informe. No toca el medidor, no ajusta umbrales y no decide nada. Un
auditor con permiso para corregir el instrumento que audita deja de ser
auditor a la segunda vez que lo corrige, porque a partir de ahí se está
revisando a sí mismo — la misma regla que ya gobierna `ritsuko.py`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

# SE ENTRA POR LA FACHADA, no por `biblia` directamente.
#
# `estilo` reexporta lo de `biblia` al final del módulo, y `biblia` importa
# `MedidaEstilo` de `estilo`. Importar de `biblia` desde fuera hace que Python
# empiece por ahí y llegue a `estilo`, que a mitad de carga vuelve a `biblia`:
#
#     ImportError: cannot import name 'EJES_SOLO_OBRA' from partially
#     initialized module 'vmagi.modules.studio.biblia'
#
# Es el precio de la reexportación, y se paga aquí en vez de deshacerla:
# obligar a quien llama a importar de dos módulos para medir y juzgar sería
# peor. La regla queda escrita para el siguiente: **desde fuera del paquete,
# todo lo del estilo entra por `estilo`.**
from .estilo import BibliaDeEstilo, EstiloError, _corre, compara, medir

logger = logging.getLogger(__name__)

#: Un ataque por eje: el filtro de FFmpeg que lo viola y en qué dirección.
#:
#: Los filtros son deliberadamente BRUSCOS. Un ataque al borde de la
#: tolerancia comprueba la calibración del umbral, que es otra pregunta; este
#: comprueba que el eje se mira siquiera. Si un eje no detecta una violación
#: escandalosa, afinar su umbral es perder el tiempo.
ATAQUES: dict[str, tuple[str, str]] = {
    "camara_px": (
        "scale=iw*1.6:ih*1.6,crop=iw/1.6:ih/1.6:x='(iw-ow)/2+(iw-ow)/2*sin(t*1.6)'"
        ":y='(ih-oh)/2'",
        "una panorámica de vaivén sobre el mismo material: cambia dónde mira "
        "la cámara y nada más"),
    "fraccion_camara_fija": (
        "scale=iw*1.6:ih*1.6,crop=iw/1.6:ih/1.6:x='(iw-ow)/2+(iw-ow)/2*sin(t*1.6)'"
        ":y='(ih-oh)/2'",
        "el mismo vaivén: ningún par de fotogramas queda quieto"),
    "saturacion": (
        # `hue=s=0` y no `eq=saturation=0.08`. El primer intento usaba `eq` y
        # el adversario lo declaró ESCAPADO: la saturación medida solo bajaba
        # de 0,313 a 0,265 —un 15%— pese a pedir una reducción del 92%. Un
        # ataque que no ataca no prueba que el medidor sea ciego: prueba que
        # el ataque era flojo, y confundir las dos cosas habría mandado a
        # tocar el medidor. `hue=s=0` es una conversión a gris sin ambigüedad.
        "hue=s=0",
        "el color arrancado del todo, a gris puro, sin tocar luz ni encuadre"),
    "luma": (
        "eq=brightness=0.35",
        "subexposición invertida: el mismo plano, dos pasos más claro"),
    "contraste": (
        "eq=contrast=0.22",
        "la imagen aplanada: mismo contenido, curva de contraste destruida"),
    "aspecto": (
        "crop=iw:ih/2:0:ih/4,pad=iw:ih:0:ih/4:black",
        "el encuadre reventado a formato de buzón: la imagen activa pasa a "
        "ser el doble de ancha de lo que era"),
    "duracion_media_plano": (
        "",       # este no es un filtro: se fabrica troceando y reordenando
        "el mismo material picado en planos cortos: mismo color, misma luz, "
        "misma cámara, otro montaje"),
}


@dataclass
class Ataque:
    eje: str
    descripcion: str
    ruta: str = ""
    #: Ejes que el veredicto suspendió al pasarle este contraejemplo.
    suspendidos: list[str] = field(default_factory=list)
    cazado: bool = False
    #: ¿El ataque llegó a mover el eje que decía atacar? Si no, el veredicto
    #: no puede decir nada de ese eje, y decir «ESCAPA» sería acusar al
    #: medidor de una ceguera que no se ha demostrado.
    aplicable: bool = True
    #: Ejes que cayeron ADEMÁS del atacado. No es un fallo por sí solo —bajar
    #: el contraste mueve la luma de verdad—, pero se declara: un ataque que
    #: tumba media biblia no prueba nada sobre el eje que decía atacar.
    colaterales: list[str] = field(default_factory=list)
    motivo: str = ""

    def render(self) -> str:
        if not self.ruta:
            return f"  ????  {self.eje:<22} no se pudo fabricar: {self.motivo}"
        if not self.aplicable:
            return (f"  N/A   {self.eje:<22} el ataque no movió el eje: "
                    f"nada que concluir")
        marca = "  CAZA " if self.cazado else "  ESCAPA"
        extra = (f"  (+{len(self.colaterales)} colaterales)"
                 if self.colaterales else "")
        return (f"{marca} {self.eje:<22} {self.descripcion[:46]}{extra}")


@dataclass
class InformeAdversario:
    ataques: list[Ataque] = field(default_factory=list)
    no_atacados: list[str] = field(default_factory=list)

    @property
    def escapados(self) -> list[Ataque]:
        """Ataques que SÍ movieron su eje y aun así no fueron cazados.

        Los inaplicables quedan fuera a propósito: un ataque que no atacó no
        prueba ceguera, y contarlo como tal manda a arreglar un instrumento
        que no estaba roto.
        """
        return [a for a in self.ataques
                if a.ruta and a.aplicable and not a.cazado]

    @property
    def inaplicables(self) -> list[Ataque]:
        return [a for a in self.ataques if a.ruta and not a.aplicable]

    @property
    def sospecha_de_ceguera(self) -> bool:
        """¿Y si el instrumento no mira nada, en vez de mirarlo todo bien?

        EL AGUJERO QUE ESTO CIERRA, Y LO ENCONTRÓ SU PROPIO TEST.
        =========================================================
        Al añadir la comprobación de «¿el ataque movió el eje?» —que existe
        para no acusar al medidor cuando el flojo era el ataque— apareció el
        caso simétrico: **un medidor que devuelve siempre lo mismo produce
        exactamente el mismo informe que siete ataques que no atacan.**

        Se detectó cegando el medidor a propósito en un test. Antes de este
        arreglo, el adversario contestaba «sólido frente a 0 ataques
        efectivos» y daba la firma. Un auditor que aprueba un instrumento
        roto es peor que no tener auditor: da la firma sin haber mirado.

        La salida es estadística y es la honesta: siete transformaciones
        deliberadamente brutales —arrancar el color, doblar el brillo, romper
        el encuadre, mover la cámara— no pueden fallar TODAS sobre el mismo
        material. Si ninguna mueve su eje, lo que no se mueve es el
        instrumento.
        """
        vivos = [a for a in self.ataques if a.ruta]
        return bool(vivos) and all(not a.aplicable for a in vivos)

    @property
    def solido(self) -> bool:
        """El medidor es sólido si ningún ataque fabricado se le escapó.

        No dice «el medidor es correcto»: dice «no falló en lo que se le
        probó». Los ejes de `no_atacados` siguen sin comprobar, y eso se
        imprime en vez de contarse como aprobado.

        Y no puede ser sólido si se sospecha ceguera: aprobar por ausencia de
        fallos cuando la ausencia se debe a que nadie miró es exactamente la
        quinta regla del proyecto al revés.
        """
        return not self.escapados and not self.sospecha_de_ceguera

    def render(self) -> str:
        lineas = []
        for a in self.ataques:
            lineas.append(a.render())
        for e in self.no_atacados:
            lineas.append(f"  ????  {e:<22} sin ataque conocido: SIN COMPROBAR")
        vivos = [a for a in self.ataques if a.ruta and a.aplicable]
        if self.sospecha_de_ceguera:
            return ("MEDIDOR CIEGO: ninguno de los "
                    f"{len([a for a in self.ataques if a.ruta])} ataques movió "
                    "su eje. Siete transformaciones brutales no pueden fallar "
                    "todas: lo que no se mueve es el instrumento.\n"
                    + "\n".join(a.render() for a in self.ataques))
        cab = (f"medidor SÓLIDO frente a {len(vivos)} ataques efectivos"
               if self.solido else
               f"MEDIDOR CIEGO en {len(self.escapados)} de "
               f"{len(self.ataques)} ejes atacados")
        if self.no_atacados:
            cab += f" · {len(self.no_atacados)} ejes sin ataque"
        if self.inaplicables:
            cab += (f" · {len(self.inaplicables)} ataques que no movieron su "
                    f"eje sobre este material")
        return cab + "\n" + "\n".join(lineas)


async def _fabrica_por_filtro(origen: Path, destino: Path, vf: str) -> None:
    rc, _ = await _corre([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(origen), "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(destino)], timeout=300)
    if rc != 0 or not destino.exists():
        raise EstiloError(f"ffmpeg no pudo fabricar el ataque: {vf[:60]}")


async def _fabrica_picado(origen: Path, destino: Path) -> None:
    """Ataque al montaje: el mismo material, picado en planos cortos.

    No se puede hacer con un filtro de color porque el montaje no es una
    propiedad de la imagen. Se corta en trozos de 0,8 s y se invierte el orden
    de a pares, que produce cortes DE VERDAD —cambios bruscos de contenido—
    sin tocar paleta, luz ni cámara. Un `fade` no serviría: sería una
    transición gradual, y el medidor las une a propósito.
    """
    from .estilo import _sonda
    datos = await _sonda(origen)
    dur = float(datos.get("format", {}).get("duration") or 0)
    trozos = max(2, int(dur // 0.8))
    partes = []
    for i in range(trozos):
        partes.append(f"[0:v]trim=start={i * 0.8}:end={(i + 1) * 0.8},"
                      f"setpts=PTS-STARTPTS[t{i}]")
    # Se alternan de los extremos hacia el centro: cada corte enfrenta dos
    # instantes lejanos del original, así que el salto de contenido es real.
    orden = []
    izq, der = 0, trozos - 1
    while izq <= der:
        orden.append(izq)
        if der != izq:
            orden.append(der)
        izq, der = izq + 1, der - 1
    cadena = "".join(f"[t{i}]" for i in orden)
    partes.append(f"{cadena}concat=n={len(orden)}:v=1:a=0[v]")
    rc, _ = await _corre([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(origen), "-filter_complex", ";".join(partes),
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(destino)], timeout=300)
    if rc != 0 or not destino.exists():
        raise EstiloError("ffmpeg no pudo fabricar el ataque de montaje")


async def ataca(biblia: BibliaDeEstilo, referencia: str | Path,
                carpeta: str | Path) -> InformeAdversario:
    """Fabrica un contraejemplo por eje y comprueba que el medidor lo caza.

    Devuelve un informe. No arregla nada, no ajusta umbrales y no toca el
    medidor: eso es de Ritsuko y Ritsuko solo mira.
    """
    ref = Path(referencia)
    dest = Path(carpeta)
    dest.mkdir(parents=True, exist_ok=True)
    inf = InformeAdversario()
    # La referencia se mide UNA vez: es contra ella contra la que se comprueba
    # que cada ataque llegó a mover su eje.
    medida_ref = await medir(ref, procedencia="obra")

    ejes = [t.eje for t in biblia.tolerancias]
    for eje in ejes:
        if eje not in ATAQUES:
            inf.no_atacados.append(eje)
            continue
        vf, descripcion = ATAQUES[eje]
        a = Ataque(eje=eje, descripcion=descripcion)
        salida = dest / f"adverso_{eje}.mp4"
        try:
            if vf:
                await _fabrica_por_filtro(ref, salida, vf)
            else:
                await _fabrica_picado(ref, salida)
            a.ruta = str(salida)
        except EstiloError as e:
            a.motivo = str(e)
            inf.ataques.append(a)
            continue
        except Exception as e:                        # pragma: no cover
            logger.debug("[adversario] %s: %s", eje, e)
            a.motivo = f"{type(e).__name__}: {e}"
            inf.ataques.append(a)
            continue

        medida = await medir(salida, procedencia="generado")

        # ¿ATACÓ SIQUIERA? Comprobación imprescindible, y la lección viene de
        # pagarla dos veces.
        #
        # La primera con el color: `eq=saturation=0.08` movía la saturación de
        # 0,313 a 0,265 pese a pedir una reducción del 92%. La segunda con el
        # montaje: picar y reordenar un plano homogéneo —un fondo verde con un
        # objeto pequeño cruzando— no produce cortes visibles, porque los
        # trozos se parecen entre sí.
        #
        # En los dos casos el informe decía «ESCAPA», que se lee como «el
        # medidor es ciego a este eje». Y la conclusión correcta era la
        # contraria: el ataque no había atacado. Mandar a tocar el medidor por
        # eso es el peor resultado posible de una auditoría — deja el
        # instrumento peor de lo que estaba, y con la firma de un auditor.
        #
        # Se mide si el eje se movió DE VERDAD respecto a la referencia. Si no
        # se movió, el veredicto no puede decir nada de ese eje, y se declara
        # así en vez de acusar.
        antes = getattr(medida_ref, eje, None)
        ahora = getattr(medida, eje, None)
        tol = next(t for t in biblia.tolerancias if t.eje == eje)
        if antes is not None and ahora is not None and \
                abs(float(ahora) - float(antes)) <= tol.margen:
            a.aplicable = False
            a.motivo = (
                f"el ataque no movió el eje: {eje} pasó de {antes:.4g} a "
                f"{ahora:.4g}, dentro del margen de {tol.margen:.4g}. No dice "
                f"nada del medidor; dice que este material no se deja atacar "
                f"por ahí.")
            inf.ataques.append(a)
            continue

        v = compara(medida, biblia)
        a.suspendidos = [d.eje for d in v.incumplidos]
        a.cazado = eje in a.suspendidos
        a.colaterales = [e for e in a.suspendidos if e != eje]
        inf.ataques.append(a)

    return inf
