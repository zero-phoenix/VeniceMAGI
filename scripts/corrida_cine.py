"""
CORRIDA DE EXTREMO A EXTREMO DEL TALLER DE CINE.

Fabrica una referencia, la mide, saca la biblia, audita el medidor contra
ella, mina el corpus, monta stills que NO salen de la referencia y lanza la
busqueda evolutiva hasta que el corte cumpla o se acabe el plazo.

Todo pasa por el REGISTRO DE HERRAMIENTAS del enjambre, no por las funciones
a pelo: si una capacidad no se puede invocar desde ahi, no existe para el
sistema (regla 3).

LA REFERENCIA POR DEFECTO ES SINTETICA Y SE DECLARA COMO TAL. Sus numeros
estan bien medidos y no son los de ninguna pelicula: son los que elegi al
construir el material. Sirve para probar la tuberia entera sin depender de
nadie, y eso es exactamente para lo que sirve.

CON MATERIAL DE VERDAD:

    python scripts/corrida_cine.py mi_grabacion.mp4

Se salta la fabricacion, mide TU fichero con procedencia "obra" y sigue igual.
Es la unica diferencia entre probar la tuberia y dirigir con ella.

El segundo argumento es el plazo de la busqueda en segundos:

    python scripts/corrida_cine.py mi_grabacion.mp4 7200
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "corrida-cine"
sys.path.insert(0, str(RAIZ))


def corre(args: list[str], plazo: int = 600) -> None:
    r = subprocess.run(args, capture_output=True, timeout=plazo)
    if r.returncode != 0:
        raise RuntimeError(
            f"{args[0]} fallo: {r.stderr.decode('utf-8', 'replace')[-800:]}")


# ------------------------------------------------------------ la referencia

def fabrica_referencia(destino: Path) -> None:
    """Tres planos largos, camara clavada, interior en penumbra, alguien que
    cruza el cuadro, y dialogo con pausas.

    Cada decision es una propiedad MEDIBLE, no un adorno:

      · 1.85:1 dentro de un contenedor 16:9 con barras -> obliga al medidor a
        encontrar el area activa en vez de leer el contenedor.
      · tres planos de ~9 s -> hay montaje que medir (>= 3 planos) y los planos
        son largos (duracion_media_plano alta).
      · sin paneo ni zoom -> camara_px ~ 0 y fraccion_camara_fija ~ 1.
      · verdes y maderas apagados, luz baja -> saturacion baja, luma baja.
      · una figura clara que cruza -> sujeto_residual > 0 con la camara quieta,
        que es la firma exacta de este cine.
      · tonos en la banda de la voz con silencios largos entre ellos -> turnos
        por minuto bajos y pausas largas.
    """
    fondos = ["0x3A4A38", "0x4A4034", "0x33403E"]     # jardin, madera, sombra
    trozos = []
    for i, color in enumerate(fondos):
        t = destino.parent / f"_plano{i}.mp4"
        # La figura cruza a distinta velocidad en cada plano y en distinta
        # altura: si fuera identica, los tres planos serian el mismo y el
        # medidor no encontraria los cortes.
        vel, alto = 26 + i * 9, 150 + i * 40
        corre([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=854x462:d=9:r=24",
            "-f", "lavfi", "-i", "color=c=0xC8BCA4:s=34x86:d=9:r=24",
            "-filter_complex",
            # rejilla tenue = textura, para que el histograma tenga con que
            # distinguir un plano de otro
            f"[0:v]drawgrid=w=61:h=61:t=1:c=0x6B5B45@0.35[bg];"
            f"[bg][1:v]overlay=x='40+{vel}*t':y={alto}[img];"
            # las barras: 854x462 es 1.85:1; dentro de 854x480 quedan 9 arriba
            # y 9 abajo, que es lo que el area activa tiene que recortar
            f"[img]pad=854:480:0:9:black[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", str(t)])
        trozos.append(t)

    lista = destino.parent / "_lista.txt"
    lista.write_text("".join(f"file '{t.name}'\n" for t in trozos),
                     encoding="utf-8")
    mudo = destino.parent / "_mudo.mp4"
    corre(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", str(lista),
           "-c", "copy", str(mudo)])

    # Dialogo: cuatro intervenciones de ~1,6 s en la banda de la voz, separadas
    # por silencios de 4 a 6 s. Es la cadencia, no el contenido: el medidor
    # cuenta tramos de sonido sostenido y las pausas entre ellos.
    voz = ("sine=f=210:d=27,volume='"
           "if(between(t,1.2,2.8),0.5,"
           "if(between(t,7.5,9.3),0.5,"
           "if(between(t,14.0,15.4),0.5,"
           "if(between(t,21.0,23.0),0.5,0.0))))':eval=frame")
    corre(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(mudo), "-f", "lavfi", "-i", voz,
           "-c:v", "copy", "-c:a", "aac", "-shortest", str(destino)])

    for t in [*trozos, lista, mudo]:
        t.unlink(missing_ok=True)


def fabrica_stills(carpeta: Path) -> list[Path]:
    """Cinco imagenes que NO salen de la referencia.

    A PROPOSITO. Sacarlas del propio material haria que la busqueda ganara sin
    hacer nada: la paleta ya seria la correcta. Estas nacen mas claras, mas
    saturadas y mas frias, asi que el etalonaje tiene que trabajar de verdad
    para acercarlas a la biblia. Un experimento en el que el candidato empieza
    en la meta no mide nada.
    """
    escenas = [
        ("0x7FA36B", "0xF2E9D0", "corredor"),
        ("0x8FA0B8", "0xEFD9B8", "ventana"),
        ("0xA88F6A", "0xF6EEDC", "mesa"),
        ("0x6E9E9A", "0xE8DCC8", "cocina"),
        ("0x9B8AA6", "0xF0E4CE", "umbral"),
    ]
    fuera = []
    for i, (fondo, luz, nombre) in enumerate(escenas):
        p = carpeta / f"still{i}_{nombre}.png"
        corre([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={fondo}:s=1280x720",
            "-f", "lavfi", "-i", f"color=c={luz}:s=210x{300 + i * 40}",
            "-filter_complex",
            f"[0:v]drawgrid=w=80:h=80:t=2:c=0x33322E@0.5[bg];"
            f"[bg][1:v]overlay=x={120 + i * 170}:y={720 - (300 + i * 40)}[v]",
            "-map", "[v]", "-frames:v", "1", str(p)])
        fuera.append(p)
    return fuera


# ------------------------------------------------------------------ la corrida

async def main() -> int:
    from vmagi.core.tools.registry import ToolRegistry
    from vmagi.modules.studio.tools import register_studio_tools

    SALIDA.mkdir(parents=True, exist_ok=True)
    reg = register_studio_tools(ToolRegistry())
    diario: list[dict] = []

    async def usa(_herramienta: str, **kw):
        """Invoca una herramienta REAL del registro y deja constancia.

        El parametro se llama `_herramienta` y no `nombre` porque varias de
        las herramientas TIENEN un argumento `nombre`, y entonces
        `usa("biblia_de_estilo", nombre="...")` choca. Un envoltorio que se
        pelea por los nombres con lo que envuelve es un envoltorio mal hecho.
        """
        t = reg.get(_herramienta)
        if t is None:
            raise SystemExit(f"el registro no tiene '{_herramienta}'")
        t0 = time.monotonic()
        r = await t.handler(**kw)
        seg = time.monotonic() - t0
        print(f"\n{'=' * 72}\n[{_herramienta}]  ok={r.ok}  {seg:.1f}s\n{'=' * 72}")
        print(r.content or r.error)
        diario.append({"herramienta": _herramienta, "ok": bool(r.ok),
                       "segundos": round(seg, 2),
                       "error": r.error, "meta": r.meta})
        return r

    # «-» = sin material propio. Hace falta un hueco explicito porque el
    # segundo argumento es el plazo, y en algunas consolas una cadena vacia no
    # llega a ser un argumento.
    propia = sys.argv[1] if len(sys.argv) > 1 else ""
    if propia == "-":
        propia = ""
    if propia:
        ref = Path(propia).resolve()
        if not ref.exists():
            raise SystemExit(f"no existe {ref}")
        procedencia, nombre = "obra", ref.stem
        print(f">> midiendo TU material: {ref}")
    else:
        ref = SALIDA / "referencia_sintetica.mp4"
        procedencia, nombre = "sintetica", "penumbra domestica"
        print(">> sin material propio: fabricando la referencia sintetica...")
        fabrica_referencia(ref)
        print(f">> {ref} ({ref.stat().st_size // 1024} KB)")

    await usa("medir_estilo", path=str(ref), procedencia=procedencia)

    biblia = SALIDA / "biblia.json"
    await usa("biblia_de_estilo", referencia=str(ref), out_path=str(biblia),
              nombre=nombre, procedencia=procedencia, holgura=0.12)

    await usa("auditar_medidor", referencia=str(ref), biblia=str(biblia),
              carpeta=str(SALIDA / "adversario"))

    await usa("minar_corpus", referencia=str(ref),
              destino=str(SALIDA / "corpus"))

    print("\n>> fabricando stills que NO salen de la referencia...")
    stills = fabrica_stills(SALIDA)

    # `auditado=True` porque el adversario ya paso por esta misma biblia unas
    # lineas mas arriba. El aviso de la busqueda es correcto por defecto —una
    # busqueda optimiza lo que se le mide— pero repetirlo cuando la auditoria
    # SI se hizo entrena a la gente a saltarse los avisos, que es peor que no
    # tenerlos.
    # EL PLAZO ES UN ARGUMENTO, y el valor por defecto sale de una medicion.
    #
    # Con 600 s la busqueda hizo 27 evaluaciones y se quedo a medias: la
    # saturacion la arreglo, la luz y el contraste no. En el banco sintetico
    # convergia con 138-194 evaluaciones. A ~22 s por candidato en esta
    # maquina, eso son unos 4000 s. Aqui la electricidad es gratis y la
    # tarjeta es tuya, asi que el plazo largo es el normal y el corto es el
    # que hay que justificar.
    plazo = float(sys.argv[2]) if len(sys.argv) > 2 else 4500.0
    print(f"\n>> plazo de busqueda: {plazo:.0f}s "
          f"(~{plazo / 22:.0f} evaluaciones a 22 s por candidato)")
    r = await usa("buscar_parametros", imagenes=[str(s) for s in stills],
                  biblia=str(biblia), out_dir=str(SALIDA / "busqueda"),
                  presupuesto_s=plazo, auditado=True, semilla=7)

    mejor = (r.meta or {}).get("mejor")
    if mejor:
        final = SALIDA / "corto.mp4"
        Path(mejor).replace(final)
        await usa("juzgar_estilo", path=str(final), biblia=str(biblia))
        await usa("observe_artifact", path=str(final), kind="video")

    (SALIDA / "diario.json").write_text(
        json.dumps(diario, indent=1, ensure_ascii=False), encoding="utf-8")
    fallos = [d["herramienta"] for d in diario if not d["ok"]]
    print(f"\n\nTERMINADO. {len(diario)} herramientas invocadas. "
          f"Fallaron: {fallos or 'ninguna'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
