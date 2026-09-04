"""
La búsqueda evolutiva, y el experimento que puede tumbarla.

LA AFIRMACIÓN QUE ESTOS TESTS PUEDEN REFUTAR
============================================
«Buscar supera a las cuatro pasadas de reglas escritas a mano.»

Se refuta si la búsqueda, con cientos de evaluaciones, NO baja de la distancia
a la que llegan las reglas. Si eso ocurre, `busqueda.py` sobra: el cómputo
gratis no está comprando nada y hay que borrarlo, no defenderlo.

EL MUNDO SIMULADO, Y POR QUÉ NO ES TRAMPA
=========================================
Los dos contendientes corren contra un `_mundo()` que traduce parámetros de
montaje a medidas. No es un mundo cualquiera: cada relación está copiada de lo
que hace FFmpeg de verdad.

  · `xfade` se come parte del plano, así que el fundido acorta la duración
    media medida.
  · `zoompan` ES movimiento de cámara: el zoom sube `camara_px` y baja
    `fraccion_camara_fija`. Es literalmente su propósito.
  · `eq=saturation` multiplica la saturación de partida.
  · `eq=contrast` PIVOTA EN EL GRIS MEDIO. Esta es la clave: en una imagen
    oscura (luma 96 sobre 255), subir el contraste la oscurece todavía más.
    Los dos ejes están acoplados en el mundo real, y unas reglas que mueven un
    mando por eje no pueden saberlo.

Correr los dos sobre el mismo mundo, con el mismo genoma y la misma biblia, es
lo que hace que la comparación signifique algo. Por eso las reglas salieron de
dentro de la herramienta a `reglas.py`: antes no se podían comparar con nada
porque hablaban otro idioma (un diccionario suelto dentro de un `async def`).

Y todo esto corre sin ffmpeg, sin red y sin modelo. Una búsqueda que solo se
puede probar generando mil vídeos no se prueba nunca.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from vmagi.modules.studio import bucle as B
from vmagi.modules.studio import busqueda as S
from vmagi.modules.studio.biblia import BibliaDeEstilo, Tolerancia, compara
from vmagi.modules.studio.estilo import MedidaEstilo
from vmagi.modules.studio.reglas import aplica_reglas, siembra_desde_biblia

#: La imagen de partida del mundo simulado: interior en penumbra, madera y
#: verde de jardín. Los números salen del orden de magnitud que da el medidor
#: sobre material de este cine, no de la nada.
SAT_BASE, LUMA_BASE, CONTRASTE_BASE = 0.42, 96.0, 34.0

#: Relación de aspecto que produce el montador. FIJA: la animática sale 16:9
#: porque las imágenes son 16:9, y ningún parámetro del genoma la mueve.
ASPECTO_MONTAJE = 1.778


def _mundo(g: S.Genoma) -> MedidaEstilo:
    """Parámetros de montaje -> medidas. La física del experimento."""
    dur = max(0.1, g.segundos_plano - 0.55 * g.crossfade)
    return MedidaEstilo(
        aspecto=ASPECTO_MONTAJE,
        duracion_media_plano=dur,
        camara_px=0.05 + 42.0 * g.zoom,
        fraccion_camara_fija=max(0.0, min(1.0, 1.0 - 6.0 * g.zoom)),
        saturacion=min(1.0, SAT_BASE * g.saturacion),
        # el pivote en el gris medio, que es lo que acopla luma y contraste
        luma=(LUMA_BASE - 128.0) * g.contraste + 128.0 + g.brillo * 255.0,
        contraste=CONTRASTE_BASE * g.contraste,
    )


def _biblia_de_una_pelicula() -> BibliaDeEstilo:
    """La biblia de una referencia REAL, no de la animática.

    Y ahí está el detalle que decide el experimento: la película es 1.85:1 y
    la animática es 16:9. Ese eje **no lo puede cumplir nadie** tocando los
    mandos del montaje, así que ni las reglas ni la búsqueda van a converger.
    La pregunta deja de ser «¿quién llega?» y pasa a ser «¿quién se acerca
    más con el resto?», que es la pregunta que de verdad se hace todas las
    noches sobre esta máquina.
    """
    objetivo = S.Genoma(segundos_plano=8.0, crossfade=0.0, zoom=0.0,
                        brillo=0.055, contraste=1.22, saturacion=0.84)
    m = _mundo(objetivo)
    m.aspecto = 1.85                       # la película, no la animática
    return BibliaDeEstilo.desde(m, nombre="pelicula", holgura=0.06)


async def _medidor_falso(ruta, *, procedencia="generado") -> MedidaEstilo:
    """Devuelve la medida que corresponde al genoma escrito en el nombre.

    El genoma viaja por el nombre del fichero porque es lo único que atraviesa
    la frontera generar->medir en el sistema real, y así el falso se comporta
    como el de verdad: mide un fichero, no recuerda quién lo pidió.
    """
    return _mundo(_GENOMAS[Path(ruta).stem])


_GENOMAS: dict[str, S.Genoma] = {}


def _apunta(g: S.Genoma) -> Path:
    _GENOMAS[g.firma] = g
    return Path(f"{g.firma}.mp4")


# =========================================================== la aptitud

def test_la_distancia_es_continua_y_la_cuenta_de_incumplidos_no():
    """El motivo entero de que exista `distancia()`.

    Dos candidatos que fallan el mismo eje puntúan IGUAL con la cuenta de
    incumplidos, aunque uno esté al borde de cumplirlo y el otro a diez
    márgenes. Una búsqueda sobre eso es una búsqueda sin cuesta que subir.
    """
    b = BibliaDeEstilo(tolerancias=[
        Tolerancia(eje="saturacion", objetivo=0.30, margen=0.03)])
    cerca = MedidaEstilo(saturacion=0.34)
    lejos = MedidaEstilo(saturacion=0.90)

    assert len(compara(cerca, b).incumplidos) == len(compara(lejos, b).incumplidos)
    assert S.distancia(cerca, b) < S.distancia(lejos, b), (
        "la aptitud no distingue «casi» de «ni de lejos»: el paisaje es una "
        "escalera y la búsqueda va a ciegas")


def test_dentro_del_margen_no_se_persigue_el_centro():
    """Un eje ya cumplido aporta CERO, no «un poquito».

    Si aportara, la búsqueda gastaría evaluaciones afinando algo que la biblia
    declaró indiferente — y, peor, empeoraría otro eje para ganar centésimas
    en este.
    """
    b = BibliaDeEstilo(tolerancias=[
        Tolerancia(eje="saturacion", objetivo=0.30, margen=0.05)])
    assert S.distancia(MedidaEstilo(saturacion=0.30), b) == 0.0
    assert S.distancia(MedidaEstilo(saturacion=0.34), b) == 0.0


def test_un_eje_sin_medir_penaliza_mucho_en_vez_de_salir_gratis():
    """LA TRAMPA QUE UN OPTIMIZADOR ENCONTRARÍA EN UNA TARDE.

    Si un eje que no se pudo medir costara cero, la búsqueda aprendería a
    producir vídeos IMPOSIBLES DE MEDIR —en negro, sin audio, de dos
    fotogramas— porque lo que no se mide no penaliza. Es la quinta regla del
    proyecto, aplicada a algo que la explotaría mil veces más rápido que una
    persona.
    """
    b = BibliaDeEstilo(tolerancias=[
        Tolerancia(eje="saturacion", objetivo=0.30, margen=0.03)])
    ciego = S.distancia(MedidaEstilo(), b)                 # nada medido
    horrible = S.distancia(MedidaEstilo(saturacion=1.0), b)
    assert ciego > horrible, (
        "salir del paso sin medir puntúa mejor que medir fatal: la búsqueda "
        "va a aprender a cegar al medidor")


def test_una_biblia_vacia_no_da_distancia_cero():
    """Sin contrato no hay perfección: devolver 0.0 haría ganar a cualquiera."""
    assert S.distancia(MedidaEstilo(saturacion=0.9),
                       BibliaDeEstilo()) == S.PENA_SIN_MEDIR


def test_un_eje_imposible_no_aplasta_a_los_demas():
    """LA SEGUNDA RAZÓN DE LA CURVA DE SATURACIÓN.

    Una biblia puede traer un eje que el generador no puede tocar. Sin tope,
    ese eje aporta un número enorme que inunda la media y deja de haber
    diferencia entre un candidato bueno y uno malo EN TODO LO DEMÁS: la
    búsqueda se queda ciega justo en lo que sí puede arreglar.
    """
    b = BibliaDeEstilo(tolerancias=[
        Tolerancia(eje="aspecto", objetivo=2.35, margen=0.01),      # imposible
        Tolerancia(eje="saturacion", objetivo=0.30, margen=0.03)])
    bueno = S.distancia(MedidaEstilo(aspecto=1.778, saturacion=0.31), b)
    malo = S.distancia(MedidaEstilo(aspecto=1.778, saturacion=0.95), b)
    assert malo - bueno > 0.5, (
        f"con el eje imposible dentro, un candidato bueno ({bueno:.4f}) y uno "
        f"malo ({malo:.4f}) casi no se distinguen")


def test_la_distancia_de_un_veredicto_ya_hecho_no_vuelve_a_medir():
    """`distancia_de_veredicto` existe aparte porque el bucle de búsqueda ya
    tiene el veredicto en la mano: volver a llamar a `compara()` para sacar el
    mismo número es medir dos veces lo mismo, y abre la puerta a que las dos
    medidas se separen el día que una de ellas cambie."""
    b = BibliaDeEstilo(tolerancias=[
        Tolerancia(eje="saturacion", objetivo=0.30, margen=0.03)])
    m = MedidaEstilo(saturacion=0.55)
    assert S.distancia_de_veredicto(compara(m, b)) == S.distancia(m, b)


# ========================================================== los operadores

def test_el_cruce_no_promedia_los_padres():
    """Promediar dos buenas soluciones da una mala con frecuencia incómoda.

    El punto medio entre «plano largo con cámara fija» y «plano corto con
    paneo» no es ninguna de las dos cosas. Es el mismo error que fusionar dos
    LoRAs promediando sus pesos: el resultado no apunta a donde apuntaba
    ninguno de los dos.
    """
    dados = S._Dados(1)
    a = S.Genoma(segundos_plano=2.0, saturacion=0.5)
    b = S.Genoma(segundos_plano=20.0, saturacion=2.0)
    for _ in range(30):
        h = S.cruza(a, b, dados)
        assert h.segundos_plano in (2.0, 20.0)
        assert h.saturacion in (0.5, 2.0)


def test_la_mutacion_no_se_sale_de_los_limites():
    dados = S._Dados(2)
    g = S.Genoma(saturacion=2.2, zoom=0.30, contraste=1.9)
    for _ in range(200):
        g = S.muta(g, dados, escala=3.0)
        for nombre, (bajo, alto) in S.LIMITES.items():
            assert bajo <= getattr(g, nombre) <= alto, nombre


def test_la_misma_semilla_da_la_misma_busqueda():
    """Sin esto, dos corridas no se pueden comparar — y comparar es todo lo
    que hace este módulo."""
    a = [g.firma for g in S.siembra(S.Genoma(), _biblia_de_una_pelicula(),
                                    S._Dados(5), 8)]
    b = [g.firma for g in S.siembra(S.Genoma(), _biblia_de_una_pelicula(),
                                    S._Dados(5), 8)]
    assert a == b


def test_la_siembra_lee_la_biblia_antes_de_la_primera_pasada():
    b = _biblia_de_una_pelicula()
    poblacion = S.siembra(S.Genoma(), b, S._Dados(0), 6)
    guiado = poblacion[1]
    assert guiado.segundos_plano == pytest.approx(8.0, abs=0.01), (
        "la biblia dice cuánto dura un plano y la siembra no lo leyó")
    assert not guiado.ken_burns, (
        "la biblia pide la cámara clavada y se siembra con Ken Burns puesto, "
        "que es literalmente un movimiento de cámara")


# ============================================ EL EXPERIMENTO QUE PUEDE REFUTAR

async def _corre_las_reglas(b: BibliaDeEstilo, monkeypatch) -> float:
    """Las cuatro pasadas de reglas a mano, sobre el mismo mundo."""
    monkeypatch.setattr(B, "medir", _medidor_falso)
    estado = {"g": siembra_desde_biblia(b)[0]}

    async def generar(version: int, correcciones: list):
        estado["g"] = aplica_reglas(estado["g"], correcciones)
        return _apunta(estado["g"])

    await B.rueda_hasta_cumplir("animática de prueba", b, generar)
    # Se puntúa el ÚLTIMO genoma que las reglas produjeron, que es lo que se
    # entregaría. Quedarse con el mejor de las cuatro pasadas sería regalarle
    # a las reglas una élite que no tienen: el bucle no la guarda.
    return S.distancia(_mundo(estado["g"]), b)


@pytest.mark.parametrize("semilla", [11, 42, 7])
async def test_EL_EXPERIMENTO_la_busqueda_supera_a_las_reglas(semilla,
                                                              monkeypatch):
    """LA REFUTACIÓN.

    Si esto falla, `busqueda.py` no vale lo que ocupa y hay que borrarlo. No
    hay una lectura amable: el argumento entero del módulo es que el cómputo
    gratis compra algo que las reglas no dan.

    TRES SEMILLAS Y NO UNA, y no es celo: un método estocástico juzgado por una
    sola corrida no está juzgado. Una semilla afortunada demuestra que el
    resultado ES POSIBLE, que es una afirmación mucho más débil que la que hace
    el módulo. Si dos de estas tres pasan y una no, lo honesto es leer que el
    método es inestable, no elegir la que salió bien.
    """
    b = _biblia_de_una_pelicula()
    con_reglas = await _corre_las_reglas(b, monkeypatch)

    async def generar(g: S.Genoma, idx: int):
        return _apunta(g)

    f = await S.busca(b, generar, poblacion=10, generaciones=30,
                      semilla=semilla, medidor=_medidor_falso, auditado=True)

    assert f.mejor is not None, f.render()
    assert f.evaluaciones >= 100, (
        f"solo {f.evaluaciones} evaluaciones: el experimento no llegó a "
        f"ejecutarse de verdad")
    assert f.mejor.distancia < con_reglas, (
        f"REFUTADO. {f.evaluaciones} evaluaciones dejaron la distancia en "
        f"{f.mejor.distancia:.4f} y las cuatro pasadas de reglas a mano la "
        f"dejan en {con_reglas:.4f}. El cómputo gratis no está comprando "
        f"nada: borra `busqueda.py` en vez de defenderlo.")

    # Y NO por poco: las reglas se atascan con la saturación y la luz, que es
    # donde su paso fijo salta por encima de la ventana que cumple. La búsqueda
    # cierra el paso cuando deja de mejorar y entra. Medido: reglas 0,7847 —
    # búsqueda 0,0000 con menos de doscientas evaluaciones, en las tres
    # semillas.
    assert f.mejor.incumplidos == 0, (
        f"la búsqueda mejora a las reglas pero NO converge ({f.mejor.incumplidos} "
        f"ejes incumplidos). El óptimo de este mundo es alcanzable, así que no "
        f"llegar significa que el paso de mutación no se está adaptando: "
        f"{f.render()}")


async def test_sin_paso_adaptativo_la_busqueda_se_queda_a_medias(monkeypatch):
    """POR QUÉ HACE FALTA LA REGLA DE UN QUINTO, con el contraejemplo delante.

    Este test congela la escala de mutación y comprueba que ENTONCES la
    búsqueda ya no converge. Sirve para que nadie borre la adaptación pensando
    que es adorno: la versión de paso fijo ganaba a las reglas —0,6023 contra
    0,7847— y por eso parecía suficiente. Ganar no era el objetivo; llegar sí.
    """
    b = _biblia_de_una_pelicula()
    monkeypatch.setattr(S, "APERTURA", 1.0)
    monkeypatch.setattr(S, "CIERRE", 1.0)

    async def generar(g: S.Genoma, idx: int):
        return _apunta(g)

    f = await S.busca(b, generar, poblacion=10, generaciones=30, semilla=11,
                      medidor=_medidor_falso, auditado=True)
    assert f.mejor.distancia > 0.0, (
        "con el paso congelado también converge: entonces la adaptación no "
        "está haciendo nada y este test miente sobre por qué existe")


async def test_la_elite_impide_que_una_generacion_con_mala_suerte_lo_estropee(
        monkeypatch):
    """La avería clásica de estos métodos, y la más difícil de ver desde fuera:
    terminar peor de lo que ya se estaba."""
    b = _biblia_de_una_pelicula()

    async def generar(g: S.Genoma, idx: int):
        return _apunta(g)

    f = await S.busca(b, generar, poblacion=8, generaciones=15, semilla=3,
                      medidor=_medidor_falso, auditado=True)
    mejores = [h["mejor"] for h in f.historial if h["mejor"] is not None]
    assert mejores == sorted(mejores, reverse=True), (
        "el mejor histórico empeoró entre generaciones: la élite no está "
        "pasando intacta")


async def test_un_generador_roto_se_diagnostica_como_generador_roto():
    """No como dirección artística equivocada. Es el mismo fallo que el bucle
    aprendió midiendo: «meseta» cuando lo que pasaba es que no se generó nada.
    """
    async def generar(g: S.Genoma, idx: int):
        return None

    f = await S.busca(_biblia_de_una_pelicula(), generar, poblacion=4,
                      generaciones=5, medidor=_medidor_falso, auditado=True)
    assert isinstance(f, S.Frontera), (
        "sale SIEMPRE el mismo tipo, también cuando no se evaluó nada. Dos "
        "contratos de salida según el resultado obligan al llamador a "
        "adivinar cuál le ha tocado")
    assert f.mejor is None
    assert f.fallos_de_generacion >= 4
    assert "GENERADOR" in f.render(), (
        f"el informe no manda a mirar el generador, y quien lo lea se irá a "
        f"tocar la dirección artística:\n{f.render()}")
    assert "no la dirección artística" in f.render()


async def test_sin_auditar_el_medidor_la_busqueda_lo_dice():
    """Una búsqueda optimiza lo que se le mide. Si el medidor tiene un punto
    ciego, esto lo encuentra — y quien lea el informe tiene que saberlo antes
    de creerse el número."""
    async def generar(g: S.Genoma, idx: int):
        return _apunta(g)

    f = await S.busca(_biblia_de_una_pelicula(), generar, poblacion=4,
                      generaciones=2, medidor=_medidor_falso)
    assert "adversario" in f.render().lower()


# ==================================================== alcanzable desde el enjambre

def test_la_busqueda_esta_en_el_registro_del_enjambre():
    from vmagi.core.tools.registry import ToolRegistry
    from vmagi.modules.studio.tools import register_studio_tools

    reg = register_studio_tools(ToolRegistry())
    t = reg.get("buscar_parametros")
    assert t is not None, "el enjambre no puede lanzar una búsqueda"
    assert "write" in (t.access or set()), "fabrica ficheros: pasa por journal"
