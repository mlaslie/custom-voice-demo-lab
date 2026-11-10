import json

import pytest
from fastapi.testclient import TestClient

from demolab import config


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMOLAB_FAKE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "SETTINGS", tmp_path / "settings.json")
    return tmp_path


def test_old_settings_migrate_to_a_profile(home):
    (home / "settings.json").write_text(json.dumps({"voice_id": "voice_abc", "voice_style": "calm", "tts_model": "m"}))
    (home / "secrets.json").write_text(json.dumps({"gemini_api_key": "AIzaTESTTESTTESTTEST1234"}))
    s = config.load()
    assert [k.hint for k in s.keys] == ["1234"]
    (v,) = s.profiles
    assert (v.voice, v.style, v.kind, s.active_profile) == ("voice_abc", "calm", "custom", v.id)
    secrets = json.loads((home / "secrets.json").read_text())
    assert secrets[config.key_secret(s.keys[0].id)] == "AIzaTESTTESTTESTTEST1234"
    assert "gemini_api_key" in secrets          # not the real home: the old entry is left alone
    assert '"voice_id"' not in (home / "settings.json").read_text()
    assert config.resolve().voice == "voice_abc" and config.load().profiles == s.profiles   # idempotent


def test_setup_flow(home):
    from demolab.api import app
    c = TestClient(app, base_url="http://127.0.0.1")
    st = c.get("/api/settings").json()
    assert st["setup_needed"] and st["keys"] == [] and st["active"] is None
    assert c.post("/api/voice/preview", json={"text": "hi"}).status_code == 428

    assert c.post("/api/keys", json={"name": "x", "key": "short"}).status_code == 400
    r = c.post("/api/keys", json={"name": "Work", "key": "AIzaFAKEFAKEFAKEFAKEwxyz"}).json()
    kid = r["key"]["id"]
    assert r["key"]["hint"] == "wxyz" and r["custom_voices"] == 1
    assert "AIzaFAKE" not in json.dumps(c.get("/api/settings").json())    # never echoed back

    v = c.get(f"/api/keys/{kid}/voices").json()
    assert [x["id"] for x in v["custom"]] == ["voice_test0001"]
    assert {x["id"] for x in v["standard"]} == {"kore", "puck"} and v["multilingual"] == 2
    assert [x["id"] for x in c.get(f"/api/keys/{kid}/voices", params={"locale": "en-us"}).json()["standard"]] == ["en-us-podcaster-1"]

    ok = c.post("/api/voice/preview", json={"text": "hello", "key_id": kid, "voice": "kore"})
    assert ok.status_code == 200 and ok.content[:4] == b"RIFF"

    st = c.post("/api/profiles", json={"name": "Narrator", "key_id": kid, "voice": "voice_test0001",
                                       "voice_name": "Test custom voice"}).json()
    assert not st["setup_needed"] and st["active"]["name"] == "Narrator"
    st = c.post("/api/profiles", json={"name": "Kore", "key_id": kid, "voice": "kore", "kind": "standard",
                                       "activate": False}).json()
    kore = next(p for p in st["profiles"] if p["name"] == "Kore")
    assert st["active"]["name"] == "Narrator"
    assert c.post(f"/api/profiles/{kore['id']}/activate").json()["active"]["voice"] == "kore"
    assert config.resolve().voice == "kore"
    assert config.resolve(st["active"]["id"]).voice == "voice_test0001"   # a project can pick another

    assert c.post("/api/keys", json={"key": "AIzaFAKEFAKEFAKEFAKE0000"},
                  headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.delete(f"/api/keys/{kid}").status_code == 400                # still used by profiles
    for p in c.get("/api/settings").json()["profiles"]:
        c.delete(f"/api/profiles/{p['id']}")
    st = c.delete(f"/api/keys/{kid}").json()
    assert st["setup_needed"] and st["keys"] == []
    assert config.key_secret(kid) not in json.loads((home / "secrets.json").read_text())
