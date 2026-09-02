"""
LOS OÍDOS: medir una banda sonora sin oírla.

POR QUÉ MEDIR Y NO ESCUCHAR
===========================
Nadie en esta cadena oye —ni los proveedores guest, ni el sistema, ni quien lo
supervisa desde fuera—. Pero para dirigir no hace falta una impresión
auditiva: hacen falta números que se puedan comparar contra el corte generado.
Si domina el ambiente y no hay música bajo el diálogo, eso se ve en la
envolvente y en el reparto de energía por bandas, y se ve MEJOR que oyéndolo,
porque sale una cifra que se puede enfrentar a otra.

QUÉ MIDE, Y QUÉ SE NIEGA A FINGIR
=================================
Mide: envolvente RMS, fracción de silencio con umbral relativo al propio
material, rango dinámico, reparto de energía en la banda de la voz, y la
cadencia de los turnos —cuántos, cuánto duran, cuánto se calla entre ellos y
cuál fue el silencio más largo.

NO mide, y lo declara: quién habla en cada turno, ni si dos voces se solapan.
Eso exige diarización, que es un modelo, y este sistema todavía no lo tiene en
local. La cadencia sí sale de la misma envolvente: cero dependencias, cero
modelos, cero VRAM.

Vive aparte de `estilo.py` por el trinquete de líneas, y el corte cae donde el
propio docstring del medidor ya separaba las cosas: ojos y oídos.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from .estilo import AUDIO_HZ, AUDIO_VENTANA, MedidaEstilo, _corre

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------- los oídos

async def _mide_audio(ruta: Path, medida: MedidaEstilo) -> None:
    """Mide la banda sonora. No la escucha: la mide.

    POR QUÉ MEDIR Y NO ESCUCHAR
    ===========================
    Nadie en esta cadena —ni los proveedores guest, ni el sistema— oye. Pero
    lo que hace falta para dirigir no es una impresión auditiva: son números.
    Si el ambiente domina y no hay música bajo el diálogo, eso se ve en la
    envolvente y en el reparto de energía por bandas, y se ve mejor que
    oyéndolo, porque sale un número que se puede comparar contra el corte
    generado.

    Lo que NO se mide aquí, y se declara: quién habla, qué dice, y si dos
    voces se solapan. Separar voces exige diarización, que es un modelo. En
    cuanto el cascarón local tenga uno, entra por esta misma puerta.
    """
    import numpy as np

    rc, crudo = await _corre([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(ruta), "-vn", "-ac", "1", "-ar", str(AUDIO_HZ),
        "-f", "s16le", "-"], timeout=300)
    if rc != 0 or len(crudo) < AUDIO_HZ:
        medida.tiene_audio = False
        medida.no_medido.append(
            "sin pista de audio utilizable: no se ha medido nada del sonido")
        return

    medida.tiene_audio = True
    x = np.frombuffer(crudo, dtype="<i2").astype(np.float32) / 32768.0
    n_v = max(1, int(AUDIO_HZ * AUDIO_VENTANA))
    n_ventanas = len(x) // n_v
    if n_ventanas < 4:
        medida.no_medido.append("audio demasiado corto para medir")
        return
    marco = x[:n_ventanas * n_v].reshape(n_ventanas, n_v)

    rms = np.sqrt((marco ** 2).mean(axis=1) + 1e-12)
    medida.rms_medio = round(float(rms.mean()), 5)

    # Umbral de silencio RELATIVO al propio material, no absoluto. Un absoluto
    # declara «todo silencio» en una mezcla suave y «nada de silencio» en una
    # ruidosa, y las dos lecturas son del volumen de masterizado, no del cine.
    pico = float(np.percentile(rms, 95))
    umbral = max(pico * 0.06, 1e-4)
    medida.fraccion_silencio = round(float((rms < umbral).mean()), 4)

    p95, p05 = float(np.percentile(rms, 95)), float(np.percentile(rms, 5))
    medida.rango_dinamico_db = round(
        20.0 * math.log10(max(p95, 1e-9) / max(p05, 1e-9)), 2)

    # Reparto de energía por bandas sobre las ventanas con sonido. La banda de
    # la voz (300-3400 Hz) dominando indica diálogo y ambiente; una cola de
    # graves fuerte indica música con base.
    activas = marco[rms >= umbral]
    if len(activas) >= 4:
        vent = np.hanning(n_v).astype(np.float32)
        esp = np.abs(np.fft.rfft(activas * vent, axis=1)) ** 2
        frec = np.fft.rfftfreq(n_v, 1.0 / AUDIO_HZ)
        voz = esp[:, (frec >= 300) & (frec <= 3400)].sum(axis=1)
        total = esp.sum(axis=1) + 1e-12
        ratio = voz / total
        medida.fraccion_banda_voz = round(float((ratio > 0.5).mean()), 4)
        medida.evidencia.append(
            f"audio: {n_ventanas} ventanas de {AUDIO_VENTANA * 1000:.0f} ms · "
            f"silencio {medida.fraccion_silencio:.0%} · "
            f"rango {medida.rango_dinamico_db:.1f} dB")
    else:
        medida.no_medido.append(
            "casi todo el audio está por debajo del umbral: no se ha podido "
            "repartir la energía por bandas")

    _mide_turnos(rms, umbral, n_v / AUDIO_HZ, medida)

    medida.no_medido.append(
        "QUIÉN habla en cada turno: exige diarización, que este sistema "
        "todavía no tiene en local. El ritmo de los turnos sí se mide; la "
        "identidad del hablante y el solapamiento de dos voces, no")


#: Un tramo de sonido más corto que esto no es un turno: es un golpe, una
#: puerta, una sílaba suelta entre dos pausas. Contarlo dispararía la cuenta
#: de turnos con ruido de sala.
TURNO_MINIMO_S = 0.30

#: Una pausa más corta que esto NO separa dos turnos: es la respiración de
#: dentro de una frase. Sin unir estos huecos, una sola réplica se contaría
#: como ocho turnos y la cadencia medida sería la de las sílabas.
PAUSA_MINIMA_S = 0.28


def _mide_turnos(rms, umbral: float, paso_s: float,
                 medida: MedidaEstilo) -> None:
    """Cadencia del diálogo a partir de la envolvente que ya está calculada.

    POR QUÉ ESTO Y NO DIARIZACIÓN
    =============================
    Separar voces exige un modelo, y este sistema todavía no lo tiene. Pero la
    pregunta que hay que responder para dirigir no es «¿quién habla?»: es «¿a
    qué ritmo se habla y cuánto se calla?». Y eso sale de la misma envolvente
    RMS que ya se midió para el silencio: cero dependencias, cero modelos,
    cero VRAM.

    En un cine de mesa de comedor —conversación continua, cámara clavada, lo
    importante en lo que no se dice— la pausa larga no es un hueco entre
    tomas: es la toma. `pausa_maxima` va aparte de `pausa_media` justo por
    eso: un silencio de seis segundos en mitad de una conversación es una
    decisión de dirección, y promediarlo con pausas de medio segundo lo borra.

    NO se declara como diarización ni se parece. Lo que no mide sigue en
    `no_medido`, que es la respuesta correcta y no la deseable.
    """
    import numpy as np

    sonando = np.asarray(rms >= umbral)
    if sonando.size < 4:
        return

    # Tramos contiguos de sonido y de silencio, en número de ventanas.
    cambios = np.flatnonzero(np.diff(sonando.astype(np.int8))) + 1
    bordes = np.concatenate(([0], cambios, [sonando.size]))
    tramos = [(int(bordes[i]), int(bordes[i + 1]), bool(sonando[bordes[i]]))
              for i in range(len(bordes) - 1)]

    # Se cosen los silencios cortos: son respiración dentro de una frase, no
    # separación entre turnos.
    cosidos: list[tuple[int, int, bool]] = []
    for ini, fin, hay in tramos:
        dur = (fin - ini) * paso_s
        if (not hay and dur < PAUSA_MINIMA_S and cosidos
                and cosidos[-1][2]):
            cosidos[-1] = (cosidos[-1][0], fin, True)
        elif cosidos and cosidos[-1][2] == hay:
            cosidos[-1] = (cosidos[-1][0], fin, hay)
        else:
            cosidos.append((ini, fin, hay))

    turnos = [(f - i) * paso_s for i, f, hay in cosidos
              if hay and (f - i) * paso_s >= TURNO_MINIMO_S]
    # Solo las pausas INTERIORES cuentan. El silencio de antes del primer
    # turno y el de después del último son cabecera y cola del fragmento, no
    # decisiones de ritmo — y en un tráiler que abre en negro, la cabecera
    # sola dispararía la pausa máxima a varios segundos.
    interiores = [i for i, (_, _, hay) in enumerate(cosidos) if hay]
    pausas: list[float] = []
    if len(interiores) >= 2:
        for k in range(interiores[0] + 1, interiores[-1]):
            ini, fin, hay = cosidos[k]
            if not hay:
                pausas.append((fin - ini) * paso_s)

    total_s = sonando.size * paso_s
    if turnos and total_s > 0:
        medida.turnos_por_minuto = round(len(turnos) / (total_s / 60.0), 2)
        medida.duracion_media_turno = round(sum(turnos) / len(turnos), 3)
    if pausas:
        medida.pausa_media = round(sum(pausas) / len(pausas), 3)
        medida.pausa_maxima = round(max(pausas), 3)
        medida.evidencia.append(
            f"ritmo: {len(turnos)} turnos, {len(pausas)} pausas interiores · "
            f"turno medio {medida.duracion_media_turno:.2f}s · pausa media "
            f"{medida.pausa_media:.2f}s · pausa máxima "
            f"{medida.pausa_maxima:.2f}s")
    elif turnos:
        medida.no_medido.append(
            f"solo se detectó {len(turnos)} turno de sonido: sin dos no hay "
            f"pausa interior que medir, y la cadencia queda sin comprobar")

