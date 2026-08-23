"""Tests offline: todo contra un Venice falso, cero red.

Si un test necesitara red, sería una opinión sobre el estado de Venice hoy,
no una prueba del sistema.
"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest

from vmagi import config
from vmagi import app as _app   # noqa: E402  (smoke de sintaxis del REPL)
from vmagi.orchestrator import Orquestador
from vmagi.tools import Ejecutor, parsea_herramientas
from vmagi.venice import ChatResp, CupoDiarioAgotado, Venice, VeniceError


# ------------------------------------------------------------- fakes

class FakeVenice(Venice):
    """Venice de mentira: respuestas guionizadas por orden de llegada."""

    def __init__(self, guion: list[str]):
        super().__init__()
        self.guion = list(guion)
        self.llamadas: list[tuple[str, dict]] = []

    async def chat(self, sistema: str, usuario: str, **kw) -> ChatResp:
        # OJO al orden: ANTÍTESIS y SÍNTESIS contienen "TESIS" dentro.
        rol = ("NAOKO" if "supervisora" in sistema else
               "BALTHASAR" if "ANTÍTESIS" in sistema else
               "CASPER" if "SÍNTESIS" in sistema else "MELCHIOR")
        self.llamadas.append((f"chat:{rol}", {"usuario": usuario[:80]}))
        texto = self.guion.pop(0) if self.guion else "ok"
        return ChatResp(texto=texto, modelo="fake", ms=1.0)

    async def imagen(self, prompt: str, **kw) -> Path:
        self.llamadas.append(("imagen", {"prompt": prompt[:60]}))
        p = config.media_dir() / "fake.png"
        p.write_bytes(b"\x89PNG fake")
        return p

    async def video(self, prompt: str, **kw) -> Path:
        self.llamadas.append(("video", {"prompt": prompt[:60], **kw}))
        p = config.media_dir() / "fake.mp4"
        p.write_bytes(b"\x00\x00 fake mp4")
        return p

    async def modelos(self) -> list[str]:
        return ["uno", "dos"]

    async def modelo_texto(self) -> str:
        return "uno"

    def cerrar(self) -> None:
        pass


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "data"))
    return config.workspace()


# ------------------------------------------------------- protocolo tool

def test_parsea_bloques_tool():
    texto = ('antes\n```tool\n{"herramienta": "write_file", '
             '"args": {"ruta": "a.py", "contenido": "x=1"}}\n```\ndespués')
    calls = parsea_herramientas(texto)
    assert len(calls) == 1
    assert calls[0].herramienta == "write_file"
    assert calls[0].args["ruta"] == "a.py"


def test_parsea_ignora_json_roto():
    assert parsea_herramientas("```tool\n{no json}\n```") == []
    assert parsea_herramientas("texto sin nada") == []


@pytest.mark.asyncio
async def test_write_file_y_run_python_reales(ws):
    ej = Ejecutor(FakeVenice([]), ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "write_file", "args": '
        '{"ruta": "calc.py", "contenido": "print(6*7)"}}\n```')[0])
    assert r.ok and r.ruta == ws / "calc.py"
    r2 = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "run_python", "args": '
        '{"codigo": "print(open(\'calc.py\').read())"}}\n```')[0])
    assert r2.ok and "print(6*7)" in r2.salida


@pytest.mark.asyncio
async def test_run_python_captura_el_fallo(ws):
    ej = Ejecutor(FakeVenice([]), ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "run_python", "args": '
        '{"codigo": "1/0"}}\n```')[0])
    assert not r.ok and "ZeroDivisionError" in r.salida


@pytest.mark.asyncio
async def test_write_file_no_escapa_del_workspace(ws):
    ej = Ejecutor(FakeVenice([]), ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "write_file", "args": '
        '{"ruta": "../../peligro.txt", "contenido": "x"}}\n```')[0])
    assert not r.ok
    assert not (ws.parent.parent / "peligro.txt").exists()


@pytest.mark.asyncio
async def test_generate_image_con_refs_de_diseno(ws, tmp_path):
    diseno = ws / "diseno.png"
    diseno.write_bytes(b"\x89PNG diseno")
    v = FakeVenice([])
    ej = Ejecutor(v, ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "generate_image", "args": '
        '{"prompt": "copia este diseno", "refs": ["diseno.png"]}}\n```')[0])
    assert r.ok and r.ruta and r.ruta.exists()
    _, args = v.llamadas[0]
    assert args["prompt"].startswith("copia")


# ------------------------------------------------------------ la ronda

@pytest.mark.asyncio
async def test_ronda_completa_tesis_antitesis_sintesis(ws):
    bloque = json.dumps({"herramienta": "write_file",
                         "args": {"ruta": "hola.py",
                                  "contenido": 'print("hola")'}})
    v = FakeVenice([
        json.dumps({"tipo": "construccion", "estilo": "tecnico",
                    "nota": ""}),
        "TESIS: escribo el fichero ```tool\n" + bloque + "\n```",
        "ANTÍTESIS: lo ejecuté y funciona",
        "SÍNTESIS: listo, hola.py creado y verificado",
    ])
    orch = Orquestador(v, ws)
    r = await orch.ronda("crea hola.py que imprima hola")
    assert "hola.py" in r.tesis or r.artefactos
    assert str(ws / "hola.py") in r.artefactos
    assert (ws / "hola.py").exists()
    assert "SÍNTESIS" in r.sintesis
    roles_llamados = [k for k, _ in v.llamadas]
    assert "chat:NAOKO" in roles_llamados
    assert "chat:MELCHIOR" in roles_llamados
    assert "chat:BALTHASAR" in roles_llamados
    assert "chat:CASPER" in roles_llamados


@pytest.mark.asyncio
async def test_naoko_roto_no_tumba_la_ronda(ws):
    v = FakeVenice([
        "esto no es json",              # Naoko llega roto
        "tesis", "antitesis", "sintesis",
    ])
    orch = Orquestador(v, ws)
    r = await orch.ronda("haz algo")
    assert r.sintesis == "sintesis"    # la ronda siguió igualmente


@pytest.mark.asyncio
async def test_consulta_no_gasta_roles(ws):
    v = FakeVenice([
        json.dumps({"tipo": "consulta", "estilo": "sintetico", "nota": ""}),
        "respuesta directa",
    ])
    orch = Orquestador(v, ws)
    r = await orch.ronda("¿qué es un mutex?")
    assert r.sintesis == "respuesta directa"
    assert not any(k.startswith("chat:MELCHIOR") for k, _ in v.llamadas)


# ------------------------------------------------------------ cliente

def test_el_cupo_diario_se_explica_sin_drama():
    from vmagi import naoko
    msg = naoko.explica_error(CupoDiarioAgotado("agotado"))
    assert "mañana" in msg and "Venice" in msg


def test_naoko_explica_los_errores():
    from vmagi import naoko
    # El VeniceError llega con su mensaje ya explicado (lo escribe quien lo
    # lanza, con el motivo y qué hacer); Naoko lo pasa tal cual.
    e = VeniceError("revisa la ventana del Edge de la puerta")
    assert "Edge" in naoko.explica_error(e)
    assert "ValueError" in naoko.explica_error(ValueError("cualquier cosa"))
