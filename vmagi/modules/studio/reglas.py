"""
LAS REGLAS ESCRITAS A MANO: el listón contra el que se mide la búsqueda.

QUÉ SON
=======
Cuatro pasadas de «si este eje falla, mueve este mando en esta dirección».
Las escribí yo mirando qué fallaba en la prueba de extremo a extremo, y
funcionan: apagan el Ken Burns cuando la biblia pide cámara clavada, alargan
los planos cuando salen cortos, drenan la saturación cuando sobra.

POR QUÉ SALEN DE DENTRO DE LA HERRAMIENTA
=========================================
Vivían incrustadas en `animatica_hasta_cumplir`, encima de un diccionario
suelto, y eso tenía dos consecuencias que no se ven hasta que se intenta algo:

1. **No se podían probar.** Comprobar la regla «si la cámara se pasa, apaga el
   Ken Burns» exigía montar un vídeo con ffmpeg. Así que nadie la probaba, y
   las reglas eran la única parte del taller sin un solo test.

2. **No se podían comparar.** `busqueda.py` afirma que buscar supera a estas
   reglas. Esa afirmación es refutable solo si las dos cosas se pueden correr
   sobre el mismo terreno — y para eso tienen que hablar el mismo idioma.

Por eso las reglas y la búsqueda operan ahora sobre el **mismo `Genoma`**. No
es elegancia: es la condición para que el experimento signifique algo. Dos
optimizadores que mueven parámetros distintos no se pueden comparar, se pueden
contar historias el uno del otro.

QUÉ SIGUEN SIENDO
=================
Un buen punto de partida. La siembra desde la biblia —leer el contrato ANTES
de la primera pasada en vez de gastar una pasada descubriéndolo— es
información gratis que la búsqueda también usa, y por eso `busqueda.siembra()`
llama aquí en vez de reimplementarla.
"""
from __future__ import annotations

from dataclasses import replace

from .biblia import BibliaDeEstilo
from .busqueda import UMBRAL_ZOOM, Genoma, _acota

#: Zoom que se pone cuando la biblia NO pide cámara clavada. Un valor pequeño:
#: el Ken Burns es un recurso de animática, no una grúa.
ZOOM_SUAVE = 0.08


def siembra_desde_biblia(biblia: BibliaDeEstilo,
                         base: Genoma | None = None) -> tuple[Genoma, list[str]]:
    """Lee el contrato ANTES de la primera pasada. Devuelve (genoma, porqués).

    Medido en la prueba de extremo a extremo: con Ken Burns activado, la
    animática mide 11,31 px de movimiento de cámara contra una biblia que pide
    0 ± 0,2. Ken Burns ES un movimiento de cámara —es literalmente su
    propósito—, así que arrancar con él encendido frente a una dirección de
    cámara fija garantiza suspender la primera pasada por algo que estaba
    escrito en el contrato desde el principio.

    Reaccionar es correcto cuando no se sabía. Aquí sí se sabía: gastar una
    pasada entera en descubrirlo es gastar ración por no leer.
    """
    from .estilo import UMBRAL_CAMARA_FIJA

    g = base or Genoma()
    porques: list[str] = []
    tol = {t.eje: t for t in biblia.tolerancias}

    if "camara_px" in tol:
        techo = tol["camara_px"].objetivo + tol["camara_px"].margen
        if techo <= UMBRAL_CAMARA_FIJA:
            g = replace(g, zoom=0.0)
            porques.append(
                f"ken_burns apagado de entrada: la biblia pide la cámara por "
                f"debajo de {techo:.2f} px")
    elif "fraccion_camara_fija" in tol:
        # Si no hay eje de movimiento pero sí de cámara fija, dice lo mismo por
        # el otro lado. Cerrar solo el primero dejaba la mitad del contrato sin
        # leer.
        fija = tol["fraccion_camara_fija"].objetivo
        g = replace(g, zoom=0.0 if fija > 0.9 else ZOOM_SUAVE)
        porques.append(
            f"zoom {'apagado' if fija > 0.9 else 'suave'}: la biblia pide "
            f"cámara fija el {fija:.0%} del tiempo")

    if "duracion_media_plano" in tol:
        seg = _acota("segundos_plano", tol["duracion_media_plano"].objetivo)
        g = replace(g, segundos_plano=seg)
        porques.append(
            f"{seg:.2f}s por plano, tomado de la biblia en vez del valor por "
            f"defecto")
    return g, porques


def aplica_reglas(g: Genoma, correcciones: list[str]) -> Genoma:
    """Mueve un mando por cada eje incumplido. Función pura sobre el genoma.

    Cada corrección llega como la frase que produce `lista_para_reintento()`,
    que trae dentro la DIRECCIÓN («hay que BAJARLO»). Un bucle que reintenta
    con los mismos parámetros no es un bucle: es la misma pasada cuatro veces.

    Los topes son deliberados. `eq` admite saturación 0-3, y dejar que el bucle
    se pase produce una imagen gris o de cómic que ya no se parece a nada pero
    que puede acercarse por casualidad en el eje que se estaba persiguiendo —
    ganar el eje perdiendo la película.
    """
    for c in correcciones:
        baja = "BAJARLO" in c
        if c.startswith("camara_px") and baja:
            g = replace(g, zoom=0.0)
        elif c.startswith("fraccion_camara_fija") and not baja:
            g = replace(g, zoom=0.0)
        elif c.startswith("duracion_media_plano"):
            g = replace(g, segundos_plano=_acota(
                "segundos_plano", g.segundos_plano * (0.65 if baja else 1.6)))
        elif c.startswith("saturacion"):
            g = replace(g, saturacion=_acota(
                "saturacion", g.saturacion * (0.72 if baja else 1.35)))
        elif c.startswith("luma"):
            g = replace(g, brillo=_acota(
                "brillo", g.brillo + (-0.10 if baja else 0.10)))
        elif c.startswith("contraste"):
            g = replace(g, contraste=_acota(
                "contraste", g.contraste * (0.75 if baja else 1.3)))
    return g


def describe(g: Genoma) -> str:
    """Los parámetros finales, en la forma en que el informe los enseñaba."""
    return (f"{g.segundos_plano:.2f}s por plano, "
            f"ken_burns={'sí' if g.zoom >= UMBRAL_ZOOM else 'no'}, "
            f"etalonaje={g.grado or 'ninguno'}")
