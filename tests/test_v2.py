"""Tests de VeniceMAGI v2: IDE, kernel, aprobaciones, medios, ración."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from vmagi import config
from vmagi.kernel import Kernel
from vmagi.orchestrator import Orquestador
from vmagi.store import Historial
from vmagi.tools import Ejecutor, _cmd_ffmpeg, parsea_herramientas
from vmagi.venice import Venice, _CACHE


class FakeVenice(Venice):
    def __init__(self):
        super().__init__()
        self.imagenes = 0

    async def imagen(self, prompt: str, **kw) -> Path:
        self.imagenes += 1
        p = config.media_dir() / f"p{self.imagenes}.png"
        p.write_bytes(b"\x89PNG" + b"x" * 64)
        return p

    async def chat(self, sistema: str, usuario: str, **kw):
        from vmagi.venice import ChatResp
        return ChatResp(texto=f"resp:{usuario[:30]}", modelo="fake", ms=1.0)

    async def modelos(self):
        return ["fake"]

    def cerrar(self):
        pass


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("VENICE_MAGI_DIR", str(tmp_path / "d"))
    _CACHE.clear()
    return config.workspace()


# ------------------------------------------------------------ herramientas

@pytest.mark.asyncio
async def test_patch_quirurgico_exige_una_coincidencia(ws):
    ej = Ejecutor(FakeVenice(), ws)
    f = ws / "c.py"
    f.write_text("a = 1\nb = 2\na = 1\n", encoding="utf-8")
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "patch_file", "args": '
        '{"ruta": "c.py", "buscar": "a = 1", "reemplazar": "a = 99"}}\n```'
    )[0])
    assert not r.ok and "2 veces" in r.salida      # ambiguo: no se toca
    r2 = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "patch_file", "args": '
        '{"ruta": "c.py", "buscar": "b = 2", "reemplazar": "b = 99"}}\n```'
    )[0])
    assert r2.ok
    assert "b = 99" in f.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_delete_va_a_la_papelera_y_queda_journal(ws):
    ej = Ejecutor(FakeVenice(), ws)
    f = ws / "x.txt"
    f.write_text("borrame", encoding="utf-8")
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "delete_file", "args": '
        '{"ruta": "x.txt"}}\n```')[0])
    assert r.ok and not f.exists()
    assert "x.txt" in r.salida                    # en la papelera
    linea = json.loads(config.journal_path()
                       .read_text(encoding="utf-8").splitlines()[-1])
    assert linea["accion"] == "delete"


@pytest.mark.asyncio
async def test_read_y_list(ws):
    ej = Ejecutor(FakeVenice(), ws)
    (ws / "sub").mkdir()
    (ws / "a.txt").write_text("hola", encoding="utf-8")
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "read_file", "args": '
        '{"ruta": "a.txt"}}\n```')[0])
    assert r.ok and "hola" in r.salida
    r2 = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "list_dir", "args": {}}\n```')[0])
    assert r2.ok and "a.txt" in r2.salida


@pytest.mark.asyncio
async def test_hardware_info_habla_de_tu_maquina(ws):
    ej = Ejecutor(FakeVenice(), ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "hardware_info", "args": {}}\n```')[0])
    assert r.ok
    assert "cpu" in r.salida and "gpu" in r.salida and "disco" in r.salida


# ------------------------------------------------------------------ shell

@pytest.mark.asyncio
async def test_shell_sin_aprobacion_no_ejecuta(ws):
    """Nadie ejecuta nada en TU máquina sin tu clic."""
    ej = Ejecutor(FakeVenice(), ws, kernel=None)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "shell", "args": '
        '{"cmd": "echo no"}}\n```')[0])
    assert not r.ok


@pytest.mark.asyncio
async def test_shell_con_aprobacion_fluida(ws):
    v = FakeVenice()
    hist = Historial(config.data_dir() / "h.db")
    k = Kernel(v, hist)
    loop = asyncio.get_event_loop()

    async def aprueba_solo():
        await asyncio.sleep(0.05)
        while not k.aprobaciones:
            await asyncio.sleep(0.01)
        aid = next(iter(k.aprobaciones))
        assert k.resuelve_aprobacion(aid, True, loop)

    aprueba = asyncio.create_task(aprueba_solo())
    ej = Ejecutor(v, ws, kernel=k)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "shell", "args": '
        '{"cmd": "echo aprobado"}}\n```')[0])
    await aprueba
    assert r.ok and "aprobado" in r.salida


# ----------------------------------------------------------- video planos

@pytest.mark.asyncio
async def test_video_planos_sin_ffmpeg_lo_dice(ws, monkeypatch):
    import vmagi.tools as T
    monkeypatch.setattr(T.shutil, "which", lambda n: None)
    ej = T.Ejecutor(FakeVenice(), ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "video_planos", "args": '
        '{"planos": ["mar", "cielo"]}}\n```')[0])
    assert not r.ok and "ffmpeg" in r.salida


@pytest.mark.asyncio
async def test_video_planos_compone_en_tu_pc(ws, monkeypatch):
    import vmagi.tools as T

    def ffmpeg_fake(cmd, **kw):
        out = Path(cmd[cmd.index(str(cmd[-1]))])
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        class P: returncode = 0; stdout = ""; stderr = ""
        return P()

    monkeypatch.setattr(T.shutil, "which", lambda n: "ffmpeg")
    monkeypatch.setattr(T.subprocess, "run", ffmpeg_fake)
    v = FakeVenice()
    ej = T.Ejecutor(v, ws)
    r = await ej.ejecuta(parsea_herramientas(
        '```tool\n{"herramienta": "video_planos", "args": '
        '{"planos": ["mar al alba", "cielo rojo"], "duracion_s": 2.0}}'
        "\n```")[0])
    assert r.ok and r.ruta and r.ruta.suffix == ".mp4"
    assert v.imagenes == 2                         # 2 planos = 2 imágenes


def test_cmd_ffmpeg_encadena_xfade():
    from pathlib import Path as P
    cmd = _cmd_ffmpeg([P("a.png"), P("b.png"), P("c.png")],
                      P("out.mp4"), 3.0, 0.6)
    s = " ".join(cmd)
    assert cmd.count("-i") == 3
    assert s.count("xfade") == 2                   # 2 fundidos para 3 planos
    assert "out.mp4" in s


# ------------------------------------------------------------------ kernel

@pytest.mark.asyncio
async def test_kernel_cola_y_eventos(ws):
    v = FakeVenice()
    hist = Historial(config.data_dir() / "h.db")
    k = Kernel(v, hist)

    async def ronda_sintetica(texto):
        k.emite("ronda_fin", sintesis="listo", tesis="", antitesis="",
                nota="", artefactos=[])

    k.ronda = ronda_sintetica                # sin Venice real en el test
    trabajador = asyncio.create_task(k.procesa_cola())
    k.cola.put_nowait("haz algo")
    await asyncio.sleep(0.1)
    tipos = [e["tipo"] for e in k.eventos]
    assert "ronda_empieza" in tipos and "ronda_fin" in tipos
    assert k.eventos_desde(0)                 # la GUI puede pollar
    trabajador.cancel()


# ------------------------------------------------------------------ cache

def test_la_cache_no_gasta_racion(ws):
    from vmagi.venice import cache_consulta, cache_guarda
    clave = ("rol", "misma pregunta", 0.4)
    assert cache_consulta(clave) is None       # primera vez: se paga
    cache_guarda(clave, "respuesta")
    assert cache_consulta(clave) == "respuesta"   # segunda: sale gratis
    # y acotada: no crece sin límite
    for i in range(80):
        cache_guarda((f"r{i}", f"p{i}", 0.4), f"v{i}")
    assert len(_CACHE) <= 64


# ---------------------------------------------------------- puerta aparcada

def test_puerta_aparcada_por_defecto_y_visible_a_placer(ws, monkeypatch):
    monkeypatch.delenv("VENICE_PUERTA_VISIBLE", raising=False)
    from vmagi import sesion
    args = sesion.Puerta._kwargs_lanzamiento()["args"]
    assert any("window-position" in a for a in args), \
        "la puerta debe venir aparcada fuera de pantalla por defecto"
    config.fijar_puerta_visible(True)
    args2 = sesion.Puerta._kwargs_lanzamiento()["args"]
    assert not any("window-position" in a for a in args2)
