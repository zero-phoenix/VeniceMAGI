"""
OPERACIONES SOBRE PÍXELES: las funciones puras del medidor.

POR QUÉ VIVEN APARTE
====================
Todo lo de aquí opera sobre arrays ya cargados en memoria. No abre ficheros,
no llama a ffmpeg y no toca la red. Esa frontera es la que las hace
comprobables sin generar un solo vídeo: `_destaca` se prueba con una lista de
números, y `_histograma` con una matriz.

Y es donde vive casi toda la calibración del instrumento, que es
conocimiento caro. Cada constante de este módulo se movió al menos una vez
por un fallo medido, y cada docstring cuenta cuál:

  · La normalización por percentiles, porque estirar por mínimo y máximo
    hacía que un objeto claro tocando el borde remapeara el histograma
    entero — 3 planos donde había 1.
  · El histograma sobre los tres canales, porque en luma normalizada un corte
    entre dos planos de colores distintos y brillo parecido es invisible:
    rojo a verde daba 0,242 contra un umbral de 0,38.
  · La prominencia local, porque un corte es un SALTO y un sujeto que cruza
    el cuadro es una MESETA, y el umbral absoluto no los distingue.
  · La unión de transiciones, porque un encadenado son dos o tres muestras
    seguidas y contarlas sueltas multiplica los planos.

Se separan de `estilo.py` por el trinquete de líneas, y el corte cae donde ya
estaba la costura: medir un FICHERO es una cosa y operar sobre una MATRIZ es
otra.
"""
from __future__ import annotations

import logging
import math

from .estilo import BUSQUEDA_MAX

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ los ojos

def _area_activa(arr, umbral: int = 20):
    """Recorta las barras negras y devuelve (arriba, abajo, izq, der).

    EL FALLO QUE ESTO CIERRA. Leer la relación de aspecto de `ffprobe` da la
    del CONTENEDOR. Una película en 1.85:1 distribuida dentro de un 4:3 con
    barras negras arriba y abajo —que es exactamente cómo llegan casi todos
    los tráileres de 2008— reporta 1.333. Comparar el encuadre de la
    referencia contra el de la salida usando ese número compara dos envases,
    no dos imágenes.
    """
    import numpy as np
    gris = arr.max(axis=2) if arr.ndim == 3 else arr
    filas = np.where(gris.max(axis=1) > umbral)[0]
    cols = np.where(gris.max(axis=0) > umbral)[0]
    if not len(filas) or not len(cols):
        return None
    return int(filas[0]), int(filas[-1]), int(cols[0]), int(cols[-1])


def _desplazamiento_global(a, b, maxd: int = BUSQUEDA_MAX):
    """Estima cuánto se ha MOVIDO LA CÁMARA entre dos fotogramas.

    Busca el desplazamiento entero (dx, dy) que minimiza la diferencia
    absoluta entre los dos fotogramas. Es correlación por fuerza bruta sobre
    una imagen ya reducida: barato, determinista y sin dependencias.

    POR QUÉ ESTO Y NO «CUÁNTOS PÍXELES CAMBIAN»
    -------------------------------------------
    `observe_video` cuenta píxeles que cambian, y con eso distingue movimiento
    de congelado. Pero no distingue las dos cosas que aquí hay que separar:

        cámara quieta + gente moviéndose   -> muchos píxeles cambian, (0,0)
        cámara moviéndose + nada más       -> muchos píxeles cambian, (dx,dy)

    Para una dirección de cámara fija, el primero es lo pedido y el segundo
    es el fallo — y contando píxeles los dos dan el mismo número. El
    desplazamiento óptimo los separa: la cámara se mide por (dx,dy), el
    sujeto por lo que queda después de compensarlo.

    Devuelve (magnitud, residual, saturado).
    """
    import numpy as np
    mejor, mejor_dx, mejor_dy = None, 0, 0
    h, w = a.shape
    m = maxd
    if h <= 2 * m + 2 or w <= 2 * m + 2:
        m = max(1, min(h, w) // 4)
    centro_a = a[m:h - m, m:w - m]
    for dy in range(-m, m + 1):
        for dx in range(-m, m + 1):
            trozo = b[m + dy:h - m + dy, m + dx:w - m + dx]
            if trozo.shape != centro_a.shape:
                continue
            d = float(np.abs(centro_a - trozo).mean())
            if mejor is None or d < mejor:
                mejor, mejor_dx, mejor_dy = d, dx, dy
    if mejor is None:
        return 0.0, 0.0, False
    magnitud = math.hypot(mejor_dx, mejor_dy)
    # Si el óptimo cae en el borde de la ventana, el movimiento real puede ser
    # mayor y este número es un suelo, no una medida. Se dice.
    saturado = abs(mejor_dx) >= m or abs(mejor_dy) >= m
    return magnitud, mejor, saturado


def _histograma(rgb, bins: int = 16):
    """Histograma NORMALIZADO en exposición, para que un corte sea un corte.

    EL ACOPLAMIENTO QUE ESTO ROMPE, ENCONTRADO EJECUTÁNDOLO
    =======================================================
    Un corte es un cambio de CONTENIDO. Comparar histogramas crudos lo
    confunde con un cambio de EXPOSICIÓN, y eso no es una sutileza teórica:
    en cuanto el bucle de autocorrección aprendió a etalonar para acercar la
    paleta a la biblia, empezó a aplanar el contraste —`contrast=0.422`— y al
    aplanarlo los histogramas de dos planos distintos se parecían lo bastante
    como para caer por debajo del umbral. Los cortes DESAPARECÍAN.

    Consecuencia medida: el mismo montaje pasaba de 3 planos a 2, la duración
    media de plano se disparaba de 5,7 s a 13,9 s, y el bucle se ponía a
    corregir la duración de los planos por un cambio que había hecho él mismo
    en el color. Corregir un eje rompía la medición de otro, y el sistema
    perseguía su propio reflejo.

    Se estira cada fotograma a rango completo antes de contar. Así un cambio
    global de brillo o de contraste no mueve el histograma, y lo que lo mueve
    es lo que tiene que moverlo: que en el cuadro haya otra cosa.

    El guardia del rango pequeño no es cosmético: un fotograma casi plano —un
    fundido a negro, una pared— tiene un rango de dos o tres niveles, y
    estirarlo a 255 amplifica el ruido de compresión hasta convertir dos
    fotogramas idénticos en un corte.
    """
    import numpy as np
    a = np.asarray(rgb, dtype=np.float32)
    g = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    # PERCENTILES, NO MIN Y MAX. Y esto lo enseñó el adversario.
    #
    # La primera versión estiraba entre el mínimo y el máximo absolutos. Son
    # dos valores que dependen de UN píxel cada uno, así que un objeto claro
    # entrando o saliendo del cuadro cambia el máximo y remapea el histograma
    # entero. Medido sobre un plano ÚNICO y continuo con un rectángulo claro
    # cruzándolo: distancias de base 0,15 con dos picos de 0,70 justo cuando
    # el objeto tocaba el borde. Tres planos donde hay uno.
    #
    # Es el fallo clásico de normalizar por extremos, y lo irónico es que
    # apareció al arreglar OTRO fallo: la normalización se metió para que el
    # etalonaje no borrase los cortes, y de paso inventó cortes nuevos. Un
    # arreglo que crea el problema simétrico es medio arreglo.
    # SE MIRA EL COLOR, NO SOLO LA LUMINANCIA. Y esto también lo enseñó el
    # adversario, en el mismo sitio y con la ironía completa.
    #
    # La normalización de exposición se metió para que el etalonaje no borrase
    # los cortes. Funcionó, y de paso borró otra cosa: si el histograma solo
    # cuenta luminancia y además se normaliza, un corte entre dos planos de
    # colores distintos pero brillo parecido se vuelve INVISIBLE.
    #
    # Medido sobre una animática de rojo -> verde -> azul con encadenados: el
    # corte rojo/verde daba 0,242 de distancia, muy por debajo del umbral de
    # 0,38, mientras el verde/azul daba 0,563. Un detector que ve unos cortes
    # sí y otros no según los colores que se cruzan no es un detector.
    #
    # La solución conserva las dos propiedades a la vez: se calcula la escala
    # de normalización sobre la LUMA y se aplica IGUAL a los tres canales. Un
    # cambio global de exposición se cancela —los tres se mueven juntos—;
    # una diferencia de tono sobrevive, porque lo que la define es la
    # proporción ENTRE canales y esa no la toca una escala común.
    lo, hi = np.percentile(g, (2.0, 98.0))
    if hi - lo > 12.0:
        a = np.clip((a - lo) * (255.0 / (hi - lo)), 0.0, 255.0)
    trozos = [np.histogram(a[..., c], bins=bins, range=(0, 255))[0]
              for c in range(3)]
    h = np.concatenate(trozos).astype(np.float64)
    s = h.sum()
    return h / s if s else h


def _distancia_hist(h1, h2) -> float:
    """Distancia L1 normalizada entre histogramas, de 0 a 1."""
    import numpy as np
    return float(np.abs(h1 - h2).sum() / 2.0)


#: Cuánto tiene que destacar un pico sobre su vecindario para ser un corte.
#: Un corte es un salto; un sujeto que cruza el cuadro es una MESETA.
PROMINENCIA_CORTE = 2.2

#: Muestras a cada lado que forman el vecindario. Con 4 a 5 fps son 0,8 s por
#: lado: bastante para ver si el cambio es un pico o el estado normal de ese
#: tramo, y poco para no meter dentro el corte siguiente.
VECINDARIO_CORTE = 4


def _destaca(distancias: list[float], i: int) -> bool:
    """¿Es este pico un CORTE, o el ruido normal de un plano con movimiento?

    EL FALSO POSITIVO QUE ESTO CIERRA, ENCONTRADO POR EL ADVERSARIO
    ==============================================================
    El umbral absoluto solo pregunta «¿cambió mucho la imagen?». Un corte
    cambia mucho la imagen; un objeto claro y grande cruzando un plano fijo,
    también. Medido sobre la referencia del adversario —un plano ÚNICO y
    continuo, cámara clavada, con un rectángulo claro atravesando el cuadro—
    el detector encontraba **3 planos donde hay 1**.

    Y eso envenena todo lo que cuelga de ahí: la duración media de plano sale
    a un tercio de la real, la biblia se construye con esa cifra, y el bucle
    persigue un ritmo de montaje que nadie pidió.

    La diferencia entre las dos cosas no está en la altura del pico, está en
    su forma. Un corte es un SALTO: una muestra alta entre muestras bajas. Un
    sujeto en movimiento es una MESETA: muchas muestras seguidas parecidas
    entre sí, porque el objeto sigue cruzando. Se compara el pico con la
    mediana de su vecindario y se exige que destaque.

    La mediana y no la media, porque la media de un vecindario que contiene
    otro corte se dispara y esconde el pico que se está juzgando.
    """
    n = len(distancias)
    ini, fin = max(0, i - VECINDARIO_CORTE), min(n, i + VECINDARIO_CORTE + 1)
    vecinos = sorted(distancias[j] for j in range(ini, fin) if j != i)
    if not vecinos:
        return True
    mediana = vecinos[len(vecinos) // 2]
    # Un vecindario prácticamente quieto no puede dividir por cero ni exigir
    # una prominencia infinita: por debajo de este suelo, el umbral absoluto
    # ya es criterio suficiente.
    if mediana < 0.02:
        return True
    return distancias[i] >= mediana * PROMINENCIA_CORTE


def _une_transiciones(picos: list[int]) -> list[int]:
    """Un encadenado es UN corte, no tres.

    EL FALLO QUE ESTO CIERRA, ENCONTRADO EJECUTÁNDOLO
    =================================================
    Un corte seco es un salto instantáneo: un único pico de distancia entre
    dos fotogramas consecutivos. Un encadenado dura medio segundo, y a 5
    muestras por segundo eso son dos o tres pares seguidos por encima del
    umbral. Contarlos sueltos convierte cada transición gradual en dos o tres
    cortes.

    Medido en la prueba de extremo a extremo del 2026-09-02: una animática de
    TRES imágenes con encadenados salía con **6 planos**, y la duración media
    de plano por tanto a la mitad de la real. Y eso no se quedó en un número
    feo: el bucle de autocorrección leyó «los planos duran poco, SÚBELOS» y
    subió de 6 a 15,36 segundos por plano persiguiendo un objetivo que nunca
    podía alcanzar, porque el error no estaba en la duración sino en el
    recuento. Una medida mal hecha no da un informe peor: da un sistema que
    corrige en la dirección equivocada con toda la autoridad de un dato.

    Se unen los índices CONSECUTIVOS, y solo esos. Un corte seco real sigue
    siendo un pico aislado, así que el montaje rápido no se penaliza: lo que
    se colapsa es exactamente la firma de una transición gradual.
    """
    if not picos:
        return []
    unidos = [picos[0]]
    for p in picos[1:]:
        if p != unidos[-1] + 1:
            unidos.append(p)
        else:
            unidos[-1] = p          # sigue el mismo fundido: se extiende
    return unidos

