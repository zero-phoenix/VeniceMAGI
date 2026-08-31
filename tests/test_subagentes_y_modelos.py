"""Subagentes por familia y opciones de modelo ampliadas.

QUE PROTEGEN
============
Dos mecanismos nuevos que comparten una misma trampa: los dos parecen
mejorar el sistema aflojando la invariante que lo sostiene.

  · Los subagentes «podrian» repartirse entre familias distintas para
    tener mas diversidad. Contaminaria la tesis con el sesgo de quien
    tiene que refutarla.
  · El mando de modelos «podria» dejar poner dos nodos en la misma
    familia si el usuario lo pide. El sistema seguiria respondiendo,
    peor, sin dar un solo error.

Ninguna de las dos falla ruidosamente. Por eso hay tests.
"""
from __future__ import annotations

import asyncio

import pytest

from vmagi.modules.swarm.subagentes import (
    MAX_FRENTES,
    MIN_FRENTES_PARA_ABRIR,
    Abanico,
    Frente,
    reparte_encargo,
    resumen,
)
from vmagi.venice.modelos import (
    NODOS,
    FamiliaRepetida,
    catalogo_de_modelos,
    familia_de,
    fijar_familia,
    informe,
    reparto_efectivo,
)


class LLMFalso:
    """Registra la familia pedida y cuanto tarda cada frente."""

    def __init__(self, respuestas=None, retardo=0.0, falla=()):
        self.respuestas = respuestas or {}
        self.retardo = retardo
        self.falla = set(falla)
        self.familias: list[str] = []
        self.prompts: list[str] = []

    async def generate(self, sistema, usuario, *, family=None, hedge=None,
                       tag="", **kw):
        self.familias.append(family or "auto")
        self.prompts.append(usuario)
        if self.retardo:
            await asyncio.sleep(self.retardo)
        if usuario in self.falla:
            raise RuntimeError("proveedor caido")
        return self.respuestas.get(usuario, f"respuesta a: {usuario}"), "prov-x"


# ------------------------------------------------------ trocear el encargo

def test_un_encargo_de_una_pieza_no_abre_abanico():
    """Un frente es una llamada normal con pasos de mas, y gasta racion."""
    r = reparte_encargo("arregla el bug del login")
    assert not r
    assert "una sola pieza" in r.motivo


def test_las_partes_separables_se_cuentan():
    r = reparte_encargo(
        "genera el ejecutable portable; "
        "escribe los tests de la capa de red; "
        "documenta el formato del fichero de configuracion")
    assert r
    assert len(r.frentes) == 3


def test_las_comas_solas_no_trocean():
    """«un dragon rojo, de noche» son matices de UNA imagen, no dos encargos.

    Trocear por comas partia encargos de imagen en trozos sin sentido y
    lanzaba tres llamadas para reconstruir una sola.
    """
    r = reparte_encargo("un dragon rojo, de noche, sobre una montana nevada")
    assert not r


def test_el_troceo_es_determinista():
    """La compuerta de la fase exige repetir la misma ronda dos veces.

    Con un troceo no determinista -si lo decidiera un modelo- el reparto
    cambiaria entre corridas identicas y «tarda menos con la misma
    calidad» dejaria de poder medirse.
    """
    e = "haz A del sistema; luego haz B del sistema; y por ultimo haz C"
    assert reparte_encargo(e).frentes == reparte_encargo(e).frentes


def test_nunca_se_pierde_una_promesa_del_encargo():
    """Lo que pasa del maximo se pega al ultimo frente, no se tira."""
    partes = [f"tarea numero {i} que hay que hacer entera" for i in range(9)]
    r = reparte_encargo("; ".join(partes))
    assert len(r.frentes) == MAX_FRENTES
    ultimo = r.frentes[-1]
    assert "tarea numero 8" in ultimo, "la ultima promesa no puede perderse"


def test_el_troceo_no_llama_a_ningun_modelo():
    """Cuesta una llamada de la racion averiguar como gastar la racion."""
    llm = LLMFalso()
    reparte_encargo("una cosa; otra cosa; y una tercera cosa distinta")
    assert llm.familias == []


# ----------------------------------------------------------- el abanico

async def test_todos_los_frentes_salen_por_LA_MISMA_familia():
    """La diversidad esta ENTRE nodos; dentro de un nodo, coherencia.

    Si los subagentes de Melchior salieran por la familia de Balthasar, la
    tesis llegaria contaminada con el sesgo de quien tiene que refutarla, y
    la refutacion encontraria menos porque parte de lo mismo.
    """
    llm = LLMFalso()
    r = reparte_encargo("primera parte del encargo; segunda parte del encargo")
    frentes = await Abanico(llm, "venice", rol="MELCHIOR").abrir("sys", r)

    assert len(frentes) == 2
    assert set(llm.familias) == {"venice"}, llm.familias


async def test_los_frentes_van_en_paralelo_de_verdad():
    llm = LLMFalso(retardo=0.15)
    r = reparte_encargo("parte uno del trabajo; parte dos del trabajo; "
                        "parte tres del trabajo")
    assert len(r.frentes) == 3, r.frentes
    ab = Abanico(llm, "venice", rol="MELCHIOR")
    frentes = await ab.abrir("sys", r)

    res = resumen(frentes, ab.ultimo_ms)
    assert res["frentes"] == 3
    assert res["ms_abanico"] < res["ms_si_fuera_en_serie"], res
    assert res["ahorro_pct"] > 40, res


async def test_un_frente_caido_no_se_lleva_a_los_demas():
    """Los otros ya han gastado racion: perderlos seria pagar dos veces."""
    malo = "segunda parte que va a fallar"
    llm = LLMFalso(falla={malo})
    r = reparte_encargo(f"primera parte del encargo; {malo}; tercera parte va")
    frentes = await Abanico(llm, "venice").abrir("sys", r)

    assert len(frentes) == 3
    assert sum(1 for f in frentes if f.util) == 2
    caido = next(f for f in frentes if not f.util)
    assert "proveedor caido" in caido.error


async def test_una_respuesta_degradada_no_cuenta_como_util():
    """Un fallo que viene como texto sigue siendo un fallo (C11)."""
    llm = LLMFalso()

    async def degradada(sistema, usuario, **kw):
        return "[Inferencia no disponible: todo agotado]", "SYSTEM_ERROR"

    llm.generate = degradada
    r = reparte_encargo("una parte del encargo; otra parte del encargo")
    frentes = await Abanico(llm, "venice").abrir("sys", r)
    assert all(not f.util for f in frentes)


def test_lo_que_no_se_cubrio_se_dice():
    """Un texto fundido sin costuras esconde el frente que fallo."""
    frentes = [
        Frente(contrato="parte A", texto="hecho"),
        Frente(contrato="parte B", error="sin respuesta en 60s"),
    ]
    fundido = Abanico.funde(frentes)
    assert "parte A" in fundido
    assert "sin cubrir" in fundido and "parte B" in fundido


async def test_balthasar_no_abre_subagentes():
    """Su turno ya es redundante por diseno: abrir mas es pagarlo dos veces."""
    from vmagi.modules.swarm.agents import BalthasarAgent, MelchiorAgent
    assert BalthasarAgent.subagentes is False
    assert MelchiorAgent.subagentes is True


async def test_un_abanico_roto_no_tumba_el_turno(monkeypatch):
    """Una optimizacion que puede dejarte sin respuesta no es una optimizacion."""
    from vmagi.core.blackboard import Blackboard
    from vmagi.core.bus import MagiBus
    from vmagi.modules.swarm.agents import MelchiorAgent

    a = MelchiorAgent(Blackboard(), MagiBus())
    monkeypatch.setattr("vmagi.modules.swarm.subagentes.reparte_encargo",
                        lambda *x, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    encargo = "primera parte del encargo; segunda parte del encargo"
    assert await a._abanico("sys", encargo) == encargo


# -------------------------------------------------- opciones de modelo

def test_el_inventario_enumera_guest_y_g4f():
    ms = catalogo_de_modelos()
    vias = {m.via for m in ms}
    assert vias == {"guest", "g4f"}
    guest = [m for m in ms if m.via == "guest"]
    assert {m.familia for m in guest} == {"venice", "notrack"}
    assert all(m.sin_cuenta for m in ms)


def test_venice_es_el_unico_guest_que_declara_imagen():
    ms = {m.familia: m for m in catalogo_de_modelos() if m.via == "guest"}
    assert "imagen" in ms["venice"].capacidades
    assert "imagen" not in ms["notrack"].capacidades


def test_se_puede_fijar_la_familia_de_un_nodo():
    assert fijar_familia("CASPER", "command")["CASPER"] == "command"
    assert familia_de("CASPER") == "command"
    fijar_familia("CASPER", None)
    assert familia_de("CASPER") == reparto_efectivo()["CASPER"]


def test_dos_nodos_no_pueden_compartir_familia():
    """No se hacen eco: se DICE por que, en vez de aceptarlo en silencio."""
    reparto = reparto_efectivo()
    with pytest.raises(FamiliaRepetida) as e:
        fijar_familia("CASPER", reparto["MELCHIOR"])
    assert "eco" in str(e.value)
    assert familia_de("CASPER") == reparto["CASPER"], "no pudo cambiar"


def test_una_familia_inventada_se_rechaza_diciendo_cuales_hay():
    with pytest.raises(ValueError) as e:
        fijar_familia("CASPER", "modelo-que-no-existe")
    assert "venice" in str(e.value) and "notrack" in str(e.value)


def test_naoko_y_ritsuko_no_se_tocan_desde_aqui():
    """Naoko rota a proposito; Ritsuko tiene prohibidas las que audita.

    Ofrecer un mando que rompe una garantia es peor que no ofrecerlo.
    """
    assert "NAOKO" not in NODOS and "RITSUKO" not in NODOS
    for prohibido in ("NAOKO", "RITSUKO"):
        with pytest.raises(ValueError) as e:
            fijar_familia(prohibido, "gemini")
        assert "Ritsuko" in str(e.value) or "Naoko" in str(e.value)


def test_el_informe_dice_de_donde_sale_cada_familia():
    fijar_familia("CASPER", "command")
    texto = informe()
    assert "fijado por ti" in texto
    assert "del catalogo" in texto
    fijar_familia("CASPER", None)


def test_los_agentes_leen_el_reparto_efectivo():
    """Si leyeran el catalogo a secas, el mando cambiaria la interfaz y no
    los agentes — el mismo fallo de v5.0.28 una capa mas arriba."""
    from vmagi.core.blackboard import Blackboard
    from vmagi.core.bus import MagiBus
    from vmagi.modules.swarm.agents import CasperAgent

    fijar_familia("CASPER", "command")
    try:
        assert CasperAgent(Blackboard(), MagiBus()).family == "command"
    finally:
        fijar_familia("CASPER", None)
