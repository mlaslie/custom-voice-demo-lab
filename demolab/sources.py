"""Slide deck ingestion: Google Slides (via gslides CLI or exported PDF+JSON), PowerPoint (.pptx), and PDF.

Slides from every deck are appended to the project's slides/ folder as 1920x1080 PNGs; a deck remembers its
slide_offset so the script can refer to slides by a single project-wide index, alongside a rich digest of
every slide's text and speaker notes.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

from . import store
from .models import Project, Source

W, H = 1920, 1080
_GSLIDES_ID_RE = re.compile(r"docs\.google\.com/presentation/d/([A-Za-z0-9_-]+)")


def _letterbox(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    img.thumbnail((W, H), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
    return canvas


def _add_slides(p: Project, images: list[Image.Image], src: Source) -> None:
    d = store.sub(p.id, "slides")
    src.slide_offset = len(p.slides)
    for i, im in enumerate(images):
        name = f"{src.id}_{i + 1:03d}.png"
        _letterbox(im).save(d / name)
        p.slides.append(name)
    src.slide_count = len(images)


def _render_pdf(path: pathlib.Path) -> tuple[list[Image.Image], list[str]]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    imgs, texts = [], []
    for page in pdf:
        w, h = page.get_size()
        imgs.append(page.render(scale=max(W / w, H / h)).to_pil())
        texts.append(page.get_textpage().get_text_range().strip())
    return imgs, texts


def _slides_digest(texts: list[str], notes: list[str], offset: int) -> str:
    out = []
    for i, t in enumerate(texts):
        out.append(f"--- Slide {offset + i} ---\n{t.strip()}")
        if i < len(notes) and notes[i].strip():
            out.append(f"[Speaker notes]\n{notes[i].strip()}")
    return "\n".join(out)


# ---- Google Slides AST helpers ------------------------------------------------------------------

def _shape_text(el: dict) -> str:
    runs = []
    for te in el.get("shape", {}).get("text", {}).get("textElements", []):
        content = te.get("textRun", {}).get("content", "")
        if content:
            runs.append(content)
    if runs:
        return "".join(runs).strip()
    tbl = el.get("table")
    if tbl:
        rows = []
        for row in tbl.get("tableRows", []):
            cells = []
            for cell in row.get("tableCells", []):
                c_runs = [
                    te.get("textRun", {}).get("content", "")
                    for te in cell.get("text", {}).get("textElements", [])
                ]
                cells.append("".join(c_runs).strip().replace("\n", " "))
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows)
    return ""


def parse_gslides_ast(data: dict) -> tuple[str, list[str], list[str]]:
    """Extract (presentation_title, slide_texts, speaker_notes) from a Google Slides API JSON object."""
    title = data.get("title", "")
    texts: list[str] = []
    notes: list[str] = []
    for sl in data.get("slides", []):
        parts = [t for el in sl.get("pageElements", []) if (t := _shape_text(el))]
        texts.append("\n".join(parts))
        note_parts = []
        notes_page = sl.get("slideProperties", {}).get("notesPage", {})
        for el in notes_page.get("pageElements", []):
            ph_type = el.get("shape", {}).get("placeholder", {}).get("type", "")
            if ph_type == "SLIDE_IMAGE":
                continue
            nt = _shape_text(el)
            if nt:
                note_parts.append(nt)
        notes.append("\n".join(note_parts))
    return title, texts, notes


def _find_gslides_cli() -> str | None:
    found = shutil.which("gslides")
    if found:
        return found
    home = pathlib.Path.home()
    candidates = [
        home / ".gemini" / "antigravity" / "bin" / "gslides",
        home / ".gemini" / "config" / "plugins" / "gslides" / "skills" / "gslides" / "scripts" / "gslides",
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def extract_gslides_id(ref: str) -> str | None:
    ref = ref.strip()
    m = _GSLIDES_ID_RE.search(ref)
    if m:
        return m.group(1)
    if ref.startswith("gslides:"):
        return ref.split(":", 1)[1].strip()
    return None


# ---- per kind -----------------------------------------------------------------------------------

def add_pdf(p: Project, path: pathlib.Path, label: str = "", gslides_json: pathlib.Path | None = None) -> Source:
    """Ingest a PDF deck, optionally enriched with speaker notes from a sibling `.gslides.json` AST file."""
    sidecar = gslides_json
    if sidecar is None:
        for cand in (path.with_suffix(".gslides.json"), path.with_suffix(".json")):
            if cand.is_file():
                sidecar = cand
                break
    notes: list[str] = []
    ast_texts: list[str] = []
    ast_title = ""
    if sidecar and sidecar.is_file():
        try:
            ast_title, ast_texts, notes = parse_gslides_ast(json.loads(sidecar.read_text()))
        except Exception:
            notes = []

    src = Source(
        kind="gslides" if ast_title or notes else "pdf",
        label=label or ast_title or path.name,
        ref=str(path),
    )
    imgs, pdf_texts = _render_pdf(path)
    _add_slides(p, imgs, src)
    final_texts = [
        (ast_texts[i] if i < len(ast_texts) and ast_texts[i].strip() else pdf_texts[i])
        for i in range(len(pdf_texts))
    ]
    src.text = _slides_digest(final_texts, notes, src.slide_offset)
    return src


def add_gslides(p: Project, pres_id: str, label: str = "") -> Source:
    """Export a Google Slides presentation directly via `gslides` CLI (PDF images + JSON speaker notes)."""
    cli = _find_gslides_cli()
    if not cli:
        raise ValueError(
            f"Google Slides CLI (`gslides`) is not installed to read presentation {pres_id}. "
            f"In Antigravity, export the deck first with `gslides readonly export {pres_id} deck.pdf --format pdf` "
            f"and `gslides readonly info {pres_id} --json > deck.gslides.json`, then pass `deck.pdf`."
        )
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="demolab-gslides-"))
    pdf_path = tmp / f"{pres_id}.pdf"
    json_path = tmp / f"{pres_id}.gslides.json"
    try:
        r_pdf = subprocess.run([cli, "readonly", "export", pres_id, str(pdf_path), "--format", "pdf"],
                               capture_output=True, text=True, timeout=90)
        if r_pdf.returncode != 0 or not pdf_path.exists():
            detail = (r_pdf.stderr or r_pdf.stdout).strip()[:300]
            raise ValueError(
                f"Direct `gslides` export could not access presentation {pres_id} ({detail or 'auth required in agent shell'}). "
                f"Run in your Antigravity shell: `gslides readonly export {pres_id} /tmp/{pres_id}.pdf --format pdf && "
                f"gslides readonly info {pres_id} --json > /tmp/{pres_id}.gslides.json`, then pass `/tmp/{pres_id}.pdf`."
            )
        r_info = subprocess.run([cli, "readonly", "info", pres_id, "--json"],
                                capture_output=True, text=True, timeout=60)
        if r_info.returncode == 0 and r_info.stdout.strip().startswith("{"):
            json_path.write_text(r_info.stdout)
        src = add_pdf(p, pdf_path, label=label, gslides_json=json_path if json_path.exists() else None)
        src.kind = "gslides"
        src.ref = f"https://docs.google.com/presentation/d/{pres_id}/edit"
        return src
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def add_pptx(p: Project, path: pathlib.Path, label: str = "") -> Source:
    from pptx import Presentation
    src = Source(kind="pptx", label=label or path.name, ref=str(path))
    prs = Presentation(str(path))
    texts, notes = [], []
    for slide in prs.slides:
        parts = []
        for shp in slide.shapes:
            if shp.has_text_frame and shp.text_frame.text.strip():
                parts.append(shp.text_frame.text.strip())
            if getattr(shp, "has_table", False) and shp.has_table:
                parts += [" | ".join(c.text for c in row.cells) for row in shp.table.rows]
        texts.append("\n".join(parts))
        notes.append(slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else "")
    pdf, why = _pptx_to_pdf(path)
    if pdf:
        imgs, _ = _render_pdf(pdf)
        _add_slides(p, imgs, src)
    else:
        src.slide_offset = len(p.slides)
        src.label += f" (text only, no slide images: {why})"
    src.text = _slides_digest(texts, notes, src.slide_offset)
    return src


KEYNOTE_EXPORT = """on run argv
  with timeout of 90 seconds
    tell application "Keynote"
      set d to open POSIX file (item 1 of argv)
      export d to POSIX file (item 2 of argv) as PDF
      close d saving no
    end tell
  end timeout
end run"""
EXPORT_TIMEOUT = 120
NO_CONVERTER = "install LibreOffice or Keynote, or add the deck's PDF export"


def _keynote_error(stderr: str) -> str:
    """Turn an osascript failure into something the user can act on."""
    if "-1743" in stderr or "Not authorized" in stderr:
        return ("macOS blocked control of Keynote. Allow it under System Settings > Privacy & Security > "
                "Automation, then add the deck again")
    if "-1712" in stderr or "timed out" in stderr:
        return ("Keynote didn't respond. Check Keynote or your screen for an open dialog (such as a "
                "permission prompt or an import warning), close it, then add the deck again")
    if "-600" in stderr or "isn't running" in stderr:
        return "Keynote couldn't be started. Open Keynote once, then add the deck again"
    msg = re.sub(r"^(\d+:\d+: )?execution error: ", "", stderr.strip().splitlines()[-1] if stderr.strip() else "")
    return f"Keynote export failed: {msg or 'no error message'}. Or add the deck's PDF export"


def _pptx_to_pdf(path: pathlib.Path) -> tuple[pathlib.Path | None, str]:
    """Slide images need a PDF: LibreOffice if installed, else Keynote on macOS."""
    soffice = shutil.which("soffice") or next(
        (x for x in ["/Applications/LibreOffice.app/Contents/MacOS/soffice"] if os.path.exists(x)), None)
    out = pathlib.Path(tempfile.mkdtemp(prefix="demolab-pptx-"))
    if soffice:
        try:
            r = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out), str(path)],
                               capture_output=True, text=True, timeout=EXPORT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return None, "LibreOffice took too long to convert the deck. Or add the deck's PDF export"
        pdfs = list(out.glob("*.pdf"))
        if pdfs:
            return pdfs[0], ""
        detail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["no error message"]
        return None, f"LibreOffice could not convert the deck: {detail[0]}. Or add the deck's PDF export"
    if sys.platform != "darwin" or not os.path.exists("/Applications/Keynote.app"):
        return None, NO_CONVERTER
    pdf = out / (path.stem + ".pdf")
    try:
        r = subprocess.run(["osascript", "-e", KEYNOTE_EXPORT, str(path.resolve()), str(pdf)],
                           capture_output=True, text=True, timeout=EXPORT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, _keynote_error("timed out")
    if r.returncode == 0 and pdf.exists():
        return pdf, ""
    return None, _keynote_error(r.stderr)


def add_deck(p: Project, ref: str, label: str = "", gslides_json: str = "") -> Source:
    """Ingest a Google Slides URL / `gslides:<ID>`, `.pdf` (with optional `.gslides.json` notes), or `.pptx`."""
    pres_id = extract_gslides_id(ref)
    if pres_id:
        return add_gslides(p, pres_id, label=label)
    path = pathlib.Path(ref).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"No such deck: {path}")
    ext = path.suffix.lower()
    if ext == ".pdf":
        sidecar = pathlib.Path(gslides_json).expanduser() if gslides_json else None
        return add_pdf(p, path, label, gslides_json=sidecar)
    if ext == ".pptx":
        return add_pptx(p, path, label)
    raise ValueError(f"Unsupported deck type {ext}: use a Google Slides URL, .pptx, or .pdf file")
