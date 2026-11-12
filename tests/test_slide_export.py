import json
import subprocess

import pypdfium2 as pdfium
import pytest

from demolab import config, sources, store
from demolab.models import Project


def _fake_run(returncode=1, stderr=""):
    def run(*a, **kw):
        return subprocess.CompletedProcess(a[0], returncode, "", stderr)
    return run


def _keynote_only(monkeypatch):
    monkeypatch.setattr(sources.shutil, "which", lambda _: None)
    monkeypatch.setattr(sources.sys, "platform", "darwin")
    monkeypatch.setattr(sources.os.path, "exists", lambda x: x == "/Applications/Keynote.app")


def _make_one_page_pdf(path):
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(960, 540)
    page.close()
    with open(path, "wb") as f:
        pdf.save(f)
    pdf.close()


def test_keynote_failures_explain_themselves(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMOLAB_PPTX_BACKEND", "external")
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
    monkeypatch.setenv("DEMOLAB_PPTX_BACKEND", "external")
    _keynote_only(monkeypatch)

    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], kw["timeout"])
    monkeypatch.setattr(sources.subprocess, "run", hang)
    pdf, why = sources._pptx_to_pdf(tmp_path / "d.pptx")
    assert pdf is None and "didn't respond" in why


def test_no_converter(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMOLAB_PPTX_BACKEND", "external")
    monkeypatch.setattr(sources.shutil, "which", lambda _: None)
    monkeypatch.setattr(sources.sys, "platform", "linux")
    monkeypatch.setattr(sources.os.path, "exists", lambda x: False)
    assert sources._pptx_to_pdf(tmp_path / "d.pptx") == (None, sources.NO_CONVERTER)


def test_builtin_pptx_works_without_libreoffice_or_keynote(tmp_path, monkeypatch):
    from PIL import Image
    from pptx import Presentation
    from pptx.util import Inches

    monkeypatch.delenv("DEMOLAB_PPTX_BACKEND", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(store, "ROOT", tmp_path / "projects")
    monkeypatch.setattr(sources.shutil, "which", lambda _: None)
    monkeypatch.setattr(sources.sys, "platform", "linux")
    monkeypatch.setattr(sources.os.path, "exists", lambda _: False)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    s1 = prs.slides.add_slide(blank)
    tb1 = s1.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    tb1.text_frame.text = "Slide One Title"
    s1.notes_slide.notes_text_frame.text = "Speaker note for slide one."

    s2 = prs.slides.add_slide(blank)
    tb2 = s2.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
    tb2.text_frame.text = "Slide Two Details"

    pptx_path = tmp_path / "sample.pptx"
    prs.save(str(pptx_path))

    p = store.create("Builtin PPTX Test")
    src = sources.add_deck(p, str(pptx_path))
    assert src.kind == "pptx"
    assert src.slide_count == 2
    assert len(p.slides) == 2
    assert "Slide One Title" in src.text
    assert "Speaker note for slide one." in src.text

    for slide_name in p.slides:
        img_path = store.sub(p.id, "slides") / slide_name
        assert img_path.is_file()
        with Image.open(img_path) as im:
            assert im.size == (1920, 1080)


def test_google_slides_ast_and_sidecar_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(store, "ROOT", tmp_path / "projects")
    p = store.create("Slides Test")

    pdf_path = tmp_path / "deck.pdf"
    _make_one_page_pdf(pdf_path)
    ast = {
        "title": "Gemini for Healthcare",
        "slides": [
            {
                "pageElements": [
                    {"shape": {"text": {"textElements": [{"textRun": {"content": "Clinical Search & FHIR\n"}}]}}}
                ],
                "slideProperties": {
                    "notesPage": {
                        "pageElements": [
                            {"shape": {"placeholder": {"type": "SLIDE_IMAGE"}}},
                            {"shape": {"text": {"textElements": [{"textRun": {"content": "Emphasize HIPAA compliance."}}]}}},
                        ]
                    }
                },
            }
        ],
    }
    (tmp_path / "deck.gslides.json").write_text(json.dumps(ast))

    src = sources.add_deck(p, str(pdf_path))
    assert src.kind == "gslides"
    assert src.label == "Gemini for Healthcare"
    assert src.slide_count == 1
    assert "Clinical Search & FHIR" in src.text
    assert "Emphasize HIPAA compliance." in src.text


def test_google_slides_url_without_cli_gives_agy_export_command(monkeypatch):
    monkeypatch.setattr(sources, "_find_gslides_cli", lambda: None)
    with pytest.raises(ValueError, match="gslides readonly export abc123"):
        sources.add_deck(Project(name="t"), "https://docs.google.com/presentation/d/abc123/edit")
