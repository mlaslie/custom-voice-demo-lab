"""Self-contained pure-wheel OOXML (.pptx) to SVG / 1080p PNG / PDF renderer.

Parses `.pptx` ZIP archives via `lxml.etree` (themes, `clrMap` & `clrMapOvr`, master -> layout ->
slide inheritance, vector preset & custom shapes, connectors with arrowheads, gradients, shadows,
grouped diagrams, cropped PNG/SVG pictures, SmartArt `drawing*.xml`, cached charts, merged-cell
tables + `tableStyles.xml`, and rich bulleted/auto-fit text), generates clean SVG 1.1 slides in
typographic point coordinates, and rasterizes via `resvg_py` + Pillow.

Zero dependency on LibreOffice, Apple Keynote, or Microsoft PowerPoint.
"""
from __future__ import annotations

import base64
import colorsys
import dataclasses
import html
import io
import math
import pathlib
import posixpath
import re
import tempfile
import zipfile
from functools import lru_cache
from typing import Any

from lxml import etree
from PIL import Image, ImageFont
import resvg_py

EMU_PER_PT = 12700.0
DEFAULT_SLIDE_CX = 9144000  # 10 in = 720 pt
DEFAULT_SLIDE_CY = 5143500  # 5.625 in = 405 pt

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
NS_DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
NS_DSP = "http://schemas.microsoft.com/office/drawing/2008/diagram"
NS_ASVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"

A = f"{{{NS_A}}}"
P = f"{{{NS_P}}}"
R = f"{{{NS_R}}}"
C = f"{{{NS_C}}}"
DGM = f"{{{NS_DGM}}}"
DSP = f"{{{NS_DSP}}}"
ASVG = f"{{{NS_ASVG}}}"

DEFAULT_CLR_MAP = {
    "bg1": "lt1",
    "tx1": "dk1",
    "bg2": "lt2",
    "tx2": "dk2",
    "accent1": "accent1",
    "accent2": "accent2",
    "accent3": "accent3",
    "accent4": "accent4",
    "accent5": "accent5",
    "accent6": "accent6",
    "hlink": "hlink",
    "folHlink": "folHlink",
}

DEFAULT_SCHEME_COLORS = {
    "dk1": (0, 0, 0),
    "lt1": (255, 255, 255),
    "dk2": (68, 84, 106),
    "lt2": (231, 230, 230),
    "accent1": (68, 114, 196),
    "accent2": (237, 125, 49),
    "accent3": (165, 165, 165),
    "accent4": (255, 192, 0),
    "accent5": (91, 155, 213),
    "accent6": (112, 173, 71),
    "hlink": (5, 99, 193),
    "folHlink": (149, 79, 114),
}

PRESET_COLORS: dict[str, str] = {
    "aliceBlue": "F0F8FF", "antiqueWhite": "FAEBD7", "aqua": "00FFFF", "aquamarine": "7FFFD4",
    "azure": "F0FFFF", "beige": "F5F5DC", "bisque": "FFE4C4", "black": "000000",
    "blanchedAlmond": "FFEBCD", "blue": "0000FF", "blueViolet": "8A2BE2", "brown": "A52A2A",
    "burlyWood": "DEB887", "cadetBlue": "5F9EA0", "chartreuse": "7FFF00", "chocolate": "D2691E",
    "coral": "FF7F50", "cornflowerBlue": "6495ED", "cornsilk": "FFF8DC", "crimson": "DC143C",
    "cyan": "00FFFF", "darkBlue": "00008B", "darkCyan": "008B8B", "darkGoldenrod": "B8860B",
    "darkGray": "A9A9A9", "darkGreen": "006400", "darkGrey": "A9A9A9", "darkKhaki": "BDB76B",
    "darkMagenta": "8B008B", "darkOliveGreen": "556B2F", "darkOrange": "FF8C00", "darkOrchid": "9932CC",
    "darkRed": "8B0000", "darkSalmon": "E9967A", "darkSeaGreen": "8FBC8F", "darkSlateBlue": "483D8B",
    "darkSlateGray": "2F4F4F", "darkTurquoise": "00CED1", "darkViolet": "9400D3", "deepPink": "FF1493",
    "deepSkyBlue": "00BFFF", "dimGray": "696969", "dkBlue": "00008B", "dkCyan": "008B8B",
    "dkGoldenrod": "B8860B", "dkGray": "A9A9A9", "dkGreen": "006400", "dkKhaki": "BDB76B",
    "dkMagenta": "8B008B", "dkOliveGreen": "556B2F", "dkOrange": "FF8C00", "dkOrchid": "9932CC",
    "dkRed": "8B0000", "dkSalmon": "E9967A", "dkSeaGreen": "8FBC8F", "dkSlateBlue": "483D8B",
    "dkSlateGray": "2F4F4F", "dkTurquoise": "00CED1", "dkViolet": "9400D3", "dodgerBlue": "1E90FF",
    "firebrick": "B22222", "floralWhite": "FFFAF0", "forestGreen": "228B22", "fuchsia": "FF00FF",
    "gainsboro": "DCDCDC", "ghostWhite": "F8F8FF", "gold": "FFD700", "goldenrod": "DAA520",
    "gray": "808080", "green": "008000", "greenYellow": "ADFF2F", "grey": "808080",
    "honeydew": "F0FFF0", "hotPink": "FF69B4", "indianRed": "CD5C5C", "indigo": "4B0082",
    "ivory": "FFFFF0", "khaki": "F0E68C", "lavender": "E6E6FA", "lavenderBlush": "FFF0F5",
    "lawnGreen": "7CFC00", "lemonChiffon": "FFFACD", "lightBlue": "ADD8E6", "lightCoral": "F08080",
    "lightCyan": "E0FFFF", "lightGoldenrodYellow": "FAFAD2", "lightGray": "D3D3D3", "lightGreen": "90EE90",
    "lightPink": "FFB6C1", "lightSalmon": "FFA07A", "lightSeaGreen": "20B2AA", "lightSkyBlue": "87CEFA",
    "lightSlateGray": "778899", "lightSteelBlue": "B0C4DE", "lightYellow": "FFFFE0", "lime": "00FF00",
    "limeGreen": "32CD32", "linen": "FAF0E6", "ltBlue": "ADD8E6", "ltCoral": "F08080",
    "ltCyan": "E0FFFF", "ltGoldenrodYellow": "FAFAD2", "ltGray": "D3D3D3", "ltGreen": "90EE90",
    "ltPink": "FFB6C1", "ltSalmon": "FFA07A", "ltSeaGreen": "20B2AA", "ltSkyBlue": "87CEFA",
    "ltSlateGray": "778899", "ltSteelBlue": "B0C4DE", "ltYellow": "FFFFE0", "magenta": "FF00FF",
    "maroon": "800000", "medAquamarine": "66CDAA", "medBlue": "0000CD", "mediumAquamarine": "66CDAA",
    "mediumBlue": "0000CD", "mediumOrchid": "BA55D3", "mediumPurple": "9370DB", "mediumSeaGreen": "3CB371",
    "mediumSlateBlue": "7B68EE", "mediumSpringGreen": "00FA9A", "mediumTurquoise": "48D1CC",
    "mediumVioletRed": "C71585", "medOrchid": "BA55D3", "medPurple": "9370DB", "medSeaGreen": "3CB371",
    "medSlateBlue": "7B68EE", "medSpringGreen": "00FA9A", "medTurquoise": "48D1CC",
    "medVioletRed": "C71585", "midnightBlue": "191970", "mintCream": "F5FFFA", "mistyRose": "FFE4E1",
    "moccasin": "FFE4B5", "navajoWhite": "FFDEAD", "navy": "000080", "oldLace": "FDF5E6",
    "olive": "808000", "oliveDrab": "6B8E23", "orange": "FFA500", "orangeRed": "FF4500",
    "orchid": "DA70D6", "paleGoldenrod": "EEE8AA", "paleGreen": "98FB98", "paleTurquoise": "AFEEEE",
    "paleVioletRed": "DB7093", "papayaWhip": "FFEFD5", "peachPuff": "FFDAB9", "peru": "CD853F",
    "pink": "FFC0CB", "plum": "DDA0DD", "powderBlue": "B0E0E6", "purple": "800080",
    "red": "FF0000", "rosyBrown": "BC8F8F", "royalBlue": "4169E1", "saddleBrown": "8B4513",
    "salmon": "FA8072", "sandyBrown": "F4A460", "seaGreen": "2E8B57", "seaShell": "FFF5EE",
    "sienna": "A0522D", "silver": "C0C0C0", "skyBlue": "87CEEB", "slateBlue": "6A5ACD",
    "slateGray": "708090", "snow": "FFFAFA", "springGreen": "00FF7F", "steelBlue": "4682B4",
    "tan": "D2B48C", "teal": "008080", "thistle": "D8BFD8", "tomato": "FF6347",
    "turquoise": "40E0D0", "violet": "EE82EE", "wheat": "F5DEB3", "white": "FFFFFF",
    "whiteSmoke": "F5F5F5", "yellow": "FFFF00", "yellowGreen": "9ACD32",
}

FONT_ALIAS_CANDIDATES: dict[str, tuple[list[str], str]] = {
    "arial": ([
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ], "Arial, Liberation Sans, Helvetica Neue, DejaVu Sans, sans-serif"),
    "calibri": ([
        "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ], "Carlito, Calibri, Arial, Helvetica Neue, sans-serif"),
    "aptos": ([
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ], "Aptos, Arial, Helvetica Neue, Liberation Sans, sans-serif"),
    "roboto": ([
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ], "Roboto, Arial, Helvetica Neue, DejaVu Sans, sans-serif"),
    "inter": ([
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ], "Inter, Helvetica Neue, Arial, DejaVu Sans, sans-serif"),
    "segoe ui": ([
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ], "Segoe UI, Helvetica Neue, Arial, sans-serif"),
    "georgia": ([
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ], "Georgia, Liberation Serif, Times New Roman, serif"),
    "cambria": ([
        "/usr/share/fonts/truetype/crosextra/Caladea-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ], "Caladea, Cambria, Georgia, serif"),
    "consolas": ([
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ], "Consolas, Menlo, Courier New, monospace"),
    "courier new": ([
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ], "Courier New, Menlo, monospace"),
}

BOLD_FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

REG_FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

ITALIC_FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
]

BOLD_ITALIC_FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
]

_CTRL_RE = re.compile(r"[\x00-\x08\x0c\x0e-\x1f\x7f]")


def _sanitize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x0b", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return _CTRL_RE.sub("", text)


def _esc(val: Any) -> str:
    return html.escape(_sanitize_text(str(val)), quote=True)


def _emu_to_pt(val: str | int | float | None, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val) / EMU_PER_PT
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _hex_to_rgb(hx: str) -> tuple[int, int, int]:
    hx = hx.strip().lstrip("#")
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)
    if len(hx) != 6:
        return (0, 0, 0)
    return int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


@dataclasses.dataclass(frozen=True)
class Color:
    rgb: tuple[int, int, int]
    alpha: float = 1.0

    @property
    def hex(self) -> str:
        return _rgb_to_hex(self.rgb)


@dataclasses.dataclass
class Xfrm:
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    rot: float = 0.0
    flip_h: bool = False
    flip_v: bool = False
    ch_x: float = 0.0
    ch_y: float = 0.0
    ch_w: float = 0.0
    ch_h: float = 0.0
    has_pos: bool = False
    has_ext: bool = False


def _parse_xfrm(el: etree._Element | None) -> Xfrm:
    if el is None:
        return Xfrm()
    off = el.find(f"{A}off")
    ext = el.find(f"{A}ext")
    ch_off = el.find(f"{A}chOff")
    ch_ext = el.find(f"{A}chExt")
    rot_raw = el.get("rot")
    return Xfrm(
        x=_emu_to_pt(off.get("x")) if off is not None else 0.0,
        y=_emu_to_pt(off.get("y")) if off is not None else 0.0,
        w=_emu_to_pt(ext.get("cx")) if ext is not None else 0.0,
        h=_emu_to_pt(ext.get("cy")) if ext is not None else 0.0,
        rot=(float(rot_raw) / 60000.0) if rot_raw else 0.0,
        flip_h=el.get("flipH") in ("1", "true"),
        flip_v=el.get("flipV") in ("1", "true"),
        ch_x=_emu_to_pt(ch_off.get("x")) if ch_off is not None else 0.0,
        ch_y=_emu_to_pt(ch_off.get("y")) if ch_off is not None else 0.0,
        ch_w=_emu_to_pt(ch_ext.get("cx")) if ch_ext is not None else 0.0,
        ch_h=_emu_to_pt(ch_ext.get("cy")) if ch_ext is not None else 0.0,
        has_pos=off is not None,
        has_ext=ext is not None,
    )


def _merge_xfrm(primary: Xfrm, fallback: Xfrm | None) -> Xfrm:
    if fallback is None:
        return primary
    return Xfrm(
        x=primary.x if primary.has_pos else fallback.x,
        y=primary.y if primary.has_pos else fallback.y,
        w=primary.w if primary.has_ext else fallback.w,
        h=primary.h if primary.has_ext else fallback.h,
        rot=primary.rot if primary.rot else fallback.rot,
        flip_h=primary.flip_h or fallback.flip_h,
        flip_v=primary.flip_v or fallback.flip_v,
        has_pos=primary.has_pos or fallback.has_pos,
        has_ext=primary.has_ext or fallback.has_ext,
    )


class _Package:
    """Reads OPC zip entries, XML roots, `.rels` mappings, and embedded TTF/OTF fonts."""

    def __init__(self, pptx_path: str | pathlib.Path):
        self.path = pathlib.Path(pptx_path)
        self._zf = zipfile.ZipFile(self.path, "r")
        self._xml_cache: dict[str, etree._Element] = {}
        self._rels_cache: dict[str, dict[str, tuple[str, str]]] = {}

    def close(self) -> None:
        self._zf.close()

    def exists(self, part: str) -> bool:
        norm = part.lstrip("/")
        return norm in self._zf.namelist()

    def read_bytes(self, part: str) -> bytes:
        return self._zf.read(part.lstrip("/"))

    def read_xml(self, part: str) -> etree._Element | None:
        norm = part.lstrip("/")
        if norm in self._xml_cache:
            return self._xml_cache[norm]
        if norm not in self._zf.namelist():
            return None
        root = etree.fromstring(self._zf.read(norm))
        self._xml_cache[norm] = root
        return root

    def rels(self, part: str) -> dict[str, tuple[str, str]]:
        """Return `{rId: (relType, target_part_path)}` for `part`."""
        norm = part.lstrip("/")
        if norm in self._rels_cache:
            return self._rels_cache[norm]
        parent = posixpath.dirname(norm)
        base = posixpath.basename(norm)
        rels_path = f"{parent}/_rels/{base}.rels" if parent else f"_rels/{base}.rels"
        mapping: dict[str, tuple[str, str]] = {}
        root = self.read_xml(rels_path)
        if root is not None:
            for rel in root:
                if rel.get("TargetMode") == "External":
                    continue
                rid = rel.get("Id", "")
                rtype = rel.get("Type", "")
                tgt = rel.get("Target", "")
                if not rid or not tgt:
                    continue
                if tgt.startswith("/"):
                    resolved = tgt.lstrip("/")
                else:
                    resolved = posixpath.normpath(posixpath.join(parent, tgt))
                mapping[rid] = (rtype, resolved)
        self._rels_cache[norm] = mapping
        return mapping

    def rel_target(self, part: str, rid: str | None) -> str | None:
        if not rid:
            return None
        entry = self.rels(part).get(rid)
        return entry[1] if entry else None

    def first_rel_by_type_suffix(self, part: str, suffix: str) -> str | None:
        for _rid, (rtype, target) in self.rels(part).items():
            if rtype.endswith(suffix):
                return target
        return None

    def extract_embedded_fonts(self, tmp_dir: pathlib.Path) -> list[str]:
        out: list[str] = []
        for name in self._zf.namelist():
            if not name.startswith("ppt/fonts/"):
                continue
            raw = self._zf.read(name)
            if len(raw) < 4:
                continue
            head = raw[:4]
            if head in (b"\x00\x01\x00\x00", b"OTTO"):
                ext = ".otf" if head == b"OTTO" else ".ttf"
                dest = tmp_dir / (pathlib.Path(name).stem + ext)
                dest.write_bytes(raw)
                out.append(str(dest))
        return out


class _Theme:
    """Theme color scheme, font scheme, `fmtScheme` fill/line lists, and `clrMap` resolution."""

    def __init__(self, theme_root: etree._Element | None, clr_map: dict[str, str] | None = None):
        self.colors: dict[str, tuple[int, int, int]] = dict(DEFAULT_SCHEME_COLORS)
        self.clr_map: dict[str, str] = dict(DEFAULT_CLR_MAP)
        if clr_map:
            self.clr_map.update(clr_map)
        self.major_font = "Calibri"
        self.minor_font = "Calibri"
        self.fill_styles: list[etree._Element] = []
        self.bg_fill_styles: list[etree._Element] = []
        self.ln_styles: list[etree._Element] = []

        if theme_root is None:
            return

        elements = theme_root.find(f"{A}themeElements")
        if elements is None:
            return

        cs = elements.find(f"{A}clrScheme")
        if cs is not None:
            for child in cs:
                slot = etree.QName(child).localname
                srgb = child.find(f"{A}srgbClr")
                if srgb is not None and srgb.get("val"):
                    self.colors[slot] = _hex_to_rgb(srgb.get("val", "000000"))
                    continue
                sys_c = child.find(f"{A}sysClr")
                if sys_c is not None and (sys_c.get("lastClr") or sys_c.get("val")):
                    self.colors[slot] = _hex_to_rgb(sys_c.get("lastClr") or "000000")

        fs = elements.find(f"{A}fontScheme")
        if fs is not None:
            maj = fs.find(f"{A}majorFont/{A}latin")
            min_ = fs.find(f"{A}minorFont/{A}latin")
            if maj is not None and maj.get("typeface"):
                self.major_font = maj.get("typeface", self.major_font)
            if min_ is not None and min_.get("typeface"):
                self.minor_font = min_.get("typeface", self.minor_font)

        fmts = elements.find(f"{A}fmtScheme")
        if fmts is not None:
            fl = fmts.find(f"{A}fillStyleLst")
            bfl = fmts.find(f"{A}bgFillStyleLst")
            ll = fmts.find(f"{A}lnStyleLst")
            if fl is not None:
                self.fill_styles = list(fl)
            if bfl is not None:
                self.bg_fill_styles = list(bfl)
            if ll is not None:
                self.ln_styles = list(ll)

    def with_clr_map(self, override: dict[str, str] | None) -> _Theme:
        if not override:
            return self
        clone = dataclasses.replace(_ThemeSnapshot(self), clr_map={**self.clr_map, **override})
        return clone.to_theme()

    def resolve_font(self, typeface: str | None) -> str:
        if not typeface:
            return self.minor_font
        if typeface.startswith("+mj-"):
            return self.major_font
        if typeface.startswith("+mn-"):
            return self.minor_font
        return typeface

    def resolve_color(self, el: etree._Element | None, ph_clr: Color | None = None) -> Color | None:
        """Resolve an `<a:srgbClr>`, `<a:schemeClr>`, `<a:sysClr>`, `<a:prstClr>`, or `<a:scrgbClr>`."""
        if el is None:
            return None

        node = el
        local = etree.QName(node).localname
        if local not in ("srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr"):
            for tag in ("srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr"):
                found = el.find(f"{A}{tag}")
                if found is not None:
                    node = found
                    local = tag
                    break
            else:
                return None

        alpha = 1.0
        rgb = (0, 0, 0)
        if local == "srgbClr":
            rgb = _hex_to_rgb(node.get("val", "000000"))
        elif local == "sysClr":
            rgb = _hex_to_rgb(node.get("lastClr") or "000000")
        elif local == "prstClr":
            val = node.get("val", "black")
            rgb = _hex_to_rgb(PRESET_COLORS.get(val, "000000"))
        elif local == "scrgbClr":
            rgb = (
                int(round(_clamp(int(node.get("r", 0)) / 100000.0) * 255)),
                int(round(_clamp(int(node.get("g", 0)) / 100000.0) * 255)),
                int(round(_clamp(int(node.get("b", 0)) / 100000.0) * 255)),
            )
        elif local == "schemeClr":
            name = node.get("val", "tx1")
            if name == "phClr":
                if ph_clr is None:
                    return None
                rgb = ph_clr.rgb
                alpha = ph_clr.alpha
            else:
                mapped = self.clr_map.get(name, name)
                rgb = self.colors.get(mapped) or self.colors.get(name) or DEFAULT_SCHEME_COLORS.get(mapped, (0, 0, 0))

        rgb, alpha = _apply_color_transforms(rgb, alpha, node)
        return Color(rgb=rgb, alpha=alpha)


@dataclasses.dataclass
class _ThemeSnapshot:
    theme: _Theme
    clr_map: dict[str, str]

    def __init__(self, t: _Theme):
        self.theme = t
        self.clr_map = dict(t.clr_map)

    def to_theme(self) -> _Theme:
        out = _Theme(None, self.clr_map)
        out.colors = self.theme.colors
        out.major_font = self.theme.major_font
        out.minor_font = self.theme.minor_font
        out.fill_styles = self.theme.fill_styles
        out.bg_fill_styles = self.theme.bg_fill_styles
        out.ln_styles = self.theme.ln_styles
        return out


def _apply_color_transforms(rgb: tuple[int, int, int], alpha: float, node: etree._Element) -> tuple[tuple[int, int, int], float]:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    for mod in node:
        name = etree.QName(mod).localname
        raw = mod.get("val")
        if raw is None:
            continue
        val = int(raw) / 100000.0
        if name == "alpha":
            alpha = _clamp(val)
        elif name == "alphaMod":
            alpha = _clamp(alpha * val)
        elif name == "alphaOff":
            alpha = _clamp(alpha + val)
        elif name == "shade":
            r, g, b = r * val, g * val, b * val
        elif name == "tint":
            r = 1.0 - (1.0 - r) * val
            g = 1.0 - (1.0 - g) * val
            b = 1.0 - (1.0 - b) * val
        elif name in ("lumMod", "lumOff", "satMod", "satOff"):
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            if name == "lumMod":
                l = _clamp(l * val)
            elif name == "lumOff":
                l = _clamp(l + val)
            elif name == "satMod":
                s = _clamp(s * val)
            elif name == "satOff":
                s = _clamp(s + val)
            r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (
        (int(round(_clamp(r) * 255)), int(round(_clamp(g) * 255)), int(round(_clamp(b) * 255))),
        alpha,
    )


def _extract_clr_map(root: etree._Element | None) -> dict[str, str]:
    if root is None:
        return {}
    cm = root.find(f"{P}clrMap")
    if cm is not None:
        return dict(cm.attrib)
    ovr = root.find(f"{P}clrMapOvr/{A}overrideClrMapping")
    if ovr is not None:
        return dict(ovr.attrib)
    return {}


@lru_cache(maxsize=64)
def _load_pil_font(font_family: str, px: int, bold: bool, italic: bool, extra_fonts: tuple[str, ...] = ()) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fam = (font_family or "Arial").strip().lower()
    candidates: list[str] = list(extra_fonts)
    if fam in FONT_ALIAS_CANDIDATES and not bold and not italic:
        candidates.extend(FONT_ALIAS_CANDIDATES[fam][0])
    if bold and italic:
        candidates.extend(BOLD_ITALIC_FALLBACK_FONTS)
    elif bold:
        candidates.extend(BOLD_FALLBACK_FONTS)
    elif italic:
        candidates.extend(ITALIC_FALLBACK_FONTS)
    if fam in FONT_ALIAS_CANDIDATES:
        candidates.extend(FONT_ALIAS_CANDIDATES[fam][0])
    candidates.extend(REG_FALLBACK_FONTS)
    for path in candidates:
        if pathlib.Path(path).is_file():
            try:
                return ImageFont.truetype(path, px)
            except Exception:
                continue
    return ImageFont.load_default(px)


def _css_font_family(font_family: str | None) -> str:
    raw = (font_family or "Arial").strip()
    key = raw.lower()
    if key in FONT_ALIAS_CANDIDATES:
        return FONT_ALIAS_CANDIDATES[key][1]
    return f"{raw}, Arial, Helvetica Neue, DejaVu Sans, sans-serif"


def _measure_text(text: str, font_family: str, size_pt: float, bold: bool, italic: bool, extra_fonts: tuple[str, ...]) -> float:
    if not text:
        return 0.0
    # Measure at 4x resolution so fractional sizes (e.g. 10.5pt, 12.5pt) never truncate via integer px rounding.
    scale = 4
    px = max(16, int(round(size_pt * scale)))
    font = _load_pil_font(font_family, px, bold, italic, extra_fonts)
    try:
        return float(font.getlength(text)) / scale
    except Exception:
        bbox = font.getbbox(text)
        return float(bbox[2] - bbox[0]) / scale


# ---- Text Style Inheritance & Layout ------------------------------------------------------------

@dataclasses.dataclass
class _RunSpec:
    text: str
    font_family: str = "Calibri"
    size_pt: float = 18.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Color = Color((32, 33, 36))
    is_break: bool = False


@dataclasses.dataclass
class _ParaSpec:
    runs: list[_RunSpec]
    lvl: int = 0
    algn: str = "l"
    mar_l: float = 0.0
    indent: float = 0.0
    spc_bef: float = 0.0
    spc_aft: float = 4.0
    line_mult: float = 1.15
    line_pts: float | None = None
    bu_type: str = "none"  # "none" | "char" | "num"
    bu_char: str = "•"
    bu_start: int = 1
    bu_color: Color | None = None
    bu_sz_pct: float = 1.0


def _merge_level_style(dst: dict[str, Any], el: etree._Element | None, theme: _Theme, fallback_clr: Color | None = None) -> None:
    if el is None:
        return
    if el.get("algn"):
        dst["algn"] = el.get("algn")
    if el.get("marL") is not None:
        dst["mar_l"] = _emu_to_pt(el.get("marL"))
    if el.get("indent") is not None:
        dst["indent"] = _emu_to_pt(el.get("indent"))

    spc_bef = el.find(f"{A}spcBef/{A}spcPts")
    if spc_bef is not None and spc_bef.get("val"):
        dst["spc_bef"] = int(spc_bef.get("val")) / 100.0
    spc_aft = el.find(f"{A}spcAft/{A}spcPts")
    if spc_aft is not None and spc_aft.get("val"):
        dst["spc_aft"] = int(spc_aft.get("val")) / 100.0
    ln_pct = el.find(f"{A}lnSpc/{A}spcPct")
    if ln_pct is not None and ln_pct.get("val"):
        dst["line_mult"] = max(0.8, int(ln_pct.get("val")) / 100000.0)
    ln_pts = el.find(f"{A}lnSpc/{A}spcPts")
    if ln_pts is not None and ln_pts.get("val"):
        dst["line_pts"] = int(ln_pts.get("val")) / 100.0

    if el.find(f"{A}buNone") is not None:
        dst["bu_type"] = "none"
    elif (bc := el.find(f"{A}buChar")) is not None:
        dst["bu_type"] = "char"
        dst["bu_char"] = bc.get("char", "•")
    elif (bn := el.find(f"{A}buAutoNum")) is not None:
        dst["bu_type"] = "num"
        dst["bu_start"] = int(bn.get("startAt", "1"))
    if (bclr := el.find(f"{A}buClr")) is not None:
        c = theme.resolve_color(bclr, fallback_clr)
        if c:
            dst["bu_color"] = c
    if (bsz := el.find(f"{A}buSzPct")) is not None and bsz.get("val"):
        dst["bu_sz_pct"] = int(bsz.get("val")) / 100000.0

    rpr = el.find(f"{A}defRPr")
    if rpr is not None:
        if rpr.get("sz"):
            dst["size_pt"] = int(rpr.get("sz")) / 100.0
        if rpr.get("b") is not None:
            dst["bold"] = rpr.get("b") in ("1", "true")
        if rpr.get("i") is not None:
            dst["italic"] = rpr.get("i") in ("1", "true")
        if rpr.get("u") is not None:
            dst["underline"] = rpr.get("u") not in ("none", "0", "false")
        latin = rpr.find(f"{A}latin")
        if latin is not None and latin.get("typeface"):
            dst["font_family"] = theme.resolve_font(latin.get("typeface"))
        sfill = rpr.find(f"{A}solidFill")
        if sfill is not None:
            c = theme.resolve_color(sfill, fallback_clr)
            if c:
                dst["color"] = c


def _build_level_defaults(lst_styles: list[etree._Element | None], lvl: int, theme: _Theme, font_ref_clr: Color | None) -> dict[str, Any]:
    tx1_rgb = theme.colors.get(theme.clr_map.get("tx1", "dk1"), (32, 33, 36))
    dst: dict[str, Any] = {
        "algn": "l",
        "mar_l": 0.0,
        "indent": 0.0,
        "spc_bef": 0.0,
        "spc_aft": 3.0,
        "line_mult": 1.15,
        "line_pts": None,
        "bu_type": "none",
        "bu_char": "•",
        "bu_start": 1,
        "bu_color": None,
        "bu_sz_pct": 1.0,
        "size_pt": 18.0,
        "bold": False,
        "italic": False,
        "underline": False,
        "font_family": theme.minor_font,
        "color": font_ref_clr or Color(tx1_rgb),
    }
    tag = f"{A}lvl{min(max(lvl, 0), 8) + 1}pPr"
    for ls in lst_styles:
        if ls is None:
            continue
        _merge_level_style(dst, ls.find(f"{A}defPPr"), theme, font_ref_clr)
        _merge_level_style(dst, ls.find(tag), theme, font_ref_clr)
    return dst


def _parse_paragraphs(
    tx_body: etree._Element,
    lst_styles: list[etree._Element | None],
    theme: _Theme,
    font_ref_clr: Color | None,
    slide_num: int,
    default_algn: str | None = None,
    default_size_pt: float | None = None,
    default_color: Color | None = None,
    default_bold: bool | None = None,
) -> list[_ParaSpec]:
    paras: list[_ParaSpec] = []
    local_lst = tx_body.find(f"{A}lstStyle")
    chain = [*lst_styles, local_lst]

    for p_el in tx_body.findall(f"{A}p"):
        ppr = p_el.find(f"{A}pPr")
        lvl = int(ppr.get("lvl", "0")) if ppr is not None else 0
        style = _build_level_defaults(chain, lvl, theme, font_ref_clr)
        if default_algn and ppr is None:
            style["algn"] = default_algn
        if default_size_pt is not None and style["size_pt"] == 18.0:
            style["size_pt"] = default_size_pt
        if default_color is not None:
            style["color"] = default_color
        if default_bold is not None:
            style["bold"] = default_bold
        if ppr is not None:
            _merge_level_style(style, ppr, theme, font_ref_clr)

        runs: list[_RunSpec] = []
        for child in p_el:
            ln = etree.QName(child).localname
            if ln in ("r", "fld"):
                if ln == "fld" and child.get("type") == "slidenum":
                    raw_txt = str(slide_num)
                else:
                    t_el = child.find(f"{A}t")
                    raw_txt = _sanitize_text(t_el.text or "") if t_el is not None else ""
                rpr = child.find(f"{A}rPr")
                ff = style["font_family"]
                sz = style["size_pt"]
                bld = style["bold"]
                ita = style["italic"]
                und = style["underline"]
                clr = style["color"]
                if rpr is not None:
                    if rpr.get("sz"):
                        sz = int(rpr.get("sz")) / 100.0
                    if rpr.get("b") is not None:
                        bld = rpr.get("b") in ("1", "true")
                    if rpr.get("i") is not None:
                        ita = rpr.get("i") in ("1", "true")
                    if rpr.get("u") is not None:
                        und = rpr.get("u") not in ("none", "0", "false")
                    lat = rpr.find(f"{A}latin")
                    if lat is not None and lat.get("typeface"):
                        ff = theme.resolve_font(lat.get("typeface"))
                    sfill = rpr.find(f"{A}solidFill")
                    if sfill is not None:
                        rc = theme.resolve_color(sfill, font_ref_clr)
                        if rc:
                            clr = rc
                if raw_txt:
                    parts = raw_txt.split("\n")
                    for idx_p, part in enumerate(parts):
                        if part:
                            runs.append(_RunSpec(text=part, font_family=ff, size_pt=sz, bold=bld, italic=ita, underline=und, color=clr))
                        if idx_p < len(parts) - 1:
                            runs.append(_RunSpec(text="", font_family=ff, size_pt=sz, is_break=True))
            elif ln == "br":
                runs.append(_RunSpec(text="", font_family=style["font_family"], size_pt=style["size_pt"], is_break=True))

        paras.append(
            _ParaSpec(
                runs=runs,
                lvl=lvl,
                algn=style["algn"],
                mar_l=style["mar_l"],
                indent=style["indent"],
                spc_bef=style["spc_bef"],
                spc_aft=style["spc_aft"],
                line_mult=style["line_mult"],
                line_pts=style["line_pts"],
                bu_type=style["bu_type"],
                bu_char=style["bu_char"],
                bu_start=style["bu_start"],
                bu_color=style["bu_color"],
                bu_sz_pct=style["bu_sz_pct"],
            )
        )
    return paras


def _has_visible_text(paras: list[_ParaSpec]) -> bool:
    return any(any(r.text.strip() for r in p.runs) for p in paras)


def _tokenize_runs(runs: list[_RunSpec]) -> list[_RunSpec]:
    tokens: list[_RunSpec] = []
    for r in runs:
        if r.is_break:
            tokens.append(r)
            continue
        for piece in re.findall(r"\S+|\s+", r.text):
            tokens.append(dataclasses.replace(r, text=piece))
    return tokens


@dataclasses.dataclass
class _PlacedLine:
    para: _ParaSpec
    runs: list[_RunSpec]
    bullet: str
    bullet_color: Color
    bullet_size: float
    x_left: float
    text_width: float
    height: float
    ascent: float
    y_baseline: float = 0.0
    gap_after: float = 0.0


def _layout_paragraphs(
    paras: list[_ParaSpec],
    box_w: float,
    box_h: float,
    scale: float,
    wrap: bool,
    extra_fonts: tuple[str, ...],
) -> tuple[list[_PlacedLine], float]:
    placed: list[_PlacedLine] = []
    y = 0.0
    auto_nums: dict[int, int] = {}

    for p_idx, p in enumerate(paras):
        tokens = _tokenize_runs(p.runs)
        if p.bu_type == "num" and any(r.text.strip() for r in p.runs):
            n = auto_nums.get(p.lvl, p.bu_start)
            bullet_str = f"{n}."
            auto_nums[p.lvl] = n + 1
        elif p.bu_type == "char" and any(r.text.strip() for r in p.runs):
            bullet_str = p.bu_char
        else:
            bullet_str = ""

        mar_l = max(0.0, p.mar_l * scale)
        indent = p.indent * scale
        first_left = max(0.0, mar_l + indent)
        cont_left = mar_l

        first_size = (p.runs[0].size_pt if p.runs else 18.0) * scale
        first_color = p.runs[0].color if p.runs else Color((32, 33, 36))

        lines_tokens: list[list[_RunSpec]] = []
        if not tokens:
            lines_tokens.append([])
        else:
            cur: list[_RunSpec] = []
            cur_w = 0.0
            avail = max(8.0, box_w - first_left)
            for tok in tokens:
                if tok.is_break:
                    lines_tokens.append(cur)
                    cur = []
                    cur_w = 0.0
                    avail = max(8.0, box_w - cont_left)
                    continue
                sz = tok.size_pt * scale
                tw = _measure_text(tok.text, tok.font_family, sz, tok.bold, tok.italic, extra_fonts)
                # Leave a ~4% wrap margin so minor Pillow vs resvg font metric differences never clip borders.
                if wrap and cur and cur_w + tw > avail * 0.96 and tok.text.strip():
                    while cur and not cur[-1].text.strip():
                        cur.pop()
                    lines_tokens.append(cur)
                    cur = []
                    cur_w = 0.0
                    avail = max(8.0, box_w - cont_left)
                    if not tok.text.strip():
                        continue
                cur.append(dataclasses.replace(tok, size_pt=sz))
                cur_w += tw
            lines_tokens.append(cur)

        y += p.spc_bef * scale
        for li, lruns in enumerate(lines_tokens):
            while lruns and not lruns[-1].text.strip() and len(lruns) > 1:
                lruns.pop()
            # Merge adjacent identical-style spans to keep SVG compact
            merged: list[_RunSpec] = []
            for r in lruns:
                if (
                    merged
                    and not r.is_break
                    and merged[-1].font_family == r.font_family
                    and abs(merged[-1].size_pt - r.size_pt) < 0.01
                    and merged[-1].bold == r.bold
                    and merged[-1].italic == r.italic
                    and merged[-1].underline == r.underline
                    and merged[-1].color == r.color
                ):
                    merged[-1] = dataclasses.replace(merged[-1], text=merged[-1].text + r.text)
                else:
                    merged.append(r)

            max_sz = max((r.size_pt for r in merged), default=first_size)
            tw = sum(_measure_text(r.text, r.font_family, r.size_pt, r.bold, r.italic, extra_fonts) for r in merged)
            line_h = (p.line_pts * scale) if p.line_pts else (max_sz * p.line_mult)
            line_h = max(line_h, max_sz * 1.05)
            ascent = max_sz * 0.82
            is_last_in_para = li == len(lines_tokens) - 1
            gap_after = (p.spc_aft * scale) if (is_last_in_para and p_idx < len(paras) - 1) else 0.0

            placed.append(
                _PlacedLine(
                    para=p,
                    runs=merged,
                    bullet=bullet_str if li == 0 else "",
                    bullet_color=p.bu_color or first_color,
                    bullet_size=first_size * p.bu_sz_pct,
                    x_left=first_left if li == 0 else cont_left,
                    text_width=tw,
                    height=line_h,
                    ascent=ascent,
                    y_baseline=y + ascent + (line_h - max_sz) * 0.35,
                    gap_after=gap_after,
                )
            )
            y += line_h + gap_after

    return placed, y


def _render_tx_body(
    tx_body: etree._Element | None,
    xfrm: Xfrm,
    lst_styles: list[etree._Element | None],
    theme: _Theme,
    font_ref_clr: Color | None,
    slide_num: int,
    extra_fonts: tuple[str, ...],
    *,
    default_algn: str | None = None,
    default_size_pt: float | None = None,
    default_color: Color | None = None,
    default_bold: bool | None = None,
    default_anchor: str = "t",
    default_insets: tuple[float, float, float, float] = (7.2, 7.2, 3.6, 3.6),
) -> str:
    if tx_body is None or xfrm.w <= 1 or xfrm.h <= 1:
        return ""

    body_pr = tx_body.find(f"{A}bodyPr")
    l_ins, r_ins, t_ins, b_ins = default_insets
    anchor = default_anchor
    wrap = True
    font_scale = 1.0
    if body_pr is not None:
        if body_pr.get("lIns") is not None:
            l_ins = _emu_to_pt(body_pr.get("lIns"))
        if body_pr.get("rIns") is not None:
            r_ins = _emu_to_pt(body_pr.get("rIns"))
        if body_pr.get("tIns") is not None:
            t_ins = _emu_to_pt(body_pr.get("tIns"))
        if body_pr.get("bIns") is not None:
            b_ins = _emu_to_pt(body_pr.get("bIns"))
        if body_pr.get("anchor"):
            anchor = body_pr.get("anchor", anchor)
        if body_pr.get("wrap") == "none":
            wrap = False
        norm_fit = body_pr.find(f"{A}normAutofit")
        if norm_fit is not None and norm_fit.get("fontScale"):
            font_scale = _clamp(int(norm_fit.get("fontScale")) / 100000.0, 0.4, 1.0)

    paras = _parse_paragraphs(
        tx_body,
        lst_styles,
        theme,
        font_ref_clr,
        slide_num,
        default_algn=default_algn,
        default_size_pt=default_size_pt,
        default_color=default_color,
        default_bold=default_bold,
    )
    if not _has_visible_text(paras):
        return ""

    box_w = max(8.0, xfrm.w - l_ins - r_ins)
    box_h = max(8.0, xfrm.h - t_ins - b_ins)

    # Auto-shrink slightly if text overflows vertically inside its container
    scale = font_scale
    lines, total_h = _layout_paragraphs(paras, box_w, box_h, scale, wrap, extra_fonts)
    for _ in range(5):
        if total_h <= box_h * 1.04 or scale <= 0.55:
            break
        scale = max(0.55, scale * min(0.9, math.sqrt(box_h / max(total_h, 1.0))))
        lines, total_h = _layout_paragraphs(paras, box_w, box_h, scale, wrap, extra_fonts)

    y_off = t_ins
    if anchor == "ctr":
        y_off = t_ins + max(0.0, (box_h - total_h) / 2.0)
    elif anchor == "b":
        y_off = t_ins + max(0.0, box_h - total_h)

    svg_parts: list[str] = []
    for ln in lines:
        y = xfrm.y + y_off + ln.y_baseline
        algn = ln.para.algn
        anchor_attr = ""
        if algn == "ctr" and not ln.bullet:
            x = xfrm.x + l_ins + ln.x_left + max(0.0, (box_w - ln.x_left) / 2.0)
            anchor_attr = ' text-anchor="middle"'
        elif algn == "ctr":
            x = xfrm.x + l_ins + ln.x_left + max(0.0, (box_w - ln.x_left - ln.text_width) / 2.0)
        elif algn == "r" and not ln.bullet:
            x = xfrm.x + l_ins + box_w
            anchor_attr = ' text-anchor="end"'
        elif algn == "r":
            x = xfrm.x + l_ins + max(ln.x_left, box_w - ln.text_width)
        else:
            x = xfrm.x + l_ins + ln.x_left

        if ln.bullet:
            bx = max(xfrm.x + l_ins, x - max(10.0, ln.bullet_size * 0.75))
            if ln.para.indent < 0 and algn == "l":
                bx = xfrm.x + l_ins + ln.x_left
                x = max(x, xfrm.x + l_ins + ln.para.mar_l * scale)
            svg_parts.append(
                f'<text x="{bx:.2f}" y="{y:.2f}" font-family="Arial, sans-serif" '
                f'font-size="{ln.bullet_size:.2f}" fill="{ln.bullet_color.hex}" '
                f'fill-opacity="{ln.bullet_color.alpha:.3f}">{_esc(ln.bullet)}</text>'
            )

        if not ln.runs:
            continue
        runs_to_emit = list(ln.runs)
        if algn in ("ctr", "r") and runs_to_emit:
            trimmed = runs_to_emit[-1].text.rstrip(" \t")
            if trimmed != runs_to_emit[-1].text:
                runs_to_emit[-1] = dataclasses.replace(runs_to_emit[-1], text=trimmed)
        tspans: list[str] = []
        for r in runs_to_emit:
            if not r.text:
                continue
            attrs = [
                f'font-family="{_esc(_css_font_family(r.font_family))}"',
                f'font-size="{r.size_pt:.2f}"',
                f'fill="{r.color.hex}"',
            ]
            if r.color.alpha < 0.999:
                attrs.append(f'fill-opacity="{r.color.alpha:.3f}"')
            if r.bold:
                attrs.append('font-weight="700"')
            if r.italic:
                attrs.append('font-style="italic"')
            if r.underline:
                attrs.append('text-decoration="underline"')
            tspans.append(f'<tspan {" ".join(attrs)}>{_esc(r.text)}</tspan>')
        if tspans:
            svg_parts.append(f'<text x="{x:.2f}" y="{y:.2f}"{anchor_attr} xml:space="preserve">{"".join(tspans)}</text>')

    return "\n".join(svg_parts)


# ---- Geometry Paths & Fills / Strokes -----------------------------------------------------------

def _geom_av_map(geom_el: etree._Element | None) -> dict[str, int]:
    out: dict[str, int] = {}
    if geom_el is None:
        return out
    av_lst = geom_el.find(f"{A}avLst")
    if av_lst is None:
        return out
    for gd in av_lst.findall(f"{A}gd"):
        name = gd.get("name", "")
        fmla = gd.get("fmla", "")
        if name and fmla.startswith("val "):
            try:
                out[name] = int(fmla.split()[1])
            except ValueError:
                pass
    return out


def _pts_path(pts: list[tuple[float, float]], close: bool = True) -> str:
    if not pts:
        return ""
    cmds = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    cmds.extend(f"L {px:.2f} {py:.2f}" for px, py in pts[1:])
    if close:
        cmds.append("Z")
    return " ".join(cmds)


def _preset_svg_path(prst: str, w: float, h: float, av: dict[str, int]) -> tuple[str, bool]:
    """Return `(svg_path_in_local_0_0_w_h, is_open_line)`."""
    if w <= 0 or h <= 0:
        return "", False
    m = min(w, h)
    if prst in ("rect", "flowChartProcess"):
        return f"M 0 0 L {w:.2f} 0 L {w:.2f} {h:.2f} L 0 {h:.2f} Z", False
    if prst == "roundRect":
        adj = av.get("adj", 16667) / 100000.0
        r = min(m * _clamp(adj, 0.0, 0.5), w / 2.0, h / 2.0)
        if r <= 0.1:
            return f"M 0 0 L {w:.2f} 0 L {w:.2f} {h:.2f} L 0 {h:.2f} Z", False
        return (
            f"M {r:.2f} 0 L {w-r:.2f} 0 Q {w:.2f} 0 {w:.2f} {r:.2f} "
            f"L {w:.2f} {h-r:.2f} Q {w:.2f} {h:.2f} {w-r:.2f} {h:.2f} "
            f"L {r:.2f} {h:.2f} Q 0 {h:.2f} 0 {h-r:.2f} "
            f"L 0 {r:.2f} Q 0 0 {r:.2f} 0 Z"
        ), False
    if prst == "snip1Rect":
        adj = av.get("adj", 16667) / 100000.0
        c = m * _clamp(adj, 0.0, 0.5)
        return _pts_path([(0, 0), (w - c, 0), (w, c), (w, h), (0, h)]), False
    if prst == "snip2SameRect":
        c = m * _clamp(av.get("adj1", 16667) / 100000.0, 0.0, 0.5)
        return _pts_path([(c, 0), (w - c, 0), (w, c), (w, h), (0, h), (0, c)]), False
    if prst in ("ellipse", "flowChartConnector"):
        rx, ry = w / 2.0, h / 2.0
        return (
            f"M {rx:.2f} 0 A {rx:.2f} {ry:.2f} 0 1 0 {rx:.2f} {h:.2f} "
            f"A {rx:.2f} {ry:.2f} 0 1 0 {rx:.2f} 0 Z"
        ), False
    if prst == "triangle":
        adj = _clamp(av.get("adj", 50000) / 100000.0, 0.0, 1.0)
        return _pts_path([(w * adj, 0), (w, h), (0, h)]), False
    if prst == "rtTriangle":
        return _pts_path([(0, 0), (w, h), (0, h)]), False
    if prst in ("diamond", "flowChartDecision"):
        return _pts_path([(w / 2.0, 0), (w, h / 2.0), (w / 2.0, h), (0, h / 2.0)]), False
    if prst == "parallelogram":
        dx = m * _clamp(av.get("adj", 25000) / 100000.0, 0.0, 1.0)
        dx = min(dx, w * 0.48)
        return _pts_path([(dx, 0), (w, 0), (w - dx, h), (0, h)]), False
    if prst == "trapezoid":
        dx = m * _clamp(av.get("adj", 25000) / 100000.0, 0.0, 0.49)
        return _pts_path([(dx, 0), (w - dx, 0), (w, h), (0, h)]), False
    if prst in ("pentagon", "hexagon", "octagon"):
        sides = {"pentagon": 5, "hexagon": 6, "octagon": 8}[prst]
        if prst == "hexagon":
            dx = min(w * 0.45, m * _clamp(av.get("adj", 25000) / 100000.0, 0.0, 0.5))
            return _pts_path([(dx, 0), (w - dx, 0), (w, h / 2.0), (w - dx, h), (dx, h), (0, h / 2.0)]), False
        pts = []
        cx, cy = w / 2.0, h / 2.0
        for i in range(sides):
            ang = -math.pi / 2.0 + (2.0 * math.pi * i / sides)
            pts.append((cx + cx * math.cos(ang), cy + cy * math.sin(ang)))
        return _pts_path(pts), False
    if prst == "chevron":
        dx = min(w * 0.8, m * _clamp(av.get("adj", 50000) / 100000.0, 0.0, 1.0))
        return _pts_path([(0, 0), (w - dx, 0), (w, h / 2.0), (w - dx, h), (0, h), (dx, h / 2.0)]), False
    if prst == "homePlate":
        dx = min(w * 0.8, m * _clamp(av.get("adj", 50000) / 100000.0, 0.0, 1.0))
        return _pts_path([(0, 0), (w - dx, 0), (w, h / 2.0), (w - dx, h), (0, h)]), False
    if prst == "rightArrow":
        adj1 = _clamp(av.get("adj1", 50000) / 100000.0, 0.05, 0.95)
        head_w = min(w * 0.85, m * _clamp(av.get("adj2", 50000) / 100000.0, 0.05, 1.0))
        shaft_half = (h * adj1) / 2.0
        cy = h / 2.0
        sx = w - head_w
        return _pts_path([(0, cy - shaft_half), (sx, cy - shaft_half), (sx, 0), (w, cy), (sx, h), (sx, cy + shaft_half), (0, cy + shaft_half)]), False
    if prst == "leftArrow":
        adj1 = _clamp(av.get("adj1", 50000) / 100000.0, 0.05, 0.95)
        head_w = min(w * 0.85, m * _clamp(av.get("adj2", 50000) / 100000.0, 0.05, 1.0))
        shaft_half = (h * adj1) / 2.0
        cy = h / 2.0
        return _pts_path([(0, cy), (head_w, 0), (head_w, cy - shaft_half), (w, cy - shaft_half), (w, cy + shaft_half), (head_w, cy + shaft_half), (head_w, h)]), False
    if prst == "upArrow":
        adj1 = _clamp(av.get("adj1", 50000) / 100000.0, 0.05, 0.95)
        head_h = min(h * 0.85, m * _clamp(av.get("adj2", 50000) / 100000.0, 0.05, 1.0))
        shaft_half = (w * adj1) / 2.0
        cx = w / 2.0
        return _pts_path([(cx, 0), (w, head_h), (cx + shaft_half, head_h), (cx + shaft_half, h), (cx - shaft_half, h), (cx - shaft_half, head_h), (0, head_h)]), False
    if prst == "downArrow":
        adj1 = _clamp(av.get("adj1", 50000) / 100000.0, 0.05, 0.95)
        head_h = min(h * 0.85, m * _clamp(av.get("adj2", 50000) / 100000.0, 0.05, 1.0))
        shaft_half = (w * adj1) / 2.0
        cx = w / 2.0
        sy = h - head_h
        return _pts_path([(cx - shaft_half, 0), (cx + shaft_half, 0), (cx + shaft_half, sy), (w, sy), (cx, h), (0, sy), (cx - shaft_half, sy)]), False
    if prst == "leftRightArrow":
        adj1 = _clamp(av.get("adj1", 50000) / 100000.0, 0.05, 0.95)
        head_w = min(w * 0.42, m * _clamp(av.get("adj2", 50000) / 100000.0, 0.05, 1.0))
        sh = (h * adj1) / 2.0
        cy = h / 2.0
        return _pts_path([(0, cy), (head_w, 0), (head_w, cy - sh), (w - head_w, cy - sh), (w - head_w, 0), (w, cy), (w - head_w, h), (w - head_w, cy + sh), (head_w, cy + sh), (head_w, h)]), False
    if prst == "notchedRightArrow":
        adj1 = _clamp(av.get("adj1", 50000) / 100000.0, 0.05, 0.95)
        head_w = min(w * 0.8, m * _clamp(av.get("adj2", 50000) / 100000.0, 0.05, 1.0))
        sh = (h * adj1) / 2.0
        cy = h / 2.0
        sx = w - head_w
        return _pts_path([(0, cy - sh), (sx, cy - sh), (sx, 0), (w, cy), (sx, h), (sx, cy + sh), (0, cy + sh), (sh, cy)]), False
    if prst == "star5":
        cx, cy = w / 2.0, h / 2.0
        ir = 0.382
        pts = []
        for i in range(10):
            ang = -math.pi / 2.0 + i * math.pi / 5.0
            rad = 1.0 if i % 2 == 0 else ir
            pts.append((cx + cx * rad * math.cos(ang), cy + cy * rad * math.sin(ang)))
        return _pts_path(pts), False
    if prst in ("donut", "blockArc"):
        rx, ry = w / 2.0, h / 2.0
        t = _clamp(av.get("adj", 25000) / 100000.0, 0.05, 0.48)
        irx, iry = max(1.0, rx - m * t), max(1.0, ry - m * t)
        outer = f"M {rx:.2f} 0 A {rx:.2f} {ry:.2f} 0 1 0 {rx:.2f} {h:.2f} A {rx:.2f} {ry:.2f} 0 1 0 {rx:.2f} 0 Z"
        inner = f"M {rx:.2f} {ry-iry:.2f} A {irx:.2f} {iry:.2f} 0 1 1 {rx:.2f} {ry+iry:.2f} A {irx:.2f} {iry:.2f} 0 1 1 {rx:.2f} {ry-iry:.2f} Z"
        return f"{outer} {inner}", False
    if prst == "wedgeRoundRectCallout":
        r = min(m * 0.15, w / 2.0, h / 2.0)
        return (
            f"M {r:.2f} 0 L {w-r:.2f} 0 Q {w:.2f} 0 {w:.2f} {r:.2f} "
            f"L {w:.2f} {h*0.78-r:.2f} Q {w:.2f} {h*0.78:.2f} {w-r:.2f} {h*0.78:.2f} "
            f"L {w*0.58:.2f} {h*0.78:.2f} L {w*0.42:.2f} {h:.2f} L {w*0.44:.2f} {h*0.78:.2f} "
            f"L {r:.2f} {h*0.78:.2f} Q 0 {h*0.78:.2f} 0 {h*0.78-r:.2f} L 0 {r:.2f} Q 0 0 {r:.2f} 0 Z"
        ), False
    if prst in ("line", "straightConnector1"):
        return f"M 0 0 L {w:.2f} {h:.2f}", True
    if prst == "bentConnector2":
        return f"M 0 0 L {w:.2f} 0 L {w:.2f} {h:.2f}", True
    if prst == "bentConnector3":
        mx = w / 2.0
        return f"M 0 0 L {mx:.2f} 0 L {mx:.2f} {h:.2f} L {w:.2f} {h:.2f}", True
    if prst == "curvedConnector3":
        mx = w / 2.0
        return f"M 0 0 C {mx:.2f} 0 {mx:.2f} {h:.2f} {w:.2f} {h:.2f}", True
    if prst in ("leftBrace", "rightBrace", "bracePair", "bracketPair"):
        return f"M 0 0 L {w:.2f} 0 M {w:.2f} {h:.2f} L 0 {h:.2f}", True
    return f"M 0 0 L {w:.2f} 0 L {w:.2f} {h:.2f} L 0 {h:.2f} Z", False


def _custom_svg_path(cust_el: etree._Element, w: float, h: float) -> tuple[str, bool]:
    pl = cust_el.find(f"{A}pathLst")
    if pl is None:
        return f"M 0 0 L {w:.2f} 0 L {w:.2f} {h:.2f} L 0 {h:.2f} Z", False
    cmds: list[str] = []
    closed = False
    for path_el in pl.findall(f"{A}path"):
        pw = float(path_el.get("w") or w) or 1.0
        ph = float(path_el.get("h") or h) or 1.0
        sx, sy = w / pw, h / ph
        cx, cy = 0.0, 0.0
        for op in path_el:
            ln = etree.QName(op).localname
            if ln == "moveTo":
                pt = op.find(f"{A}pt")
                if pt is not None:
                    cx, cy = float(pt.get("x", 0)) * sx, float(pt.get("y", 0)) * sy
                    cmds.append(f"M {cx:.2f} {cy:.2f}")
            elif ln == "lnTo":
                pt = op.find(f"{A}pt")
                if pt is not None:
                    cx, cy = float(pt.get("x", 0)) * sx, float(pt.get("y", 0)) * sy
                    cmds.append(f"L {cx:.2f} {cy:.2f}")
            elif ln == "cubicBezTo":
                pts = op.findall(f"{A}pt")
                if len(pts) == 3:
                    coords = [(float(p.get("x", 0)) * sx, float(p.get("y", 0)) * sy) for p in pts]
                    cx, cy = coords[2]
                    cmds.append(
                        f"C {coords[0][0]:.2f} {coords[0][1]:.2f} "
                        f"{coords[1][0]:.2f} {coords[1][1]:.2f} {cx:.2f} {cy:.2f}"
                    )
            elif ln == "quadBezTo":
                pts = op.findall(f"{A}pt")
                if len(pts) == 2:
                    coords = [(float(p.get("x", 0)) * sx, float(p.get("y", 0)) * sy) for p in pts]
                    cx, cy = coords[1]
                    cmds.append(f"Q {coords[0][0]:.2f} {coords[0][1]:.2f} {cx:.2f} {cy:.2f}")
            elif ln == "arcTo":
                rx = float(op.get("wR", 0)) * sx
                ry = float(op.get("hR", 0)) * sy
                st = math.radians(float(op.get("stAng", 0)) / 60000.0)
                sw = math.radians(float(op.get("swAng", 0)) / 60000.0)
                end_ang = st + sw
                ex = cx + rx * (math.cos(end_ang) - math.cos(st))
                ey = cy + ry * (math.sin(end_ang) - math.sin(st))
                large = 1 if abs(sw) > math.pi else 0
                sweep = 1 if sw >= 0 else 0
                cmds.append(f"A {abs(rx):.2f} {abs(ry):.2f} 0 {large} {sweep} {ex:.2f} {ey:.2f}")
                cx, cy = ex, ey
            elif ln == "close":
                cmds.append("Z")
                closed = True
    return (" ".join(cmds) if cmds else f"M 0 0 L {w:.2f} 0 L {w:.2f} {h:.2f} L 0 {h:.2f} Z"), not closed


# ---- Render Context & Document Renderer ---------------------------------------------------------

class _Renderer:
    def __init__(self, pkg: _Package, extra_fonts: tuple[str, ...]):
        self.pkg = pkg
        self.extra_fonts = extra_fonts
        self._id_seq = 0
        self.defs: list[str] = []

    def next_id(self, prefix: str) -> str:
        self._id_seq += 1
        return f"{prefix}_{self._id_seq}"

    def image_data_uri(self, part: str, crop: tuple[float, float, float, float] = (0, 0, 0, 0), alpha: float = 1.0) -> str | None:
        if not self.pkg.exists(part):
            return None
        raw = self.pkg.read_bytes(part)
        ext = pathlib.Path(part).suffix.lower()
        if ext == ".svg":
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:image/svg+xml;base64,{b64}"
        try:
            im = Image.open(io.BytesIO(raw))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            l, t, r, b = crop
            if l or t or r or b:
                w, h = im.size
                x0 = int(round(w * _clamp(l, 0, 0.98)))
                y0 = int(round(h * _clamp(t, 0, 0.98)))
                x1 = max(x0 + 1, int(round(w * (1.0 - _clamp(r, 0, 0.98)))))
                y1 = max(y0 + 1, int(round(h * (1.0 - _clamp(b, 0, 0.98)))))
                im = im.crop((x0, y0, x1, y1))
            if alpha < 0.999:
                im = im.convert("RGBA")
                r_ch, g_ch, b_ch, a_ch = im.split()
                a_ch = a_ch.point(lambda p: int(round(p * alpha)))
                im = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))
            buf = io.BytesIO()
            fmt = "PNG" if im.mode == "RGBA" else "JPEG"
            mime = "image/png" if fmt == "PNG" else "image/jpeg"
            im.save(buf, format=fmt, quality=92)
            return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
        except Exception:
            return None

    def resolve_fill_attr(
        self,
        container: etree._Element | None,
        theme: _Theme,
        part_path: str,
        ph_clr: Color | None = None,
        default_fill: str = "none",
    ) -> tuple[str, float]:
        if container is None:
            return default_fill, 1.0
        if container.find(f"{A}noFill") is not None:
            return "none", 1.0
        sf = container.find(f"{A}solidFill")
        if sf is not None:
            c = theme.resolve_color(sf, ph_clr)
            if c is not None:
                return c.hex, c.alpha
            return "none", 1.0
        gf = container.find(f"{A}gradFill")
        if gf is not None:
            gs_lst = gf.find(f"{A}gsLst")
            stops = []
            if gs_lst is not None:
                for gs in gs_lst.findall(f"{A}gs"):
                    pos = _clamp(int(gs.get("pos", 0)) / 100000.0)
                    c = theme.resolve_color(gs, ph_clr) or Color((128, 128, 128))
                    stops.append((pos, c))
            stops.sort(key=lambda x: x[0])
            if stops:
                gid = self.next_id("grad")
                lin = gf.find(f"{A}lin")
                path_el = gf.find(f"{A}path")
                stop_tags = "".join(
                    f'<stop offset="{pos * 100:.1f}%" stop-color="{c.hex}" stop-opacity="{c.alpha:.3f}"/>'
                    for pos, c in stops
                )
                if path_el is not None:
                    self.defs.append(f'<radialGradient id="{gid}" cx="50%" cy="50%" r="55%">{stop_tags}</radialGradient>')
                else:
                    ang_deg = (int(lin.get("ang", 0)) / 60000.0) if lin is not None and lin.get("ang") else 0.0
                    rad = math.radians(ang_deg)
                    dx, dy = math.cos(rad), math.sin(rad)
                    x1, y1 = 50 - dx * 50, 50 - dy * 50
                    x2, y2 = 50 + dx * 50, 50 + dy * 50
                    self.defs.append(
                        f'<linearGradient id="{gid}" x1="{x1:.1f}%" y1="{y1:.1f}%" x2="{x2:.1f}%" y2="{y2:.1f}%">{stop_tags}</linearGradient>'
                    )
                return f"url(#{gid})", 1.0
        bf = container.find(f"{A}blipFill")
        if bf is not None:
            blip = bf.find(f"{A}blip")
            rid = blip.get(f"{R}embed") if blip is not None else None
            target = self.pkg.rel_target(part_path, rid)
            if target:
                uri = self.image_data_uri(target)
                if uri:
                    pid = self.next_id("pat")
                    self.defs.append(
                        f'<pattern id="{pid}" patternUnits="objectBoundingBox" width="1" height="1">'
                        f'<image href="{uri}" width="1" height="1" preserveAspectRatio="none"/></pattern>'
                    )
                    return f"url(#{pid})", 1.0
        return default_fill, 1.0

    def resolve_line(
        self,
        ln_el: etree._Element | None,
        theme: _Theme,
        ph_clr: Color | None = None,
        style_ln_idx: int = 0,
    ) -> tuple[str, float, float, str, str, str]:
        """Return `(stroke_hex, stroke_opacity, stroke_width_pt, dasharray, head_marker, tail_marker)`."""
        base_el = ln_el
        if base_el is None and style_ln_idx > 0 and style_ln_idx <= len(theme.ln_styles):
            base_el = theme.ln_styles[style_ln_idx - 1]
        if base_el is None or base_el.find(f"{A}noFill") is not None:
            return "none", 1.0, 0.0, "", "", ""

        sf = base_el.find(f"{A}solidFill")
        clr = theme.resolve_color(sf, ph_clr) if sf is not None else ph_clr
        if clr is None:
            if style_ln_idx > 0 and style_ln_idx <= len(theme.ln_styles):
                st_ln = theme.ln_styles[style_ln_idx - 1]
                st_sf = st_ln.find(f"{A}solidFill")
                clr = theme.resolve_color(st_sf, ph_clr)
            if clr is None:
                return "none", 1.0, 0.0, "", "", ""

        w_pt = _emu_to_pt(base_el.get("w"), 1.0)
        if w_pt <= 0 and style_ln_idx > 0 and style_ln_idx <= len(theme.ln_styles):
            w_pt = _emu_to_pt(theme.ln_styles[style_ln_idx - 1].get("w"), 1.0)
        if w_pt <= 0:
            w_pt = 0.75

        dash = ""
        prst_dash = base_el.find(f"{A}prstDash")
        if prst_dash is not None:
            dv = prst_dash.get("val", "solid")
            if dv in ("dot", "sysDot"):
                dash = f"{w_pt:.1f},{w_pt*2:.1f}"
            elif dv in ("dash", "sysDash", "lgDash"):
                dash = f"{w_pt*4:.1f},{w_pt*2:.1f}"
            elif dv in ("dashDot", "lgDashDot"):
                dash = f"{w_pt*4:.1f},{w_pt*2:.1f},{w_pt:.1f},{w_pt*2:.1f}"

        head_m = self._arrow_marker(base_el.find(f"{A}headEnd"), clr)
        tail_m = self._arrow_marker(base_el.find(f"{A}tailEnd"), clr)
        return clr.hex, clr.alpha, w_pt, dash, head_m, tail_m

    def _arrow_marker(self, end_el: etree._Element | None, clr: Color) -> str:
        if end_el is None or end_el.get("type", "none") == "none":
            return ""
        mid = self.next_id("arr")
        self.defs.append(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="{clr.hex}" fill-opacity="{clr.alpha:.3f}"/></marker>'
        )
        return f"url(#{mid})"

    def resolve_shadow_filter(self, sp_pr: etree._Element | None, theme: _Theme) -> str:
        if sp_pr is None:
            return ""
        shdw = sp_pr.find(f"{A}effectLst/{A}outerShdw")
        if shdw is None:
            return ""
        blur = max(0.5, _emu_to_pt(shdw.get("blurRad"), 3.0) * 0.5)
        dist = _emu_to_pt(shdw.get("dist"), 2.0)
        ang = math.radians(int(shdw.get("dir", "2700000")) / 60000.0)
        dx, dy = dist * math.cos(ang), dist * math.sin(ang)
        clr = theme.resolve_color(shdw) or Color((0, 0, 0), 0.25)
        fid = self.next_id("shdw")
        self.defs.append(
            f'<filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%">'
            f'<feDropShadow dx="{dx:.2f}" dy="{dy:.2f}" stdDeviation="{blur:.2f}" '
            f'flood-color="{clr.hex}" flood-opacity="{clr.alpha:.3f}"/></filter>'
        )
        return f'filter="url(#{fid})"'


def _shape_placeholder_info(el: etree._Element) -> tuple[str | None, str | None]:
    for nv_tag in ("nvSpPr", "nvPicPr", "nvGraphicFramePr"):
        nv = el.find(f"{P}{nv_tag}")
        if nv is not None:
            ph = nv.find(f"{P}nvPr/{P}ph")
            if ph is not None:
                return ph.get("type"), ph.get("idx")
    return None, None


def _is_hidden(el: etree._Element) -> bool:
    for nv_tag in ("nvSpPr", "nvPicPr", "nvGraphicFramePr", "nvGrpSpPr", "nvCxnSpPr"):
        nv = el.find(f"{P}{nv_tag}")
        if nv is not None:
            cnv = nv.find(f"{P}cNvPr")
            if cnv is not None and cnv.get("hidden") in ("1", "true"):
                return True
    return False


def _index_placeholders(tree_parent: etree._Element | None) -> tuple[dict[str, etree._Element], dict[str, etree._Element]]:
    by_idx: dict[str, etree._Element] = {}
    by_type: dict[str, etree._Element] = {}
    if tree_parent is None:
        return by_idx, by_type
    sp_tree = tree_parent.find(f"{P}cSld/{P}spTree")
    if sp_tree is None:
        return by_idx, by_type
    for el in sp_tree:
        ptype, pidx = _shape_placeholder_info(el)
        if pidx is not None:
            by_idx[pidx] = el
        if ptype is not None:
            by_type[ptype] = el
    return by_idx, by_type


def _find_matching_placeholder(ptype: str | None, pidx: str | None, by_idx: dict[str, etree._Element], by_type: dict[str, etree._Element]) -> etree._Element | None:
    if pidx is not None and pidx in by_idx:
        return by_idx[pidx]
    if ptype is not None:
        if ptype in by_type:
            return by_type[ptype]
        alias = {"ctrTitle": "title", "subTitle": "body", "obj": "body"}.get(ptype)
        if alias and alias in by_type:
            return by_type[alias]
    return None


def _render_background(
    renderer: _Renderer,
    slide_root: etree._Element,
    layout_root: etree._Element | None,
    master_root: etree._Element | None,
    slide_part: str,
    layout_part: str | None,
    master_part: str | None,
    theme: _Theme,
    w_pt: float,
    h_pt: float,
) -> str:
    for root, part in ((slide_root, slide_part), (layout_root, layout_part), (master_root, master_part)):
        if root is None or part is None:
            continue
        bg = root.find(f"{P}cSld/{P}bg")
        if bg is None:
            continue
        bg_pr = bg.find(f"{P}bgPr")
        if bg_pr is not None:
            fill, op = renderer.resolve_fill_attr(bg_pr, theme, part, default_fill="#ffffff")
            if fill != "none":
                return f'<rect x="0" y="0" width="{w_pt:.2f}" height="{h_pt:.2f}" fill="{fill}" fill-opacity="{op:.3f}"/>'
        bg_ref = bg.find(f"{P}bgRef")
        if bg_ref is not None:
            idx = int(bg_ref.get("idx", "0"))
            ref_clr = theme.resolve_color(bg_ref)
            style_idx = idx - 1001 if idx >= 1001 else idx - 1
            if 0 <= style_idx < len(theme.bg_fill_styles):
                st_el = theme.bg_fill_styles[style_idx]
                tmp = etree.Element("bgPr")
                tmp.append(etree.fromstring(etree.tostring(st_el)))
                fill, op = renderer.resolve_fill_attr(tmp, theme, part, ph_clr=ref_clr, default_fill="none")
                if fill != "none":
                    return f'<rect x="0" y="0" width="{w_pt:.2f}" height="{h_pt:.2f}" fill="{fill}" fill-opacity="{op:.3f}"/>'
            if ref_clr is not None:
                return f'<rect x="0" y="0" width="{w_pt:.2f}" height="{h_pt:.2f}" fill="{ref_clr.hex}" fill-opacity="{ref_clr.alpha:.3f}"/>'
    return f'<rect x="0" y="0" width="{w_pt:.2f}" height="{h_pt:.2f}" fill="#ffffff"/>'


# ---- Charts & Tables & SmartArt -----------------------------------------------------------------

def _chart_cached_points(ser: etree._Element) -> tuple[str, list[str], list[float]]:
    name = ""
    tx_v = ser.find(f"{C}tx//{C}v")
    if tx_v is not None and tx_v.text:
        name = tx_v.text.strip()
    cats: list[str] = []
    cat_el = ser.find(f"{C}cat")
    if cat_el is not None:
        pts = sorted(cat_el.findall(f".//{C}pt"), key=lambda x: int(x.get("idx", 0)))
        cats = [(_p.findtext(f"{C}v") or "").strip() for _p in pts]
    vals: list[float] = []
    val_el = ser.find(f"{C}val")
    if val_el is not None:
        pts = sorted(val_el.findall(f".//{C}pt"), key=lambda x: int(x.get("idx", 0)))
        for _p in pts:
            try:
                vals.append(float(_p.findtext(f"{C}v") or 0.0))
            except ValueError:
                vals.append(0.0)
    return name, cats, vals


def _first_child(parent: etree._Element, *tags: str) -> etree._Element | None:
    for tag in tags:
        found = parent.find(tag)
        if found is not None:
            return found
    return None


def _render_chart(renderer: _Renderer, chart_part: str, xfrm: Xfrm, theme: _Theme) -> str:
    root = renderer.pkg.read_xml(chart_part)
    if root is None or xfrm.w <= 10 or xfrm.h <= 10:
        return ""
    chart_el = root.find(f"{C}chart")
    if chart_el is None:
        return ""

    out: list[str] = [
        f'<rect x="{xfrm.x:.2f}" y="{xfrm.y:.2f}" width="{xfrm.w:.2f}" height="{xfrm.h:.2f}" rx="4" fill="#ffffff" stroke="#e2e8f0" stroke-width="0.75"/>'
    ]
    title_texts = [t.text.strip() for t in chart_el.findall(f"{C}title//{A}t") if t.text and t.text.strip()]
    top_pad = 16.0
    if title_texts:
        out.append(
            f'<text x="{xfrm.x + xfrm.w/2:.2f}" y="{xfrm.y + 20:.2f}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#1e293b">{_esc(" ".join(title_texts))}</text>'
        )
        top_pad = 32.0

    plot = chart_el.find(f"{C}plotArea")
    if plot is None:
        return "\n".join(out)

    palette = [
        _rgb_to_hex(theme.colors.get(f"accent{k}", DEFAULT_SCHEME_COLORS[f"accent{k}"]))
        for k in range(1, 7)
    ]

    pie_el = _first_child(plot, f"{C}pieChart", f"{C}doughnutChart")
    if pie_el is not None:
        ser = pie_el.find(f"{C}ser")
        if ser is not None:
            _name, cats, vals = _chart_cached_points(ser)
            total = sum(max(0.0, v) for v in vals) or 1.0
            cx = xfrm.x + xfrm.w * 0.38
            cy = xfrm.y + top_pad + (xfrm.h - top_pad - 12) / 2.0
            rad = max(12.0, min(xfrm.w * 0.28, (xfrm.h - top_pad - 20) * 0.44))
            hole = rad * 0.48 if etree.QName(pie_el).localname == "doughnutChart" else 0.0
            ang = -math.pi / 2.0
            for idx, v in enumerate(vals):
                frac = max(0.0, v) / total
                if frac <= 0:
                    continue
                clr = palette[idx % len(palette)]
                sweep = frac * 2.0 * math.pi
                if frac >= 0.999:
                    out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rad:.2f}" fill="{clr}"/>')
                else:
                    x1, y1 = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
                    x2, y2 = cx + rad * math.cos(ang + sweep), cy + rad * math.sin(ang + sweep)
                    large = 1 if sweep > math.pi else 0
                    out.append(
                        f'<path d="M {cx:.2f} {cy:.2f} L {x1:.2f} {y1:.2f} A {rad:.2f} {rad:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} Z" '
                        f'fill="{clr}" stroke="#ffffff" stroke-width="1"/>'
                    )
                ang += sweep
            if hole > 0:
                out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{hole:.2f}" fill="#ffffff"/>')
            lx = xfrm.x + xfrm.w * 0.68
            for idx, cat in enumerate(cats[:8]):
                ly = xfrm.y + top_pad + 18 + idx * 18
                clr = palette[idx % len(palette)]
                out.append(f'<rect x="{lx:.2f}" y="{ly - 9:.2f}" width="10" height="10" rx="2" fill="{clr}"/>')
                out.append(
                    f'<text x="{lx + 15:.2f}" y="{ly:.2f}" font-family="Arial, sans-serif" font-size="10" fill="#334155">'
                    f'{_esc(cat)}</text>'
                )
        return "\n".join(out)

    series_parent = _first_child(plot, f"{C}barChart", f"{C}lineChart", f"{C}areaChart")
    if series_parent is None:
        return "\n".join(out)

    kind = etree.QName(series_parent).localname
    all_ser = series_parent.findall(f"{C}ser")
    parsed_ser: list[tuple[str, list[str], list[float], str]] = []
    cats: list[str] = []
    max_val = 1.0
    for idx, ser in enumerate(all_ser):
        sname, scats, svals = _chart_cached_points(ser)
        if scats and not cats:
            cats = scats
        if svals:
            max_val = max(max_val, max(svals))
        sp_pr = ser.find(f"{C}spPr")
        clr, _op = renderer.resolve_fill_attr(sp_pr, theme, chart_part, default_fill="none")
        if clr == "none" or not clr.startswith("#"):
            clr = palette[idx % len(palette)]
        parsed_ser.append((sname or f"Series {idx+1}", scats, svals, clr))

    n_cats = max(len(cats), max((len(s[2]) for s in parsed_ser), default=0))
    if n_cats == 0:
        return "\n".join(out)

    px0 = xfrm.x + 42
    py0 = xfrm.y + top_pad + 8
    pw = max(20.0, xfrm.w - 60)
    ph = max(20.0, xfrm.h - top_pad - 48)

    # Gridlines
    for tick in range(5):
        frac = tick / 4.0
        gy = py0 + ph * (1.0 - frac)
        val_lbl = max_val * frac
        out.append(f'<line x1="{px0:.2f}" y1="{gy:.2f}" x2="{px0 + pw:.2f}" y2="{gy:.2f}" stroke="#e2e8f0" stroke-width="0.75"/>')
        out.append(
            f'<text x="{px0 - 5:.2f}" y="{gy + 3:.2f}" text-anchor="end" font-family="Arial, sans-serif" font-size="9" fill="#64748b">'
            f'{val_lbl:.0f}</text>'
        )

    slot_w = pw / n_cats
    if kind == "barChart":
        ns = max(1, len(parsed_ser))
        bar_w = max(4.0, (slot_w * 0.7) / ns)
        for ci in range(n_cats):
            base_x = px0 + ci * slot_w + slot_w * 0.15
            for si, (_sn, _sc, svals, clr) in enumerate(parsed_ser):
                v = svals[ci] if ci < len(svals) else 0.0
                bh = (max(0.0, v) / max_val) * ph
                bx = base_x + si * bar_w
                by = py0 + ph - bh
                out.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bar_w - 1:.2f}" height="{bh:.2f}" rx="1.5" fill="{clr}"/>')
    else:
        for _sn, _sc, svals, clr in parsed_ser:
            pts = []
            for ci in range(min(n_cats, len(svals))):
                cx = px0 + (ci + 0.5) * slot_w
                cy = py0 + ph - (max(0.0, svals[ci]) / max_val) * ph
                pts.append((cx, cy))
            if pts:
                if kind == "areaChart":
                    area_pts = [(pts[0][0], py0 + ph), *pts, (pts[-1][0], py0 + ph)]
                    out.append(f'<path d="{_pts_path(area_pts)}" fill="{clr}" fill-opacity="0.25"/>')
                out.append(f'<path d="{_pts_path(pts, close=False)}" fill="none" stroke="{clr}" stroke-width="2.2"/>')
                for cx, cy in pts:
                    out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="3" fill="{clr}"/>')

    for ci, cat in enumerate(cats[:n_cats]):
        lx = px0 + (ci + 0.5) * slot_w
        out.append(
            f'<text x="{lx:.2f}" y="{py0 + ph + 14:.2f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="9.5" fill="#475569">'
            f'{_esc(cat)}</text>'
        )

    if len(parsed_ser) > 1:
        lx = px0
        ly = xfrm.y + xfrm.h - 10
        for sname, _sc, _sv, clr in parsed_ser:
            out.append(f'<rect x="{lx:.2f}" y="{ly - 8:.2f}" width="8" height="8" rx="1.5" fill="{clr}"/>')
            out.append(
                f'<text x="{lx + 11:.2f}" y="{ly:.2f}" font-family="Arial, sans-serif" font-size="9" fill="#334155">{_esc(sname)}</text>'
            )
            lx += max(56.0, len(sname) * 5.8 + 20.0)
    return "\n".join(out)


def _find_table_style(pkg: _Package, style_id: str | None) -> etree._Element | None:
    if not style_id:
        return None
    ts_root = pkg.read_xml("ppt/tableStyles.xml")
    if ts_root is None:
        return None
    for st in ts_root.findall(f"{A}tblStyle"):
        if st.get("styleId", "").upper() == style_id.upper():
            return st
    return None


def _table_section_style(tbl_style: etree._Element | None, sec_name: str, theme: _Theme) -> tuple[str | None, Color | None, bool, dict[str, tuple[str, float]]]:
    if tbl_style is None:
        return None, None, False, {}
    sec = tbl_style.find(f"{A}{sec_name}")
    if sec is None:
        return None, None, False, {}
    fill_hex: str | None = None
    tc_style = sec.find(f"{A}tcStyle")
    borders: dict[str, tuple[str, float]] = {}
    if tc_style is not None:
        sf = tc_style.find(f"{A}fill/{A}solidFill")
        if sf is not None:
            c = theme.resolve_color(sf)
            if c:
                fill_hex = c.hex
        tc_bdr = tc_style.find(f"{A}tcBdr")
        if tc_bdr is not None:
            for side in ("left", "right", "top", "bottom", "insideH", "insideV"):
                ln = tc_bdr.find(f"{A}{side}/{A}ln")
                if ln is not None and ln.find(f"{A}noFill") is None:
                    bclr = theme.resolve_color(ln.find(f"{A}solidFill"))
                    if bclr:
                        borders[side] = (bclr.hex, max(0.5, _emu_to_pt(ln.get("w"), 1.0)))

    txt_clr: Color | None = None
    bold = False
    tx_st = sec.find(f"{A}tcTxStyle")
    if tx_st is not None:
        bold = tx_st.get("b") == "on"
        c = theme.resolve_color(tx_st)
        if c:
            txt_clr = c
    return fill_hex, txt_clr, bold, borders


def _render_table(renderer: _Renderer, tbl: etree._Element, xfrm: Xfrm, part_path: str, theme: _Theme, slide_num: int) -> str:
    cols = [_emu_to_pt(gc.get("w")) for gc in tbl.findall(f"{A}tblGrid/{A}gridCol")]
    if not cols:
        return ""
    total_cw = sum(cols)
    if total_cw <= 1.0 and xfrm.w > 1.0:
        cols = [xfrm.w / len(cols)] * len(cols)

    rows = tbl.findall(f"{A}tr")
    if not rows:
        return ""
    row_hs = [max(16.0, _emu_to_pt(r.get("h"), 20.0)) for r in rows]

    tbl_pr = tbl.find(f"{A}tblPr")
    first_row = tbl_pr is not None and tbl_pr.get("firstRow") in ("1", "true")
    band_row = tbl_pr is not None and tbl_pr.get("bandRow") in ("1", "true")
    style_id = tbl_pr.findtext(f"{A}tableStyleId") if tbl_pr is not None else None
    tbl_style = _find_table_style(renderer.pkg, style_id)

    whole_fill, whole_tx, _, whole_bdr = _table_section_style(tbl_style, "wholeTbl", theme)
    first_fill, first_tx, first_bold, first_bdr = _table_section_style(tbl_style, "firstRow", theme)
    b1_fill, _, _, _ = _table_section_style(tbl_style, "band1H", theme)
    b2_fill, _, _, _ = _table_section_style(tbl_style, "band2H", theme)

    col_xs = [xfrm.x]
    for cw in cols:
        col_xs.append(col_xs[-1] + cw)
    row_ys = [xfrm.y]
    for rh in row_hs:
        row_ys.append(row_ys[-1] + rh)

    out: list[str] = []
    n_rows = len(rows)
    n_cols = len(cols)
    for ri, tr in enumerate(rows):
        cells = tr.findall(f"{A}tc")
        for ci, tc in enumerate(cells):
            if ci >= n_cols:
                break
            if tc.get("hMerge") in ("1", "true") or tc.get("vMerge") in ("1", "true"):
                continue
            gspan = max(1, int(tc.get("gridSpan", "1")))
            rspan = max(1, int(tc.get("rowSpan", "1")))
            cx = col_xs[ci]
            cy = row_ys[ri]
            cw = col_xs[min(n_cols, ci + gspan)] - cx
            ch = row_ys[min(n_rows, ri + rspan)] - cy

            tc_pr = tc.find(f"{A}tcPr")
            fill_hex, fill_op = renderer.resolve_fill_attr(tc_pr, theme, part_path, default_fill="none")
            def_txt_clr = whole_tx
            def_bold: bool | None = None
            if fill_hex == "none":
                if first_row and ri == 0 and first_fill:
                    fill_hex = first_fill
                    def_txt_clr = first_tx or Color((255, 255, 255))
                    def_bold = first_bold
                elif band_row and (ri > 0 or not first_row):
                    idx_b = ri - (1 if first_row else 0)
                    fill_hex = (b1_fill if idx_b % 2 == 0 else b2_fill) or whole_fill or "none"
                elif whole_fill:
                    fill_hex = whole_fill

            if fill_hex != "none":
                out.append(f'<rect x="{cx:.2f}" y="{cy:.2f}" width="{cw:.2f}" height="{ch:.2f}" fill="{fill_hex}" fill-opacity="{fill_op:.3f}"/>')

            # Cell text
            tx_body = tc.find(f"{A}txBody")
            insets = (5.4, 5.4, 3.6, 3.6)
            anchor = "ctr"
            if tc_pr is not None:
                insets = (
                    _emu_to_pt(tc_pr.get("marL"), 5.4),
                    _emu_to_pt(tc_pr.get("marR"), 5.4),
                    _emu_to_pt(tc_pr.get("marT"), 3.6),
                    _emu_to_pt(tc_pr.get("marB"), 3.6),
                )
                anchor = tc_pr.get("anchor", "ctr")
            out.append(
                _render_tx_body(
                    tx_body,
                    Xfrm(x=cx, y=cy, w=cw, h=ch),
                    [],
                    theme,
                    None,
                    slide_num,
                    renderer.extra_fonts,
                    default_size_pt=12.0,
                    default_color=def_txt_clr,
                    default_bold=def_bold,
                    default_anchor=anchor,
                    default_insets=insets,
                )
            )

            # Borders
            sides = [
                ("lnL", "left", cx, cy, cx, cy + ch),
                ("lnR", "right", cx + cw, cy, cx + cw, cy + ch),
                ("lnT", "top", cx, cy, cx + cw, cy),
                ("lnB", "bottom", cx, cy + ch, cx + cw, cy + ch),
            ]
            for tag, bkey, x1, y1, x2, y2 in sides:
                ln = tc_pr.find(f"{A}{tag}") if tc_pr is not None else None
                if ln is not None and ln.find(f"{A}noFill") is None:
                    sc, sop, sw, _, _, _ = renderer.resolve_line(ln, theme)
                    if sc != "none" and sw > 0:
                        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{sc}" stroke-opacity="{sop:.3f}" stroke-width="{sw:.2f}"/>')
                elif ln is None:
                    b_spec = (first_bdr.get(bkey) if (first_row and ri == 0) else None) or whole_bdr.get(bkey) or whole_bdr.get("insideH" if bkey in ("top", "bottom") else "insideV")
                    if b_spec:
                        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{b_spec[0]}" stroke-width="{b_spec[1]:.2f}"/>')
                    else:
                        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#d0d7de" stroke-width="0.5"/>')

    return "\n".join(part for part in out if part)


def _render_smartart_drawing(renderer: _Renderer, drawing_part: str, xfrm: Xfrm, theme: _Theme, slide_num: int) -> str:
    root = renderer.pkg.read_xml(drawing_part)
    if root is None:
        return ""
    sp_tree = root.find(f"{DSP}spTree")
    if sp_tree is None:
        return ""
    shapes = sp_tree.findall(f"{DSP}sp")
    if not shapes:
        return ""
    # Compute bounding box of drawing shapes so we place them cleanly inside graphicFrame
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = 0.0, 0.0
    for sp in shapes:
        sp_pr = sp.find(f"{DSP}spPr")
        sx = _parse_xfrm(sp_pr.find(f"{A}xfrm") if sp_pr is not None else None)
        if sx.w > 0 and sx.h > 0:
            min_x = min(min_x, sx.x)
            min_y = min(min_y, sx.y)
            max_x = max(max_x, sx.x + sx.w)
            max_y = max(max_y, sx.y + sx.h)
    bw = max(1.0, max_x - min_x) if min_x < float("inf") else xfrm.w
    bh = max(1.0, max_y - min_y) if min_y < float("inf") else xfrm.h
    sx_scale = (xfrm.w / bw) if xfrm.w > 1 else 1.0
    sy_scale = (xfrm.h / bh) if xfrm.h > 1 else 1.0
    ox = min_x if min_x < float("inf") else 0.0
    oy = min_y if min_y < float("inf") else 0.0

    inner = "\n".join(_render_shape(renderer, sp, drawing_part, theme, slide_num, ns_prefix=DSP) for sp in shapes)
    return f'<g transform="translate({xfrm.x:.2f},{xfrm.y:.2f}) scale({sx_scale:.4f},{sy_scale:.4f}) translate({-ox:.2f},{-oy:.2f})">{inner}</g>'


# ---- Element Renderers --------------------------------------------------------------------------

def _render_shape(
    renderer: _Renderer,
    sp: etree._Element,
    part_path: str,
    theme: _Theme,
    slide_num: int,
    *,
    ns_prefix: str = P,
    ph_match_layout: etree._Element | None = None,
    ph_match_master: etree._Element | None = None,
    inherited_lst_styles: list[etree._Element | None] | None = None,
) -> str:
    if _is_hidden(sp):
        return ""
    sp_pr = sp.find(f"{ns_prefix}spPr")
    xfrm = _parse_xfrm(sp_pr.find(f"{A}xfrm") if sp_pr is not None else None)
    for fallback_ph in (ph_match_layout, ph_match_master):
        if fallback_ph is not None and (not xfrm.has_pos or not xfrm.has_ext):
            f_sp_pr = fallback_ph.find(f"{P}spPr")
            xfrm = _merge_xfrm(xfrm, _parse_xfrm(f_sp_pr.find(f"{A}xfrm") if f_sp_pr is not None else None))

    if xfrm.w <= 0 and xfrm.h <= 0:
        return ""

    is_cxn = etree.QName(sp).localname == "cxnSp"
    geom_prst = "straightConnector1" if is_cxn else "rect"
    av: dict[str, int] = {}
    cust_geom: etree._Element | None = None
    for cand_pr in (
        sp_pr,
        ph_match_layout.find(f"{P}spPr") if ph_match_layout is not None else None,
        ph_match_master.find(f"{P}spPr") if ph_match_master is not None else None,
    ):
        if cand_pr is None:
            continue
        pg = cand_pr.find(f"{A}prstGeom")
        cg = cand_pr.find(f"{A}custGeom")
        if pg is not None:
            geom_prst = pg.get("prst", geom_prst)
            av = _geom_av_map(pg)
            break
        if cg is not None:
            cust_geom = cg
            break

    # Style references (`<p:style>` `fillRef` / `lnRef` / `fontRef`)
    style_el = sp.find(f"{ns_prefix}style")
    fill_ref_clr: Color | None = None
    ln_ref_clr: Color | None = None
    ln_ref_idx = 0
    font_ref_clr: Color | None = None
    if style_el is not None:
        fr = style_el.find(f"{A}fillRef")
        if fr is not None and fr.get("idx", "0") != "0":
            fill_ref_clr = theme.resolve_color(fr)
        lr = style_el.find(f"{A}lnRef")
        if lr is not None and lr.get("idx", "0") != "0":
            ln_ref_idx = int(lr.get("idx", "0"))
            ln_ref_clr = theme.resolve_color(lr)
        fnr = style_el.find(f"{A}fontRef")
        if fnr is not None:
            font_ref_clr = theme.resolve_color(fnr)

    fill_attr, fill_op = renderer.resolve_fill_attr(sp_pr, theme, part_path, default_fill="none")
    if fill_attr == "none" and sp_pr is not None and sp_pr.find(f"{A}noFill") is None and fill_ref_clr is not None and not is_cxn:
        fill_attr, fill_op = fill_ref_clr.hex, fill_ref_clr.alpha

    ln_el = sp_pr.find(f"{A}ln") if sp_pr is not None else None
    sc, sop, sw, dash, head_m, tail_m = renderer.resolve_line(ln_el, theme, ln_ref_clr, ln_ref_idx)

    tx_body = sp.find(f"{ns_prefix}txBody")
    ls_chain = list(inherited_lst_styles or [])
    for ph in (ph_match_master, ph_match_layout):
        if ph is not None:
            ls_chain.append(ph.find(f"{P}txBody/{A}lstStyle"))

    text_svg = _render_tx_body(tx_body, xfrm, ls_chain, theme, font_ref_clr, slide_num, renderer.extra_fonts)
    if fill_attr == "none" and sc == "none" and not text_svg:
        return ""

    if cust_geom is not None:
        path_d, is_line = _custom_svg_path(cust_geom, max(0.5, xfrm.w), max(0.5, xfrm.h))
    else:
        path_d, is_line = _preset_svg_path(geom_prst, max(0.5, xfrm.w) if is_cxn and xfrm.w == 0 else xfrm.w, max(0.5, xfrm.h) if is_cxn and xfrm.h == 0 else xfrm.h, av)

    if is_line or is_cxn:
        fill_attr = "none"

    geom_transforms = [f"translate({xfrm.x:.2f},{xfrm.y:.2f})"]
    if xfrm.flip_h or xfrm.flip_v:
        sx = -1 if xfrm.flip_h else 1
        sy = -1 if xfrm.flip_v else 1
        tx = xfrm.w if xfrm.flip_h else 0.0
        ty = xfrm.h if xfrm.flip_v else 0.0
        geom_transforms.append(f"translate({tx:.2f},{ty:.2f}) scale({sx},{sy})")

    shdw_attr = renderer.resolve_shadow_filter(sp_pr, theme)
    shape_attrs = [
        f'd="{path_d}"',
        f'fill="{fill_attr}"',
    ]
    if fill_attr != "none" and fill_op < 0.999:
        shape_attrs.append(f'fill-opacity="{fill_op:.3f}"')
    if geom_prst in ("donut", "blockArc"):
        shape_attrs.append('fill-rule="evenodd"')
    if sc != "none" and sw > 0:
        shape_attrs.append(f'stroke="{sc}"')
        if sop < 0.999:
            shape_attrs.append(f'stroke-opacity="{sop:.3f}"')
        shape_attrs.append(f'stroke-width="{sw:.2f}"')
        if dash:
            shape_attrs.append(f'stroke-dasharray="{dash}"')
        if head_m:
            shape_attrs.append(f'marker-start="{head_m}"')
        if tail_m:
            shape_attrs.append(f'marker-end="{tail_m}"')
    if shdw_attr:
        shape_attrs.append(shdw_attr)

    geom_svg = f'<path transform="{" ".join(geom_transforms)}" {" ".join(shape_attrs)}/>' if (fill_attr != "none" or (sc != "none" and sw > 0)) else ""
    combined = f"{geom_svg}\n{text_svg}".strip()
    if xfrm.rot:
        cx, cy = xfrm.x + xfrm.w / 2.0, xfrm.y + xfrm.h / 2.0
        return f'<g transform="rotate({xfrm.rot:.3f} {cx:.2f} {cy:.2f})">{combined}</g>'
    return combined


def _render_picture(renderer: _Renderer, pic: etree._Element, part_path: str, theme: _Theme, ph_match_layout: etree._Element | None, ph_match_master: etree._Element | None) -> str:
    if _is_hidden(pic):
        return ""
    sp_pr = pic.find(f"{P}spPr")
    xfrm = _parse_xfrm(sp_pr.find(f"{A}xfrm") if sp_pr is not None else None)
    for fallback_ph in (ph_match_layout, ph_match_master):
        if fallback_ph is not None and (not xfrm.has_pos or not xfrm.has_ext):
            f_sp_pr = fallback_ph.find(f"{P}spPr")
            xfrm = _merge_xfrm(xfrm, _parse_xfrm(f_sp_pr.find(f"{A}xfrm") if f_sp_pr is not None else None))
    if xfrm.w <= 0 or xfrm.h <= 0:
        return ""

    bf = pic.find(f"{P}blipFill")
    if bf is None:
        return ""
    blip = bf.find(f"{A}blip")
    if blip is None:
        return ""

    svg_blip = blip.find(f".//{ASVG}svgBlip")
    rid = (svg_blip.get(f"{R}embed") if svg_blip is not None else None) or blip.get(f"{R}embed")
    target = renderer.pkg.rel_target(part_path, rid)
    if not target:
        return ""

    src_rect = bf.find(f"{A}srcRect")
    crop = (
        int(src_rect.get("l", 0)) / 100000.0,
        int(src_rect.get("t", 0)) / 100000.0,
        int(src_rect.get("r", 0)) / 100000.0,
        int(src_rect.get("b", 0)) / 100000.0,
    ) if src_rect is not None else (0.0, 0.0, 0.0, 0.0)
    alpha_el = blip.find(f"{A}alphaModFix")
    alpha = _clamp(int(alpha_el.get("amt", 100000)) / 100000.0) if alpha_el is not None else 1.0
    uri = renderer.image_data_uri(target, crop=crop, alpha=alpha)
    if not uri:
        return ""

    pg = sp_pr.find(f"{A}prstGeom") if sp_pr is not None else None
    prst = pg.get("prst", "rect") if pg is not None else "rect"
    clip_attr = ""
    if prst != "rect":
        path_d, _ = _preset_svg_path(prst, xfrm.w, xfrm.h, _geom_av_map(pg))
        cid = renderer.next_id("clip")
        renderer.defs.append(f'<clipPath id="{cid}"><path transform="translate({xfrm.x:.2f},{xfrm.y:.2f})" d="{path_d}"/></clipPath>')
        clip_attr = f' clip-path="url(#{cid})"'

    img_svg = f'<image x="{xfrm.x:.2f}" y="{xfrm.y:.2f}" width="{xfrm.w:.2f}" height="{xfrm.h:.2f}" href="{uri}" preserveAspectRatio="none"{clip_attr}/>'
    ln_el = sp_pr.find(f"{A}ln") if sp_pr is not None else None
    sc, sop, sw, dash, _, _ = renderer.resolve_line(ln_el, theme)
    if sc != "none" and sw > 0:
        path_d, _ = _preset_svg_path(prst, xfrm.w, xfrm.h, _geom_av_map(pg))
        img_svg += f'\n<path transform="translate({xfrm.x:.2f},{xfrm.y:.2f})" d="{path_d}" fill="none" stroke="{sc}" stroke-opacity="{sop:.3f}" stroke-width="{sw:.2f}"/>'

    if xfrm.rot:
        cx, cy = xfrm.x + xfrm.w / 2.0, xfrm.y + xfrm.h / 2.0
        return f'<g transform="rotate({xfrm.rot:.3f} {cx:.2f} {cy:.2f})">{img_svg}</g>'
    return img_svg


def _render_graphic_frame(renderer: _Renderer, gf: etree._Element, part_path: str, theme: _Theme, slide_num: int) -> str:
    if _is_hidden(gf):
        return ""
    xfrm_el = gf.find(f"{P}xfrm")
    if xfrm_el is None:
        xfrm_el = gf.find(f"{A}xfrm")
    xfrm = _parse_xfrm(xfrm_el)
    if xfrm.w <= 0 and xfrm.h <= 0:
        return ""

    graphic = gf.find(f"{A}graphic/{A}graphicData")
    if graphic is None:
        return ""
    tbl = graphic.find(f"{A}tbl")
    if tbl is not None:
        return _render_table(renderer, tbl, xfrm, part_path, theme, slide_num)
    chart_ref = graphic.find(f"{C}chart")
    if chart_ref is not None:
        c_part = renderer.pkg.rel_target(part_path, chart_ref.get(f"{R}id"))
        if c_part:
            return _render_chart(renderer, c_part, xfrm, theme)
    dgm_rels = graphic.find(f"{DGM}relIds")
    if dgm_rels is not None:
        dm_part = renderer.pkg.rel_target(part_path, dgm_rels.get(f"{R}dm"))
        drawing_part: str | None = None
        if dm_part:
            dm_xml = renderer.pkg.read_xml(dm_part)
            if dm_xml is not None:
                ext_el = dm_xml.find(f".//{DSP}dataModelExt")
                if ext_el is not None and ext_el.get("relId"):
                    drawing_part = renderer.pkg.rel_target(part_path, ext_el.get("relId"))
        if not drawing_part:
            drawing_part = renderer.pkg.first_rel_by_type_suffix(part_path, "diagramDrawing")
        if drawing_part:
            return _render_smartart_drawing(renderer, drawing_part, xfrm, theme, slide_num)
    return ""


def _render_group(
    renderer: _Renderer,
    grp: etree._Element,
    part_path: str,
    theme: _Theme,
    slide_num: int,
) -> str:
    if _is_hidden(grp):
        return ""
    grp_sp_pr = grp.find(f"{P}grpSpPr")
    xfrm = _parse_xfrm(grp_sp_pr.find(f"{A}xfrm") if grp_sp_pr is not None else None)
    cw = xfrm.ch_w or xfrm.w or 1.0
    ch = xfrm.ch_h or xfrm.h or 1.0
    sx = (xfrm.w / cw) if xfrm.w > 0 else 1.0
    sy = (xfrm.h / ch) if xfrm.h > 0 else 1.0

    children_svg = _render_sp_tree_children(renderer, grp, part_path, theme, slide_num)
    if not children_svg:
        return ""
    transforms = []
    if xfrm.rot:
        cx, cy = xfrm.x + xfrm.w / 2.0, xfrm.y + xfrm.h / 2.0
        transforms.append(f"rotate({xfrm.rot:.3f} {cx:.2f} {cy:.2f})")
    transforms.append(f"translate({xfrm.x:.2f},{xfrm.y:.2f})")
    transforms.append(f"scale({sx:.5f},{sy:.5f})")
    transforms.append(f"translate({-xfrm.ch_x:.2f},{-xfrm.ch_y:.2f})")
    return f'<g transform="{" ".join(transforms)}">\n{children_svg}\n</g>'


def _render_sp_tree_children(
    renderer: _Renderer,
    parent: etree._Element,
    part_path: str,
    theme: _Theme,
    slide_num: int,
    *,
    skip_placeholders: bool = False,
    layout_ph: tuple[dict[str, etree._Element], dict[str, etree._Element]] | None = None,
    master_ph: tuple[dict[str, etree._Element], dict[str, etree._Element]] | None = None,
    tx_styles: dict[str, etree._Element | None] | None = None,
    default_text_style: etree._Element | None = None,
) -> str:
    parts: list[str] = []
    l_idx, l_type = layout_ph or ({}, {})
    m_idx, m_type = master_ph or ({}, {})

    for child in parent:
        ln = etree.QName(child).localname
        if ln not in ("sp", "cxnSp", "pic", "grpSp", "graphicFrame"):
            continue
        ptype, pidx = _shape_placeholder_info(child)
        if skip_placeholders and (ptype is not None or pidx is not None):
            continue

        ph_l = _find_matching_placeholder(ptype, pidx, l_idx, l_type) if (ptype or pidx) else None
        ph_m = _find_matching_placeholder(ptype, pidx, m_idx, m_type) if (ptype or pidx) else None
        lst_styles: list[etree._Element | None] = [default_text_style]
        if tx_styles and (ptype or pidx):
            if ptype in ("title", "ctrTitle"):
                lst_styles.append(tx_styles.get("titleStyle"))
            elif ptype in ("body", "subTitle", "obj"):
                lst_styles.append(tx_styles.get("bodyStyle"))
            else:
                lst_styles.append(tx_styles.get("otherStyle"))

        if ln in ("sp", "cxnSp"):
            s = _render_shape(
                renderer, child, part_path, theme, slide_num,
                ph_match_layout=ph_l, ph_match_master=ph_m, inherited_lst_styles=lst_styles,
            )
        elif ln == "pic":
            s = _render_picture(renderer, child, part_path, theme, ph_l, ph_m)
        elif ln == "graphicFrame":
            s = _render_graphic_frame(renderer, child, part_path, theme, slide_num)
        elif ln == "grpSp":
            s = _render_group(renderer, child, part_path, theme, slide_num)
        else:
            s = ""
        if s:
            parts.append(s)
    return "\n".join(parts)


# ---- Public Entrypoints -------------------------------------------------------------------------

def slide_svgs(pptx_path: str | pathlib.Path) -> list[str]:
    """Return one self-contained SVG 1.1 string per slide in presentation order."""
    pkg = _Package(pptx_path)
    try:
        pres = pkg.read_xml("ppt/presentation.xml")
        if pres is None:
            raise ValueError(f"Invalid PPTX archive (missing ppt/presentation.xml): {pptx_path}")

        sld_sz = pres.find(f"{P}sldSz")
        cx = int(sld_sz.get("cx", DEFAULT_SLIDE_CX)) if sld_sz is not None else DEFAULT_SLIDE_CX
        cy = int(sld_sz.get("cy", DEFAULT_SLIDE_CY)) if sld_sz is not None else DEFAULT_SLIDE_CY
        w_pt = _emu_to_pt(cx, 720.0)
        h_pt = _emu_to_pt(cy, 405.0)
        default_text_style = pres.find(f"{P}defaultTextStyle")

        sld_ids = pres.findall(f"{P}sldIdLst/{P}sldId")
        slide_parts: list[str] = []
        for sid in sld_ids:
            rid = sid.get(f"{R}id")
            sp = pkg.rel_target("ppt/presentation.xml", rid)
            if sp and pkg.exists(sp):
                slide_parts.append(sp)

        with tempfile.TemporaryDirectory(prefix="demolab-fonts-") as fdir:
            font_files = tuple(pkg.extract_embedded_fonts(pathlib.Path(fdir)))
            out_svgs: list[str] = []
            for idx, slide_part in enumerate(slide_parts, start=1):
                slide_root = pkg.read_xml(slide_part)
                if slide_root is None:
                    continue
                layout_part = pkg.first_rel_by_type_suffix(slide_part, "slideLayout")
                layout_root = pkg.read_xml(layout_part) if layout_part else None
                master_part = pkg.first_rel_by_type_suffix(layout_part, "slideMaster") if layout_part else None
                master_root = pkg.read_xml(master_part) if master_part else None
                theme_part = pkg.first_rel_by_type_suffix(master_part, "theme") if master_part else None
                if not theme_part:
                    theme_part = pkg.first_rel_by_type_suffix("ppt/presentation.xml", "theme")
                theme_root = pkg.read_xml(theme_part) if theme_part else None

                theme = _Theme(theme_root, _extract_clr_map(master_root))
                theme = theme.with_clr_map(_extract_clr_map(layout_root))
                theme = theme.with_clr_map(_extract_clr_map(slide_root))

                tx_styles: dict[str, etree._Element | None] = {}
                if master_root is not None:
                    txs = master_root.find(f"{P}txStyles")
                    if txs is not None:
                        tx_styles = {
                            "titleStyle": txs.find(f"{P}titleStyle"),
                            "bodyStyle": txs.find(f"{P}bodyStyle"),
                            "otherStyle": txs.find(f"{P}otherStyle"),
                        }

                layout_ph = _index_placeholders(layout_root)
                master_ph = _index_placeholders(master_root)

                renderer = _Renderer(pkg, font_files)
                layers: list[str] = []
                layers.append(
                    _render_background(
                        renderer, slide_root, layout_root, master_root,
                        slide_part, layout_part, master_part, theme, w_pt, h_pt,
                    )
                )

                show_master_on_slide = slide_root.get("showMasterSp", "1") != "0"
                show_master_on_layout = layout_root.get("showMasterSp", "1") != "0" if layout_root is not None else True

                if show_master_on_slide and show_master_on_layout and master_root is not None and master_part:
                    m_tree = master_root.find(f"{P}cSld/{P}spTree")
                    if m_tree is not None:
                        m_svg = _render_sp_tree_children(renderer, m_tree, master_part, theme, idx, skip_placeholders=True)
                        if m_svg:
                            layers.append(m_svg)

                if show_master_on_slide and layout_root is not None and layout_part:
                    l_tree = layout_root.find(f"{P}cSld/{P}spTree")
                    if l_tree is not None:
                        l_svg = _render_sp_tree_children(renderer, l_tree, layout_part, theme, idx, skip_placeholders=True)
                        if l_svg:
                            layers.append(l_svg)

                s_tree = slide_root.find(f"{P}cSld/{P}spTree")
                if s_tree is not None:
                    s_svg = _render_sp_tree_children(
                        renderer,
                        s_tree,
                        slide_part,
                        theme,
                        idx,
                        skip_placeholders=False,
                        layout_ph=layout_ph,
                        master_ph=master_ph,
                        tx_styles=tx_styles,
                        default_text_style=default_text_style,
                    )
                    if s_svg:
                        layers.append(s_svg)

                defs_block = f"<defs>\n{chr(10).join(renderer.defs)}\n</defs>" if renderer.defs else ""
                svg_doc = (
                    f'<svg xmlns="http://www.w3.org/2000/svg" '
                    f'viewBox="0 0 {w_pt:.3f} {h_pt:.3f}" width="{w_pt:.3f}" height="{h_pt:.3f}">\n'
                    f"{defs_block}\n"
                    f'{chr(10).join(layers)}\n'
                    f"</svg>"
                )
                out_svgs.append(svg_doc)
            return out_svgs
    finally:
        pkg.close()


def _letterbox_rgb(im: Image.Image, width: int, height: int) -> Image.Image:
    im = im.convert("RGB")
    if im.size == (width, height):
        return im
    im.thumbnail((width, height), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(im, ((width - im.width) // 2, (height - im.height) // 2))
    return canvas


def render_pptx(pptx_path: str | pathlib.Path, width: int = 1920, height: int = 1080) -> list[Image.Image]:
    """Render every slide in a `.pptx` file directly to `(width, height)` RGB `PIL.Image` frames."""
    svgs = slide_svgs(pptx_path)
    if not svgs:
        return []

    pkg = _Package(pptx_path)
    try:
        pres = pkg.read_xml("ppt/presentation.xml")
        sld_sz = pres.find(f"{P}sldSz") if pres is not None else None
        w_pt = _emu_to_pt(sld_sz.get("cx") if sld_sz is not None else DEFAULT_SLIDE_CX, 720.0)
        h_pt = _emu_to_pt(sld_sz.get("cy") if sld_sz is not None else DEFAULT_SLIDE_CY, 405.0)
        scale = min(width / max(w_pt, 1.0), height / max(h_pt, 1.0))
        target_w = max(1, int(round(w_pt * scale)))
        target_h = max(1, int(round(h_pt * scale)))

        with tempfile.TemporaryDirectory(prefix="demolab-rsvg-fonts-") as fdir:
            font_files = pkg.extract_embedded_fonts(pathlib.Path(fdir))
            images: list[Image.Image] = []
            for svg in svgs:
                png_bytes = resvg_py.svg_to_bytes(
                    svg_string=svg,
                    width=target_w,
                    height=target_h,
                    background="#ffffff",
                    font_files=font_files or None,
                    skip_system_fonts=False,
                )
                im = Image.open(io.BytesIO(png_bytes))
                images.append(_letterbox_rgb(im, width, height))
            return images
    finally:
        pkg.close()


def pptx_to_pdf(
    pptx_path: str | pathlib.Path,
    pdf_path: str | pathlib.Path,
    width: int = 1920,
    height: int = 1080,
    dpi: float = 144.0,
) -> pathlib.Path:
    """Render every `.pptx` slide via `render_pptx` and write a multi-page PDF to `pdf_path`."""
    out = pathlib.Path(pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    slides = render_pptx(pptx_path, width=width, height=height)
    if not slides:
        blank = Image.new("RGB", (width, height), "white")
        blank.save(out, "PDF", resolution=dpi)
        return out
    slides[0].save(out, "PDF", resolution=dpi, save_all=True, append_images=slides[1:])
    return out
