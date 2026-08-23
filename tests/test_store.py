from __future__ import annotations

from vmagi.store import Historial


def test_historial_guarda_y_lista_renders(tmp_path):
    db = tmp_path / "h.db"
    h = Historial(db)
    h.anota_render(
        kind="image",
        prompt="retrato",
        ruta=str(tmp_path / "img.png"),
        metadata=str(tmp_path / "img.png.json"),
    )
    items = h.ultimos_renders(5)
    h.close()
    assert len(items) == 1
    assert items[0]["kind"] == "image"
    assert items[0]["prompt"] == "retrato"
