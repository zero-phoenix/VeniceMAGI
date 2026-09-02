"""
«Conecta o borra» deja de ser una norma y pasa a ser un trinquete.

LA LECCIÓN Nº2, POR ESCRITO Y CON MECANISMO
===========================================
El README lo dice: *conecta o borra*. Era una norma —algo que se cumple
mientras alguien se acuerde— y el historial demuestra que no basta. Aparecieron
una detrás de otra:

  · `MetricsCollector`, construido, probado y enganchado al bus, sin nadie que
    llamara a `obs.metrics`. El panel de salud no existía.
  · `eval.run` y `naoko.self_improve`: motor completo, ningún botón.
  · `record_usage()` nunca llamado, con `token_ledger` vacía desde su creación.
  · La tabla `task_event`, creada en la migración 0001 y sin una sola escritura
    hasta cuatro fases más tarde.

Ninguno rompía un test. El sistema funcionaba: solo tenía piezas que no hacían
nada. La única forma de encontrarlas fue que alguien se sentara a auditar a
mano, y eso no escala ni se repite.

QUÉ HACE ESTE TEST, Y QUÉ NO
============================
NO exige cero. Hoy hay 108, y ponerlo en cero significaría o borrar módulos
enteros de golpe o llenar la lista de excepciones hasta vaciarla de sentido.

Lo que hace es impedir que la cifra SUBA. Es un trinquete: el número puede
bajar cuando alguien conecte o retire una pieza, y bajarlo actualiza el techo.
Lo que no puede es crecer sin que se vea, que es exactamente como llegó a 108.

Mismo criterio que ya se aplica al lint en el CI: la deuda existente se publica
y se salda cuando toca; lo que no se admite es que aumente en silencio.

SOBRE LOS FALSOS POSITIVOS
==========================
Parte de los 108 son tipos internos con nombre público —un `dataclass` que
devuelve una función del mismo módulo y que nadie nombra desde fuera—. No son
código muerto: son nombres que deberían empezar por `_`. Que aparezcan aquí es
correcto y además señala algo real, aunque la acción no sea borrarlos.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "huerfanos.py"

#: techo actual. Solo puede bajar. Si bajas, baja también este número en el
#: mismo commit: es la mitad del trinquete que hace que sirva de algo.
#:
#: 80 desde el 2026-08-16 (recalibrado): el conteo local daba 70 porque el
#: indice de uso leía .venv-lock/site-packages y otros directorios que no
#: existen en un checkout limpio — nombres comunes contaban como "uso" sin
#: que nadie hubiera conectado nada. El CI tenía razón. Arreglado en
#: scripts/huerfanos.py (EXCLUIDOS) y recalibrado a lo que de verdad hay.
# 94 desde el 2026-08-16: archivado providers/selector.py en _attic (mock
# muerto de una arquitectura anterior: importaba ProviderDef y get_provider,
# que ya no existen). 95 desde el 2026-08-13: bajó de 107 al cablear la sonda —`LlmDeSonda`,
# `candidatos_para_sondear`, `medias_por_familia`, `refrescar_si_toca`— que
# llevaba semanas construida y sin llamar. El trinquete lo detectó y exigió
# consolidarlo, que es la mitad del mecanismo que se olvida siempre: si el
# techo no baja cuando baja el conteo, el margen ganado se puede volver a
# gastar sin que nadie se entere.
#
# 89 desde el 2026-08-30, y ESTA subida necesita justificarse porque el
# trinquete existe justamente para que no se suba a la ligera.
#
# El techo solo puede bajar en el curso normal del proyecto. Lo que pasó aquí
# no es el curso normal: el port de VeniceMAGI incorpora DOS paquetes nuevos
# enteros —`vmagi/venice` (el núcleo cloud-first) y `vmagi/repl` (el REPL de
# consola que el manifiesto promete)— que llegan con su propia superficie
# pública. No es andamiaje que alguien dejó a medias: es código que ya
# funcionaba en otro repositorio y que aquí entra completo.
#
# Lo que SÍ se hizo antes de subirlo, porque es la mitad que se olvida:
#   · se borró `proveedor_guest`, que nadie llamaba (el trinquete lo cazó);
#   · se conectó `studio/arte.py` desde `crear_arte` en el registro de
#     herramientas, en vez de dejarlo como capacidad inalcanzable;
#   · se conectó `vmagi/repl` desde `main.py --consola`.
#
# A partir de aquí vuelve a la regla de siempre: solo baja, y en el mismo
# commit que la bajada real.
#
# 88 desde el 2026-08-31, y esto SÍ es la regla de siempre. La suite cazó 90
# —dos por encima del techo— y la respuesta no fue subirlo:
#   · `cache_consulta` y `cache_guarda` eran «compatibilidad con la v1» que no
#     llamaba nadie. La v1 no sobrevive a este repositorio, así que la
#     compatibilidad era con un pasado que no existe. Borradas.
#   · `instala_alias` pasa a `_instala_alias`: la llama `registra()` en su
#     propio módulo y no es API de nadie más.
# El techo baja con el conteo. Si no bajara, el margen ganado se podría volver
# a gastar sin que nadie se entere — que es la mitad del mecanismo que siempre
# se olvida.
#
# 87 el 2026-09-02, y el caso es instructivo. Entró un módulo nuevo entero
# —`studio/estilo.py`, el medidor de estilo— y el conteo BAJÓ uno.
#
# La primera versión sí subía: traía sus propias `ffmpeg_disponible` y
# `ffprobe_disponible`, que son exactamente las preguntas que `video.py` ya
# respondía con `ffmpeg_available` y `ffprobe_available`. Tres huérfanos
# nuevos y, peor que el conteo, dos funciones distintas para la misma
# pregunta: el día que una mire el PATH y la otra intente ejecutar, dirán
# cosas distintas sobre la misma máquina.
#
# Al reusar las de `video.py` desaparecen las dos copias Y se conecta
# `ffprobe_available`, que llevaba tiempo definida sin que nadie la llamara.
# El trinquete no cazó un descuido de estilo: cazó una duplicación.
#
# 84 el mismo día, y esta vez por lo que este mecanismo persigue desde que
# existe. `studio/bucle.py` es el cable que le faltaba a tres módulos que
# llevaban aquí señalados desde su creación: `loop.py` —cuyo propio docstring
# confesaba que su función de medida «es un mock»—, `spec.py` y `rights.py`.
# Motor de convergencia completo, contrato medible completo, control de
# derechos completo, y ningún llamador. Conectarlos al medidor de estilo
# retira `AutoCorrectionLoop`, `SpecError`, `RightsGate` y `RightsBlockedError`
# de la lista, y de paso el bucle del plan pasa a medir ficheros de verdad.
TECHO = 84

#: techos por paquete (2026-08-16, tras archivar 6 paquetes sin importadores:
#: device, fabrication, vision, reasoning, os_portable, capabilities -> _attic). El total puede
#: cumplir y aun así acumularse todo en un sitio: el desglose dice DÓNDE
#: crece el andamiaje sin conectar, que es lo accionable. Misma regla que el
#: techo global: solo pueden bajar, y en el mismo commit que la baja real.
#:
#: 2026-08-30: `vmagi/venice` y `vmagi/repl` entran con techo propio en vez de
#: diluirse en el total. Es lo que hace accionable el desglose: si mañana el
#: andamiaje crece, se sabrá en cuál de los dos, y no habrá que buscarlo.
#: `vmagi/core` sube de 18 a 20 por el backend `guest_web` y los alias del
#: manifiesto en `core/tools`.
#: 2026-08-31: `core` baja de 20 a 17 y `venice` sube de 5 a 6 — el desglose
#: enseñando exactamente para lo que existe: el total bajó, pero no bajó en
#: todas partes. `venice` creció con `seedance_admitido`, que es la regla de
#: versiones que sustituyó a dos comparaciones de cadenas.
#: 2026-09-02: `vmagi/modules` baja de 63 a 59 en dos pasos. Primero a 62 con
#: la entrada del medidor de estilo —un módulo nuevo que hace bajar el
#: desglose, porque no basta con que lo añadido esté conectado: tiene que no
#: duplicar lo que ya había—. Después a 59 al cablear `loop.py`, `spec.py` y
#: `rights.py`, que llevaban señalados aquí desde el primer día.
TECHOS_POR_PAQUETE = {"vmagi/modules": 59, "vmagi/core": 17,
                      "vmagi/venice": 6, "vmagi/repl": 2}


def _cuenta() -> int:
    r = subprocess.run([sys.executable, str(SCRIPT), "--conteo"],
                       capture_output=True, text=True, timeout=600, cwd=str(RAIZ))
    if r.returncode != 0:
        pytest.fail(f"scripts/huerfanos.py falló:\n{r.stderr[-800:]}")
    return int(r.stdout.strip())


def _por_paquete() -> dict[str, int]:
    r = subprocess.run([sys.executable, str(SCRIPT), "--json"],
                       capture_output=True, text=True, timeout=600, cwd=str(RAIZ))
    if r.returncode != 0:
        pytest.fail(f"scripts/huerfanos.py falló:\n{r.stderr[-800:]}")
    import json
    conteo: dict[str, int] = {}
    for item in json.loads(r.stdout):
        partes = item["sitios"][0].replace("\\", "/").split("/")
        paquete = "/".join(partes[:2]) if partes[0] == "vmagi" and len(partes) > 2 else partes[0]
        conteo[paquete] = conteo.get(paquete, 0) + 1
    return conteo


def test_el_entorno_virtual_del_README_no_falsea_el_conteo():
    """El directorio que las instrucciones de instalación mandan crear.

    EL FALLO, MEDIDO. Mismo commit y mismo código en dos máquinas: 87
    huérfanos sin entorno virtual, **78** con un `.venv` recién creado dentro
    del repo. Nueve piezas pasaban por «conectadas» porque su nombre aparecía
    en algún fichero de site-packages, y el índice de uso busca en TODO el
    repositorio a propósito.

    Lo grave no es el número, son dos cosas:

      1. El README dice literalmente `python -m venv .venv`. Seguir las
         instrucciones del proyecto rompía el trinquete del proyecto.
      2. Lo rompía HACIA ABAJO, que es la dirección que no avisa. Un conteo
         que baja parece una mejora, y `test_si_baja_el_conteo_se_baja_el_techo`
         habría invitado a consolidar como logro un margen que no existía.

    `EXCLUIDOS` ya tenía `venv` y `.venv-lock` — el comentario de 2026-08-16
    cuenta que este mismo problema ya se pagó una vez con site-packages. Lo
    que faltaba era justo el nombre que el README manda usar.
    """
    import scripts.huerfanos as h  # noqa: PLC0415

    assert ".venv" in h.EXCLUIDOS, (
        "`.venv` no está excluido, y es el nombre que el README manda crear. "
        "Con él dentro, el conteo baja solo y el trinquete deja de medir.")
    # Y el que ya estaba, que no se pierda por el camino.
    assert {".venv-lock", "venv", "site-packages"} <= h.EXCLUIDOS


def test_el_codigo_publico_sin_llamar_no_crece():
    n = _cuenta()
    assert n <= TECHO, (
        f"Hay {n} definiciones públicas sin sitio de llamada; el techo es "
        f"{TECHO}. Algo nuevo se ha quedado sin conectar.\n\n"
        f"Ejecuta `python scripts/huerfanos.py` para ver cuáles. Cada una es "
        f"una de tres cosas: una capacidad a la que le falta el cable "
        f"(CONÉCTALA), andamiaje que sobra (BÓRRALO o llévalo a vmagi/_attic/), "
        f"o un punto de entrada legítimo (añádelo a ENTRADAS en el script, con "
        f"el motivo escrito).")


def test_el_andamiaje_no_se_acumula_en_un_solo_paquete():
    conteo = _por_paquete()
    for paquete, techo in TECHOS_POR_PAQUETE.items():
        n = conteo.get(paquete, 0)
        assert n <= techo, (
            f"`{paquete}` tiene {n} definiciones públicas sin llamar y su "
            f"techo es {techo}. El total puede cumplir y aun así acumularse "
            f"todo en un sitio: este desglose existe para que el crecimiento "
            f"tenga dirección visible.\n\n"
            f"Reparto actual: {conteo}. Si consolidaste huérfanos de este "
            f"paquete, baja su techo en este mismo commit.")


def test_si_baja_el_conteo_se_baja_el_techo():
    """
    Un trinquete que no se aprieta no es un trinquete.

    Si alguien conecta o retira piezas y el techo se queda arriba, el margen
    recuperado se puede volver a gastar sin que nada avise. Este test obliga a
    consolidar la mejora en el mismo commit que la produce.
    """
    n = _cuenta()
    assert n >= TECHO - 5, (
        f"El conteo ha bajado a {n} y TECHO sigue en {TECHO}. Enhorabuena: "
        f"baja TECHO a {n} en tests/test_sin_huerfanos.py para consolidarlo. "
        f"Si no, el margen que acabas de ganar se puede volver a gastar sin "
        f"que nadie se entere.")


def test_el_script_explica_que_hacer_y_no_solo_que_pasa():
    """
    Un informe que dice «108 huérfanos» y nada más no ayuda a nadie.

    El proyecto lleva media docena de sesiones quitando cifras sin contexto;
    esta no va a ser una más. El informe tiene que decir qué son las tres
    salidas posibles.
    """
    # CODIFICACIÓN FIJADA EN LOS DOS EXTREMOS, y no por manía.
    #
    # Con `text=True` a secas, Python descodifica la salida del hijo con
    # `locale.getpreferredencoding()` — cp1252 en este equipo, UTF-8 en el CI
    # de Ubuntu. El hijo, por su parte, escribe en lo que le diga el entorno.
    # Si los dos no coinciden, «CONÉCTALA» llega convertida en ruido y este
    # test falla por una razón que no tiene NADA que ver con lo que comprueba.
    #
    # Pasó tal cual el 2026-08-20: bastó lanzar la suite con
    # PYTHONIOENCODING=utf-8 en el shell para que fallara, mientras el código
    # que audita estaba perfectamente. Un test que depende del entorno de quien
    # lo lanza no es una red de seguridad: es una fuente de ruido que enseña a
    # ignorar los fallos rojos.
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(SCRIPT)],
                       capture_output=True, timeout=600, cwd=str(RAIZ),
                       env=entorno, encoding="utf-8", errors="replace")
    assert r.returncode == 0
    for pista in ("CONÉCTALA", "BÓRRALO", "_attic", "ENTRADAS"):
        assert pista in r.stdout, f"el informe debería explicar «{pista}»"
