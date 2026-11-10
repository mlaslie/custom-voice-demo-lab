import os

from PIL import Image

os.environ.setdefault("DEMOLAB_FAKE_GEMINI", "1")


def test_session_source(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMOLAB_HOME", str(tmp_path / "home"))
    import importlib

    from demolab import config, scriptgen, sources, store
    importlib.reload(config), importlib.reload(store)

    ws = tmp_path / "ws"
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "spec.md").write_text("# Policy editor\nCreate and test policies.")
    (ws / ".env").write_text("GEMINI_API_KEY=do-not-read")
    (ws / "app.bin").write_bytes(b"\0\1")
    Image.new("RGB", (800, 600), "blue").save(ws / "shot.png")

    p = store.create("Session test")
    src = sources.add_session(p, "Goal:\nShow the policy editor.", ["docs/spec.md", ".env", "app.bin", "shot.png", "docs"],
                              workspace=str(ws))
    assert src.kind == "session" and src.text.startswith("Goal:")
    assert "Create and test policies." in src.text
    assert "do-not-read" not in src.text and ".env (looks like a secret)" in src.text
    assert "app.bin (unsupported type)" in src.text and "2 files skipped" in src.label
    assert src.files == ["docs/spec.md", "shot.png", "docs"]
    assert len(src.images) == 1 and (store.pdir(p.id) / "session" / src.images[0]).exists()

    p.sources = [sources.add_text(p, "Notes", "older notes"), src]
    store.save(p)
    digest = scriptgen._sources_digest(p)
    assert digest.index("[SESSION]") < digest.index("[text]")
    assert len(scriptgen._session_images(p)) == 1
