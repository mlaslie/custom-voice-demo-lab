"""Decks the session worked with (PowerPoint, PDF, Google Slides) become slide images for slide segments,
plus a text digest of each slide and its speaker notes for the session's model to write from.

Slides from every deck are appended to the project's slides/ folder as 1920x1080 PNGs; a deck remembers its
slide_offset so the script can refer to slides by a single project-wide index.
"""
from __future__ import annotations

import io
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


# ---- per kind -----------------------------------------------------------------------------------

def add_pdf(p: Project, path: pathlib.Path, label: str = "") -> Source:
    src = Source(kind="pdf", label=label or path.name, ref=str(path))
    imgs, texts = _render_pdf(path)
    _add_slides(p, imgs, src)
    src.text = _slides_digest(texts, [], src.slide_offset)
    return src


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
    """Slide images need a PDF: LibreOffice if installed, else Keynote on macOS (asks once for permission).
    Returns (pdf, "") or (None, why it could not be made)."""
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


def gslides_id(ref: str) -> str:
    m = re.search(r"/presentation/d/([A-Za-z0-9_-]+)", ref)
    return m.group(1) if m else ref.strip()


def add_gslides(p: Project, ref: str, label: str = "") -> Source:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from .google_auth import credentials
    creds = credentials()
    pid = gslides_id(ref)
    deck = build("slides", "v1", credentials=creds, cache_discovery=False).presentations().get(
        presentationId=pid).execute()
    texts, notes = [], []
    for s in deck.get("slides", []):
        texts.append(_gs_text(s.get("pageElements", [])))
        nprops = s.get("slideProperties", {}).get("notesPage", {})
        notes_id = nprops.get("notesProperties", {}).get("speakerNotesObjectId")
        notes.append(_gs_text([e for e in nprops.get("pageElements", []) if e.get("objectId") == notes_id]))
    req = build("drive", "v3", credentials=creds, cache_discovery=False).files().export_media(
        fileId=pid, mimeType="application/pdf")
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="demolab-gs-")) / "deck.pdf"
    tmp.write_bytes(buf.getvalue())
    src = Source(kind="gslides", label=label or deck.get("title", "Google Slides"), ref=pid)
    imgs, _ = _render_pdf(tmp)
    _add_slides(p, imgs, src)
    src.text = _slides_digest(texts, notes, src.slide_offset)
    return src


def _gs_text(elements: list[dict]) -> str:
    out = []
    for e in elements:
        for t in e.get("shape", {}).get("text", {}).get("textElements", []):
            out.append(t.get("textRun", {}).get("content", ""))
        for row in e.get("table", {}).get("tableRows", []):
            cells = ["".join(t.get("textRun", {}).get("content", "")
                             for t in c.get("text", {}).get("textElements", [])).strip()
                     for c in row.get("tableCells", [])]
            out.append(" | ".join(cells) + "\n")
    return "".join(out).strip()


def add_deck(p: Project, ref: str, label: str = "") -> Source:
    """A .pptx or .pdf path, or a Google Slides URL or id."""
    if "docs.google.com/presentation" in ref or re.fullmatch(r"[A-Za-z0-9_-]{25,}", ref.strip()):
        return add_gslides(p, ref, label)
    path = pathlib.Path(ref).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"No such deck: {path}")
    ext = path.suffix.lower()
    if ext == ".pdf":
        return add_pdf(p, path, label)
    if ext == ".pptx":
        return add_pptx(p, path, label)
    raise ValueError(f"Unsupported deck type {ext}: use .pptx, .pdf or a Google Slides link")
