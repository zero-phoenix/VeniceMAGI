"""El taller de arte: dos autores separados y un critico que no perdona.

Lo que estos tests protegen es justo lo que un refactor bienintencionado
rompe primero: la separacion de los autores (parece redundante), la
familia del critico (parece un detalle), y la regla de que la maquina
manda sobre el modelo (parece desconfianza).
"""
from __future__ import annotations

import asyncio

import pytest

from vmagi.modules.studio.arte import (
    AUTORES,
    FAMILIA_CRITICO,
    Encargo,
    Medida,
    TallerDeArte,
)


class LLMFalso:
    """Registra QUE familia se pidio y con que prompt de sistema."""

    def __init__(self, respuestas: dict[str, str] | None = None):
        self.respuestas = respuestas or {}
        self.llamadas: list[tuple[str, str, str]] = []

    async def generate(self, sistema, usuario, *, family=None,
                       temperature=0.4, tag="", **kw):
        self.llamadas.append((family or "auto", tag, usuario))
        return self.respuestas.get(family or "auto", ""), f"prov-{family}"

    def familias_pedidas(self) -> list[str]:
        return [f for f, _t, _u in self.llamadas]


async def _pintor_falso(prompt, *, aspect_ratio="1:1", seed=None):
    return None            # sin Pillow ni archivo: la medida lo dira


def _taller(llm, pintor=_pintor_falso, **kw):
    return TallerDeArte(llm, pintor, **kw)


# ------------------------------------------------------------- contrato

def test_el_encargo_se_trocea_en_promesas_separables():
    """«Un dragon rojo, de noche, sobre una montana» son tres promesas.

    Contarlas al empezar es lo que permite decir al final cuales
    quedaron sin cubrir. Un encargo tratado como un tema no se puede
    incumplir a medias: se puede incumplir entero y parecer bien.
    """
    e = Encargo.desde_peticion("un dragon rojo, de noche, sobre una montana",
                               aspect_ratio="16:9")
    textos = [c.texto for c in e.criterios]
    assert any("16:9" in t for t in textos)
    assert sum(1 for c in e.criterios if not c.medible) >= 3
    assert sum(1 for c in e.criterios if c.medible) >= 3


def test_los_criterios_medibles_no_los_decide_un_modelo():
    e = Encargo.desde_peticion("algo", aspect_ratio="9:16")
    medibles = [c for c in e.criterios if c.medible]
    assert {c.clave for c in medibles} == {"existe", "no_vacia", "proporcion"}


# -------------------------------------------------------------- autores

async def test_los_dos_autores_reciben_el_encargo_y_no_se_ven():
    llm = LLMFalso({
        "venice": "LECTURA: dragon\nPROMPT: a red dragon at night",
        "notrack": "LECTURA: otra cosa\nPROMPT: crimson wyrm, moonlight",
    })
    t = _taller(llm)
    props = await t.propuestas(Encargo.desde_peticion("un dragon"))

    assert sorted(p.autor for p in props) == sorted(AUTORES)
    assert all(p.util for p in props)
    # Ninguno ha visto el prompt del otro: en las dos llamadas, el texto
    # de usuario es el mismo encargo y no contiene la salida del contrario.
    for _fam, _tag, usuario in llm.llamadas:
        assert "crimson wyrm" not in usuario
        assert "a red dragon at night" not in usuario


async def test_un_autor_caido_no_tumba_el_taller():
    llm = LLMFalso({"venice": "LECTURA: x\nPROMPT: a red dragon"})
    t = _taller(llm)
    props = await t.propuestas(Encargo.desde_peticion("un dragon"))
    utiles = [p for p in props if p.util]
    assert len(utiles) == 1 and utiles[0].autor == "venice"


async def test_las_dos_lecturas_se_funden_en_vez_de_descartar_una():
    """La discrepancia entre dos lecturas independientes es informacion.

    Elegir una y tirar la otra desperdicia justo lo que se acaba de pagar
    con dos llamadas.
    """
    llm = LLMFalso({
        "venice": "LECTURA: a\nPROMPT: red dragon",
        "notrack": "LECTURA: b\nPROMPT: night sky",
    })
    t = _taller(llm)
    e = Encargo.desde_peticion("un dragon")
    props = await t.propuestas(e)
    fundido = t._funde([p for p in props if p.util], e)
    assert "red dragon" in fundido and "night sky" in fundido


# -------------------------------------------------------------- critico

def test_el_critico_nunca_corre_en_la_familia_de_un_autor():
    """Un critico que comparte modelo con el autor no critica, confirma."""
    t = _taller(LLMFalso())
    assert set(t.familias_critico).isdisjoint(set(AUTORES))
    for f in FAMILIA_CRITICO:
        assert f not in AUTORES, f"{f} esta en AUTORES y no puede juzgar"


def test_sin_familia_propia_el_taller_se_niega_a_construirse():
    with pytest.raises(ValueError) as e:
        _taller(LLMFalso(), autores=("gemini", "venice"),
                familias_critico=("gemini",))
    assert "confirma" in str(e.value)


async def test_lo_que_mide_la_maquina_manda_sobre_lo_que_dice_el_critico():
    """El sesgo de complacencia existe; aqui hay un numero que lo desmiente.

    El critico aprueba las tres promesas medibles. La maquina midio que
    el archivo no existe. Gana la maquina.
    """
    llm = LLMFalso({"gemini": "CUMPLE 1: ok\nCUMPLE 2: ok\nCUMPLE 3: ok\n"
                              "VEREDICTO: ENTREGABLE"})
    t = _taller(llm)
    e = Encargo.desde_peticion("algo", aspect_ratio="1:1")
    v = await t.juzga(e, "prompt", Medida(ruta=None))     # no existe

    assert v.cumple is False
    assert any("existe" in x for x in v.incumplidos)
    assert v.familia == "gemini"


async def test_lo_no_medible_no_se_aprueba_por_omision():
    """Sin Pillow no se puede saber si la imagen esta en blanco.

    La quinta regla del proyecto nacio justo de esto: sin Pillow, el
    observador devolvia «correcto» sobre una captura que nunca abrio.
    """
    llm = LLMFalso({"gemini": "CUMPLE 2: se ve bien"})
    t = _taller(llm)
    e = Encargo.desde_peticion("algo")
    m = Medida(ruta=None, existe=True, abre=False,
               no_verificado=["Pillow no esta instalado"])
    v = await t.juzga(e, "p", m)
    assert any("blanco" in x for x in v.no_verificables)
    assert not any("blanco" in x for x in v.cumplidos)


def test_la_correccion_es_una_orden_concreta_no_un_hazlo_mejor():
    llm = LLMFalso({"gemini": "INCUMPLE 3: la proporcion salio 1:1"})
    t = _taller(llm)
    e = Encargo.desde_peticion("algo", aspect_ratio="16:9")
    v = t._lee_veredicto("INCUMPLE 3: mal", e, "gemini")
    correccion = v.correccion()
    assert "proporcion" in correccion
    assert "16:9" in correccion


# ----------------------------------------------------- medida de verdad

def test_la_medida_de_un_archivo_que_no_esta_no_finge():
    m = TallerDeArte.medir(None, "1:1")
    assert m.existe is False and m.abre is False
    assert m.resumen() == "el archivo no existe"


def test_proporcion_correcta_e_incorrecta(tmp_path):
    pil = pytest.importorskip("PIL", reason="sin Pillow no hay nada que medir")
    from PIL import Image

    ruta = tmp_path / "a.png"
    Image.new("RGB", (1600, 900), "white").save(ruta)

    e = Encargo.desde_peticion("x", aspect_ratio="16:9")
    m = TallerDeArte.medir(ruta, "16:9")
    assert m.abre and m.ancho == 1600
    ok = TallerDeArte.comprueba_medibles(e, m)
    assert ok[[c.texto for c in e.criterios if c.clave == "proporcion"][0]] is True

    e2 = Encargo.desde_peticion("x", aspect_ratio="9:16")
    m2 = TallerDeArte.medir(ruta, "9:16")
    ok2 = TallerDeArte.comprueba_medibles(e2, m2)
    assert ok2[[c.texto for c in e2.criterios if c.clave == "proporcion"][0]] is False


def test_una_imagen_de_color_plano_se_detecta(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    plana = tmp_path / "plana.png"
    Image.new("RGB", (512, 512), "white").save(plana)
    m = TallerDeArte.medir(plana, "1:1")
    assert m.entropia < 1.0, "un color plano tiene entropia ~0"


# ---------------------------------------------------------------- ciclo

async def test_sin_ningun_prompt_util_no_se_pinta_nada():
    llm = LLMFalso()                       # ningun autor devuelve PROMPT
    pintadas = []

    async def pintor(prompt, **kw):
        pintadas.append(prompt)
        return None

    obra = await _taller(llm, pintor).crear("un dragon")
    assert obra.estado == "fallo"
    assert pintadas == [], "no se gasta racion pintando sin encargo legible"


async def test_el_reintento_lleva_la_correccion_dentro(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    ruta = tmp_path / "b.png"
    Image.new("RGB", (100, 100), "white").save(ruta)
    usados: list[str] = []

    async def pintor(prompt, **kw):
        usados.append(prompt)
        return ruta

    llm = LLMFalso({
        "venice": "LECTURA: a\nPROMPT: red dragon",
        "notrack": "LECTURA: b\nPROMPT: night",
        "gemini": "INCUMPLE 3: la proporcion no es 16:9",
    })
    obra = await _taller(llm, pintor, max_pasadas=2).crear(
        "un dragon", aspect_ratio="16:9")

    assert obra.estado == "no_converge"
    assert len(usados) == 2
    assert "proporcion" in usados[1], (
        "la segunda pasada tiene que decir QUE arreglar, no 'hazlo mejor'")


async def test_la_metadata_guarda_lo_que_produjo_la_obra(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    ruta = tmp_path / "c.png"
    Image.new("RGB", (64, 64)).putdata([(i % 255, 0, 0) for i in range(64 * 64)])
    Image.new("RGB", (64, 64), "white").save(ruta)

    llm = LLMFalso({
        "venice": "LECTURA: a\nPROMPT: p1",
        "notrack": "LECTURA: b\nPROMPT: p2",
        "gemini": "INCUMPLE 2: plana",
    })
    obra = await _taller(llm, lambda p, **k: _devuelve(ruta),
                         max_pasadas=1).crear("algo")
    md = obra.metadata()
    assert [a["autor"] for a in md["autores"]] == list(AUTORES)
    assert md["veredicto"]["familia_critico"] == "gemini"
    assert md["contrato"] and md["pasadas"] == 1


async def _devuelve(x):
    return x
