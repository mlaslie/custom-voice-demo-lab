import base64
import io
import json
import wave

import pytest
from fastapi.testclient import TestClient

from demolab import config, store


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMOLAB_FAKE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(store, "ROOT", tmp_path / "projects")
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


def test_voice_pairs_are_verified(home):
    from demolab.api import app
    c = TestClient(app, base_url="http://127.0.0.1")
    kid = c.post("/api/keys", json={"name": "K", "key": "AIzaFAKEFAKEFAKEFAKEwxyz"}).json()["key"]["id"]

    st = c.post("/api/profiles", json={"name": "Good", "key_id": kid, "voice": "kore", "kind": "standard"}).json()
    good = st["active"]
    assert good["verified_at"] > 0 and good["verify_error"] == ""            # tested on save

    st = c.post("/api/profiles", json={"name": "Wrong", "key_id": kid, "voice": "voice_from_another_project"}).json()
    bad = next(v for v in st["profiles"] if v["name"] == "Wrong")
    assert bad["verified_at"] == 0 and "has no voice 'voice_from_another_project'" in bad["verify_error"]

    st = c.patch(f"/api/profiles/{bad['id']}", json={"voice": "puck", "kind": "standard"}).json()
    assert next(v for v in st["profiles"] if v["id"] == bad["id"])["verified_at"] > 0   # retested on change
    st = c.patch(f"/api/profiles/{good['id']}", json={"style": "slower"}).json()
    assert next(v for v in st["profiles"] if v["id"] == good["id"])["verified_at"] > 0  # style keeps it

    config.delete_secret(config.key_secret(kid))                             # key vanished from the keychain
    r = c.post(f"/api/profiles/{good['id']}/verify").json()
    assert not r["ok"] and "missing from the keychain" in r["error"]


def test_pacing(home, monkeypatch):
    from demolab import store
    from demolab.api import app
    monkeypatch.setattr(store, "ROOT", home / "projects")
    c = TestClient(app, base_url="http://127.0.0.1")
    kid = c.post("/api/keys", json={"name": "K", "key": "AIzaFAKEFAKEFAKEFAKEwxyz"}).json()["key"]["id"]
    st = c.post("/api/profiles", json={"name": "V", "key_id": kid, "voice": "kore", "kind": "standard", "speed": 3}).json()
    vid = st["active"]["id"]
    assert st["active"]["speed"] == 1.4                                     # clamped on create
    assert c.patch(f"/api/profiles/{vid}", json={"speed": 0.1}).json()["active"]["speed"] == 0.7   # and on edit
    c.patch(f"/api/profiles/{vid}", json={"speed": 1.0})

    text = "one two three four five six seven eight nine ten eleven twelve thirteen"
    base = c.post("/api/voice/preview", json={"text": text, "profile_id": vid})
    fast = c.post("/api/voice/preview", json={"text": text, "profile_id": vid, "speed": 1.25})
    s1, s2 = float(base.headers["X-Seconds"]), float(fast.headers["X-Seconds"])
    assert abs(s2 - s1 / 1.25) < 0.1                                        # time-stretched to match
    assert int(fast.headers["X-Words-Per-Minute"]) > int(base.headers["X-Words-Per-Minute"])

    p = c.post("/api/projects", json={"name": "P"}).json()
    seg = [{"type": "card", "title": "T", "narration": " ".join(["word"] * 132)}]
    at1 = c.put(f"/api/projects/{p['id']}/segments", json=seg).json()["seconds"]
    c.patch(f"/api/projects/{p['id']}", json={"speed": 1.2})               # this demo only
    at12 = c.put(f"/api/projects/{p['id']}/segments", json=seg).json()["seconds"]
    assert abs(at12 - at1 / 1.2) < 0.5
    from demolab import pipeline
    assert pipeline.voice_for(store.get(p["id"])).speed == 1.2
    c.patch(f"/api/projects/{p['id']}", json={"speed": 0})                 # back to the voice's pace
    assert pipeline.voice_for(store.get(p["id"])).speed == 1.0


def _silent_wav_b64(seconds: float = 0.25) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * int(24000 * seconds))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_key_verify_custom_voice_and_projects_detail(home):
    from demolab.api import app

    c = TestClient(app, base_url="http://127.0.0.1")
    k = c.post("/api/keys", json={"name": "Primary", "key": "AIzaFAKEFAKEFAKEFAKE1234"})
    assert k.status_code == 200
    kid = k.json()["key"]["id"]

    v = c.post(f"/api/keys/{kid}/verify")
    assert v.status_code == 200
    v_body = v.json()
    assert v_body["ok"] is True
    assert isinstance(v_body["custom_voices"], int)
    assert isinstance(v_body["standard_voices"], int)

    wav_b64 = _silent_wav_b64()
    created = c.post("/api/custom-voices", json={
        "key_id": kid,
        "name": "HAL Studio Voice",
        "description": "Use for product walkthroughs",
        "source_audio_b64": wav_b64,
        "consent_audio_b64": wav_b64,
    })
    assert created.status_code == 200
    c_body = created.json()
    voice = c_body["voice"]
    assert voice["name"] == "HAL Studio Voice"
    assert voice["kind"] == "custom"
    vid = voice["id"]
    pid = c_body["settings"]["active"]["id"]

    listed = c.get(f"/api/keys/{kid}/voices").json()
    assert any(item["id"] == vid for item in listed["custom"])

    proj = c.post("/api/projects", json={"name": "Demo One"}).json()
    c.patch(f"/api/projects/{proj['id']}", json={"profile_id": pid})
    mp4 = store.pdir(proj["id"]) / "renders" / "render-01.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"fake-mp4-bytes")
    p_loaded = store.get(proj["id"])
    from demolab.models import Render
    p_loaded.renders.append(Render(
        file=str(mp4),
        seconds=4.2,
        segments=1,
        resolution="1080p",
        created_at=1700000000.0,
    ))
    store.save(p_loaded)

    projs = c.get("/api/projects").json()
    match = next(item for item in projs if item["id"] == proj["id"])
    assert match["profile_id"] == pid
    assert len(match["renders_detail"]) == 1
    assert match["renders_detail"][0]["index"] == 0
    assert match["renders_detail"][0]["file"] == str(mp4)
    assert match["renders_detail"][0]["resolution"] == "1080p"
    assert match["renders_detail"][0]["size_bytes"] == len(b"fake-mp4-bytes")

    deleted = c.delete(f"/api/profiles/{pid}?delete_remote=true")
    assert deleted.status_code == 200
    listed_after = c.get(f"/api/keys/{kid}/voices").json()
    assert all(item["id"] != vid for item in listed_after["custom"])


def test_local_audio_devices_and_live_capture(home):
    import time
    from demolab.api import app

    c = TestClient(app, base_url="http://127.0.0.1")
    devs = c.get("/api/audio/devices")
    assert devs.status_code == 200
    d_body = devs.json()
    assert len(d_body["devices"]) >= 1
    rec_id = d_body["recommended_id"]
    assert rec_id

    started = c.post("/api/audio/capture/start", json={"device_id": rec_id, "record": True})
    assert started.status_code == 200
    assert started.json()["active"] is True

    time.sleep(0.15)
    status = c.get("/api/audio/capture/status")
    assert status.status_code == 200
    st = status.json()
    assert st["active"] is True
    assert len(st["bands"]) == 48
    assert any(b > 0 for b in st["bands"])

    stopped = c.post("/api/audio/capture/stop")
    assert stopped.status_code == 200
    stop_body = stopped.json()
    assert stop_body["ok"] is True
    assert stop_body["seconds"] > 0
    assert base64.b64decode(stop_body["audio_b64"])[:4] == b"RIFF"
