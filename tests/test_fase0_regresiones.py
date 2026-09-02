"""
Los fallos que la auditoría del 2026-09-02 encontró, cada uno con su test.

Los cuatro estaban en código que el README anuncia y que nadie había puesto a
prueba en la rama exacta donde fallaban. Es la regla 2 del proyecto vista
desde el otro lado: no basta con que la pieza tenga tests, tienen que cubrir
el camino por el que el sistema pasa de verdad.
"""
from __future__ import annotations

import pytest

from vmagi.venice.cliente import (
    COLA_PROMPT,
    LIMITE_PROMPT,
    recorta_prompt,
)
from vmagi.venice.medios import VideoSeedanceError

# ================================================ 1 · el error que no se lanza

def test_el_error_de_seedance_acepta_el_codigo_http():
    """`VideoSeedanceError(msg, estado=429)` tiene que construirse.

    EL FALLO. `medios.py` lanzaba exactamente eso sobre una clase que heredaba
    de `RuntimeError` sin `__init__` propio, y `RuntimeError` no acepta
    argumentos con nombre. Resultado verificado antes del arreglo:

        TypeError: VideoSeedanceError() takes no keyword arguments

    O sea que la única rama que informa de un error HTTP de Seedance lanzaba
    un error de tipos en su lugar, y el usuario recibía un mensaje que no
    mencionaba ni el código ni el motivo. Cero tests la tocaban.
    """
    e = VideoSeedanceError("Seedance error 429: sin cuota", estado=429)
    assert e.estado == 429
    assert "429" in str(e)


def test_sin_codigo_el_estado_es_none_y_no_cero():
    """`None` es «esto no vino de una respuesta HTTP». Cero sería un código.

    Las otras tres construcciones de esta excepción —falta de key, modelo no
    permitido, respuesta sin URL— no son fallos HTTP. Colapsarlas a 0 haría
    que `es_cuota` y cualquier futura decisión por código tuvieran que
    distinguir un 0 real de un 0 inventado.
    """
    e = VideoSeedanceError("Para vídeo con Seedance 2.5+ necesitas key.")
    assert e.estado is None
    assert e.es_cuota is False


@pytest.mark.parametrize("codigo,espera", [
    (429, True), (402, True), (401, False), (500, False), (200, False)])
def test_distingue_cuota_agotada_de_los_demas_fallos(codigo, espera):
    """Sin el código, un 429 y un 401 eran el mismo texto opaco.

    Y hay que reaccionar distinto: ante cuota agotada se espera o se cambia de
    proveedor; ante un 401 se revisa la key; ante un 5xx se reintenta.
    """
    assert VideoSeedanceError("x", estado=codigo).es_cuota is espera


def test_sigue_siendo_capturable_como_runtimeerror():
    """El arreglo no puede romper a quien ya la captura por su base."""
    with pytest.raises(RuntimeError):
        raise VideoSeedanceError("x", estado=500)


# ============================================ 2 · el prompt que se decapitaba

def test_un_prompt_que_cabe_no_se_toca():
    texto = "hola" * 100
    salida, recortado = recorta_prompt(texto)
    assert salida == texto
    assert recortado == 0


def test_el_final_del_prompt_sobrevive_al_recorte():
    """LO QUE ESTE TEST DEFIENDE, Y POR QUÉ ES EL FINAL Y NO EL PRINCIPIO.

    La línea era `[:7000]`: un corte por el final, en silencio. Ya figura en
    `docs/AUTOMODELO.json` como afirmación REFUTADA.

    Y lo que viaja al final de un prompt en este sistema no es relleno: es la
    evidencia con la que Balthasar refuta, la lista de promesas incumplidas
    del reintento dirigido del taller, y las restricciones de dirección
    artística de la biblia de estilo. El nodo contestaba sobre medio encargo
    creyendo que lo tenía entero.
    """
    cabeza = "A" * 6000
    centro = "B" * 20000
    cola = "RESTRICCION CRITICA: la camara no se mueve nunca."
    salida, recortado = recorta_prompt(cabeza + centro + cola)

    assert recortado > 0
    assert salida.endswith(cola), "el final, que es lo que más pesa, se perdió"
    assert salida.startswith("AAAA")
    assert "B" * 20000 not in salida


def test_el_recorte_nunca_pasa_del_limite():
    """Incluso contando el propio aviso de que se ha recortado.

    Trampa real: si el marcador no se descuenta del presupuesto, el resultado
    se pasa del límite justo por el texto que avisa de que no se ha pasado.
    """
    for n in (7001, 9000, 50000, 200000):
        salida, _ = recorta_prompt("x" * n)
        assert len(salida) <= LIMITE_PROMPT, (
            f"con {n} de entrada salieron {len(salida)}, y el tope es "
            f"{LIMITE_PROMPT}")


def test_el_recorte_se_declara_dentro_del_propio_prompt():
    """«Lo que no se cubrió, se dice» — la misma regla que los subagentes.

    Un texto fundido sin costuras esconde justo el trozo que falta. El modelo
    tiene que leer que le falta contexto para poder decirlo en su respuesta.
    """
    salida, recortado = recorta_prompt("z" * 30000)
    assert "RECORTADO" in salida
    assert str(recortado) in salida


def test_el_numero_de_caracteres_perdidos_cuadra():
    entrada = "q" * 40000
    salida, recortado = recorta_prompt(entrada)
    # Lo que queda del original = cabeza + cola. El marcador no es original.
    marca_ini = salida.index("\n\n[... RECORTADO")
    marca_fin = salida.index("...]\n\n") + len("...]\n\n")
    original_conservado = marca_ini + (len(salida) - marca_fin)
    assert original_conservado + recortado == len(entrada)


def test_limite_absurdo_no_revienta():
    """Un límite tan pequeño que no cabe ni el aviso todavía tiene que dar
    algo utilizable y declarar cuánto se perdió."""
    salida, recortado = recorta_prompt("abcdefghij" * 10, limite=12, cola=4)
    assert len(salida) <= 12
    assert recortado == 100 - len(salida)


def test_la_cola_nunca_se_come_el_limite_entero():
    """Si `cola >= limite`, la cabeza desaparecería y el prompt sería solo el
    final. Se topa a la mitad del presupuesto."""
    salida, _ = recorta_prompt("m" * 20000, limite=1000, cola=9999)
    assert len(salida) <= 1000
    assert salida.startswith("mmmm")


def test_el_valor_por_defecto_de_la_cola_cabe_en_el_limite():
    assert 0 < COLA_PROMPT < LIMITE_PROMPT // 2 + 1


# ================================ 3 · el recorte llega a quien lee la respuesta

def test_chatresp_declara_cuanto_se_recorto():
    """Que el número exista en la respuesta, no solo en un log.

    Un aviso que solo va al log no lo ve quien decide si creerse la respuesta.
    `recortado != 0` significa que el modelo contestó sobre un encargo
    incompleto, y eso pertenece al resultado.
    """
    from vmagi.venice.cliente import ChatResp
    limpia = ChatResp(texto="ok", modelo="venice-guest", ms=1.0)
    assert limpia.recortado == 0, "por defecto tiene que ser cero, no None"
    coja = ChatResp(texto="ok", modelo="venice-guest", ms=1.0, recortado=812)
    assert coja.recortado == 812
