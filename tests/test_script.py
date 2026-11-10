import pytest
from fastapi.testclient import TestClient

from demolab import config, script, store
from demolab.models import Project

GOOD = [
    {"type": "card", "kicker": "DEMO", "title": "Policy editor", "narration": "Here is the policy editor."},
    {"type": "slide", "slide": 1, "narration": "The second slide shows the architecture."},
    {"type": "step", "title": "Open it", "narration": "We open the editor.",
     "actions": [{"op": "goto", "value": "/policies"}, {"op": "click", "selector": "role=button[name=\"New\"]"}],
     "after_narration": "The editor is open."},
    {"type": "card", "title": "Recap", "bullets": ["One", "Two"], "narration": "That is the editor."},
]


def project(**kw) -> Project:
    return Project(**{"name": "t", "slides": ["a.png", "b.png"], "base_url": "http://localhost:9", **kw})


def test_good_script_passes():
    segs, errors, warnings = script.validate(GOOD, project())
    assert errors == [] and warnings == [] and [s.type for s in segs] == ["card", "slide", "step", "card"]
    assert 5 < script.seconds(segs) < 30


def test_errors_and_warnings_name_the_segment():
    bad = [
        {"type": "slide", "slide": 7, "narration": "x"},
        {"type": "step", "narration": "Go to https://example.com", "actions": [{"op": "click"}]},
        {"type": "banner", "narration": "x"},
        {"type": "card", "narration": "**bold** text"},
    ]
    segs, errors, warnings = script.validate(bad, project(base_url=""))
    joined = "\n".join(errors)
    assert "segment 1 (slide): slide must be 0 to 1" in joined
    assert "web steps need the project's base_url" in joined and "a click action needs a selector" in joined
    assert "segment 3: type" in joined
    assert any("contains a URL" in w for w in warnings) and any("markdown" in w for w in warnings)
    assert any("opens with an intro card" in w for w in warnings)


def test_no_slides_says_how_to_attach():
    _, errors, _ = script.validate([{"type": "slide", "slide": 0, "narration": "x"}], Project(name="t"))
    assert "attach the deck with start_demo" in errors[0]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(store, "ROOT", tmp_path / "projects")
    from demolab.api import app
    return TestClient(app, base_url="http://127.0.0.1")


def test_write_script_through_the_api(client):
    p = client.post("/api/projects", json={"name": "Demo", "brief": "We reviewed the editor.",
                                           "base_url": "http://localhost:9"}).json()
    assert p["brief"] == "We reviewed the editor."
    r = client.put(f"/api/projects/{p['id']}/segments", json=[GOOD[1]])
    assert r.status_code == 400 and "has no slides" in r.json()["detail"]["errors"][0]
    assert client.get(f"/api/projects/{p['id']}").json()["segments"] == []      # nothing saved
    ok = client.put(f"/api/projects/{p['id']}/segments", json=[GOOD[0], GOOD[2], GOOD[3]]).json()
    assert ok["warnings"] == [] and len(ok["project"]["segments"]) == 3 and not ok["project"]["script_approved"]
