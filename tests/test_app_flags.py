from __future__ import annotations

from vmagi.app import _parse_flags, _parse_int, _parse_on_off


def test_parse_flags_imagen():
    opts, prompt = _parse_flags(
        ["--ar", "16:9", "--seed", "42", "--quality", "ultra", "retrato", "realista"],
        {"--ar": "aspect_ratio", "--seed": "seed", "--quality": "quality"},
    )
    assert opts["aspect_ratio"] == "16:9"
    assert opts["seed"] == "42"
    assert opts["quality"] == "ultra"
    assert prompt == "retrato realista"


def test_parse_flags_deja_texto_sin_flag():
    opts, prompt = _parse_flags(
        ["hola", "--desconocido", "x"],
        {"--ar": "aspect_ratio"},
    )
    assert opts == {}
    assert prompt == "hola --desconocido x"


def test_parse_int_acepta_negativos():
    assert _parse_int("-42") == -42
    assert _parse_int("abc") is None


def test_parse_on_off():
    assert _parse_on_off("on") is True
    assert _parse_on_off("sí") is True
    assert _parse_on_off("off") is False
    assert _parse_on_off("quizas") is None
