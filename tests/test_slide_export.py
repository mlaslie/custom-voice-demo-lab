import subprocess

from demolab import sources


def _fake_run(returncode=1, stderr=""):
    def run(*a, **kw):
        return subprocess.CompletedProcess(a[0], returncode, "", stderr)
    return run


def _keynote_only(monkeypatch):
    monkeypatch.setattr(sources.shutil, "which", lambda _: None)
    monkeypatch.setattr(sources.sys, "platform", "darwin")
    monkeypatch.setattr(sources.os.path, "exists", lambda x: x == "/Applications/Keynote.app")


def test_keynote_failures_explain_themselves(tmp_path, monkeypatch):
    _keynote_only(monkeypatch)
    deck = tmp_path / "d.pptx"
    cases = {
        "54:86: execution error: Keynote got an error: AppleEvent timed out. (-1712)": "open dialog",
        "execution error: Not authorized to send Apple events to Keynote. (-1743)": "Automation",
        "execution error: Keynote got an error: Can't open file. (-1000)": "Keynote export failed: Keynote got an error: Can't open file. (-1000)",
    }
    for stderr, expect in cases.items():
        monkeypatch.setattr(sources.subprocess, "run", _fake_run(1, stderr))
        pdf, why = sources._pptx_to_pdf(deck)
        assert pdf is None and expect in why, why


def test_keynote_hang_is_reported(tmp_path, monkeypatch):
    _keynote_only(monkeypatch)

    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], kw["timeout"])
    monkeypatch.setattr(sources.subprocess, "run", hang)
    pdf, why = sources._pptx_to_pdf(tmp_path / "d.pptx")
    assert pdf is None and "didn't respond" in why


def test_no_converter(tmp_path, monkeypatch):
    monkeypatch.setattr(sources.shutil, "which", lambda _: None)
    monkeypatch.setattr(sources.sys, "platform", "linux")
    monkeypatch.setattr(sources.os.path, "exists", lambda x: False)
    assert sources._pptx_to_pdf(tmp_path / "d.pptx") == (None, sources.NO_CONVERTER)


def test_google_slides_links_ask_for_an_export():
    import pytest
    from demolab.models import Project
    with pytest.raises(ValueError, match="export the deck as a PDF or .pptx"):
        sources.add_deck(Project(name="t"), "https://docs.google.com/presentation/d/abc123/edit")
