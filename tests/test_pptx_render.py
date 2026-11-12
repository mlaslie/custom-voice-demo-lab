import io
import zipfile

import pypdfium2 as pdfium
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from demolab import pptx_render


def test_shapes_gradients_tables_groups_and_images_render_to_png_and_pdf(tmp_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # Slide 1: solid background, rounded card, rightArrow, bulleted rich text, picture with crop
    s1 = prs.slides.add_slide(blank)
    bg = s1.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x10, 0x20, 0x38)

    card = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.8), Inches(6.0), Inches(4.0))
    card.fill.gradient()
    card.fill.gradient_stops[0].color.rgb = RGBColor(0x1E, 0x40, 0xAF)
    card.fill.gradient_stops[1].color.rgb = RGBColor(0x0F, 0x76, 0x6E)
    card.line.color.rgb = RGBColor(0x93, 0xC5, 0xFD)
    card.line.width = Pt(2)
    tf = card.text_frame
    p1 = tf.paragraphs[0]
    r1 = p1.add_run()
    r1.text = "Architecture Overview"
    r1.font.bold = True
    r1.font.size = Pt(24)
    r1.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p2 = tf.add_paragraph()
    p2.text = "Serverless pipeline step"
    p2.font.size = Pt(16)
    p2.font.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)

    arrow = s1.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(7.1), Inches(2.2), Inches(1.4), Inches(0.9))
    arrow.fill.solid()
    arrow.fill.fore_color.rgb = RGBColor(0xF5, 0x9E, 0x0B)
    arrow.line.fill.background()

    img_path = tmp_path / "photo.png"
    Image.new("RGB", (200, 200), (220, 38, 38)).save(img_path)
    pic = s1.shapes.add_picture(str(img_path), Inches(9.0), Inches(1.0), Inches(3.2), Inches(3.2))
    pic.crop_left = 0.1
    pic.crop_right = 0.1

    # Slide 2: merged-cell table + grouped shapes + schemeClr
    s2 = prs.slides.add_slide(blank)
    tbl_shape = s2.shapes.add_table(3, 3, Inches(0.8), Inches(0.8), Inches(11.5), Inches(2.6))
    tbl = tbl_shape.table
    tbl.cell(0, 0).merge(tbl.cell(0, 1))
    tbl.cell(0, 0).text = "Merged Header"
    tbl.cell(0, 2).text = "Region"
    tbl.cell(1, 0).text = "Lakehouse"
    tbl.cell(1, 1).text = "Active"
    tbl.cell(1, 2).text = "us-central1"
    tbl.cell(2, 0).text = "Vector Index"
    tbl.cell(2, 1).text = "Ready"
    tbl.cell(2, 2).text = "global"

    grp = s2.shapes.add_group_shape()
    b1 = grp.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.0), Inches(4.0), Inches(1.8), Inches(1.8))
    b1.fill.solid()
    b1.fill.fore_color.rgb = RGBColor(0x05, 0x96, 0x69)
    b1.text = "Node A"

    pptx_path = tmp_path / "rich.pptx"
    prs.save(str(pptx_path))

    svgs = pptx_render.slide_svgs(pptx_path)
    assert len(svgs) == 2
    assert "Architecture Overview" in svgs[0]
    assert "Merged Header" in svgs[1]
    assert "Node A" in svgs[1]

    imgs = pptx_render.render_pptx(pptx_path)
    assert len(imgs) == 2
    for im in imgs:
        assert im.size == (1920, 1080)
        assert im.mode == "RGB"
    # Top-left background pixel of slide 1 should match #102038 = (16, 32, 56)
    bg_px = imgs[0].getpixel((12, 12))
    assert abs(bg_px[0] - 16) <= 3 and abs(bg_px[1] - 32) <= 3 and abs(bg_px[2] - 56) <= 3
    # Cropped red picture center on slide 1 should be near #DC2626 = (220, 38, 38)
    pic_px = imgs[0].getpixel((int(1920 * 10.6 / 13.333), int(1080 * 2.6 / 7.5)))
    assert pic_px[0] > 200 and pic_px[1] < 60 and pic_px[2] < 60

    pdf_path = tmp_path / "rich.pdf"
    pptx_render.pptx_to_pdf(pptx_path, pdf_path)
    assert pdf_path.is_file()
    doc = pdfium.PdfDocument(str(pdf_path))
    assert len(doc) == 2
    doc.close()


def test_master_placeholder_prompts_are_not_rendered(tmp_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Default title slide layout contains master/layout placeholder prompts like
    # "Click to edit Master title style"; add decorative non-placeholder bar to master
    master = prs.slide_masters[0]
    bar_xml = etree.fromstring(
        '<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:nvSpPr><p:cNvPr id="77" name="HeaderBar"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="12191695" cy="182880"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:solidFill><a:srgbClr val="1A73E8"/></a:solidFill></p:spPr></p:sp>'
    )
    master.shapes._spTree.append(bar_xml)

    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Real Slide Title"
    # Leave subtitle placeholder unfilled

    pptx_path = tmp_path / "master_ph.pptx"
    prs.save(str(pptx_path))

    svgs = pptx_render.slide_svgs(pptx_path)
    assert len(svgs) == 1
    assert "Real Slide Title" in svgs[0]
    assert "Click to edit Master" not in svgs[0]
    assert "#1a73e8" in svgs[0].lower()

    imgs = pptx_render.render_pptx(pptx_path)
    assert len(imgs) == 1
    top_bar_px = imgs[0].getpixel((500, 8))
    assert top_bar_px[2] > 200 and top_bar_px[0] < 60


def test_charts_and_smartart_fallback_render(tmp_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # Slide 1: Column chart + Pie chart
    s1 = prs.slides.add_slide(blank)
    cdata = CategoryChartData()
    cdata.categories = ["Q1", "Q2", "Q3"]
    cdata.add_series("Latency ms", (42, 31, 24))
    ch1 = s1.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(0.5), Inches(6.0), Inches(5.0), cdata).chart
    ch1.has_title = True
    ch1.chart_title.text_frame.text = "Query Latency"

    pdata = CategoryChartData()
    pdata.categories = ["FHIR", "DICOM"]
    pdata.add_series("Share", (65, 35))
    ch2 = s1.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(6.8), Inches(0.5), Inches(6.0), Inches(5.0), pdata).chart
    ch2.has_title = True
    ch2.chart_title.text_frame.text = "Modalities"

    # Slide 2: placeholder slide that we inject a SmartArt graphicFrame + diagram drawing XML into
    s2 = prs.slides.add_slide(blank)
    pptx_path = tmp_path / "charts_smartart.pptx"
    prs.save(str(pptx_path))

    drawing_xml = """<dsp:drawing xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <dsp:spTree>
        <dsp:nvGrpSpPr><dsp:cNvPr id="0" name=""/><dsp:cNvGrpSpPr/></dsp:nvGrpSpPr>
        <dsp:grpSpPr><a:xfrm/></dsp:grpSpPr>
        <dsp:sp>
          <dsp:nvSpPr><dsp:cNvPr id="1" name="Step1"/><dsp:cNvSpPr/></dsp:nvSpPr>
          <dsp:spPr>
            <a:xfrm><a:off x="0" y="0"/><a:ext cx="2286000" cy="914400"/></a:xfrm>
            <a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>
            <a:solidFill><a:srgbClr val="1A73E8"/></a:solidFill>
          </dsp:spPr>
          <dsp:txBody>
            <a:bodyPr anchor="ctr"/>
            <a:p><a:r><a:rPr sz="1600" b="1"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></a:rPr><a:t>Ingest Step</a:t></a:r></a:p>
          </dsp:txBody>
        </dsp:sp>
      </dsp:spTree>
    </dsp:drawing>""".encode("utf-8")

    # Inject graphicFrame + drawing1.xml cleanly into the zip copy
    patched = tmp_path / "charts_smartart_patched.pptx"
    with zipfile.ZipFile(pptx_path, "r") as zin, zipfile.ZipFile(patched, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "ppt/slides/slide2.xml":
                root = etree.fromstring(data)
                sp_tree = root.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}spTree")
                gf = etree.fromstring(
                    '<p:graphicFrame xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                    'xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram">'
                    '<p:nvGraphicFramePr><p:cNvPr id="99" name="Diagram 1"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
                    '<p:xfrm><a:off x="914400" y="914400"/><a:ext cx="4572000" cy="1828800"/></p:xfrm>'
                    '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/diagram">'
                    '<dgm:relIds r:dm="rId99"/>'
                    '</a:graphicData></a:graphic></p:graphicFrame>'
                )
                sp_tree.append(gf)
                data = etree.tostring(root)
            elif item.filename == "ppt/slides/_rels/slide2.xml.rels":
                rroot = etree.fromstring(data)
                rroot.append(
                    etree.fromstring(
                        '<Relationship xmlns="http://schemas.openxmlformats.org/package/2006/relationships" '
                        'Id="rId98" Type="http://schemas.microsoft.com/office/2007/relationships/diagramDrawing" '
                        'Target="../diagrams/drawing1.xml"/>'
                    )
                )
                data = etree.tostring(rroot)
            zout.writestr(item, data)
        zout.writestr("ppt/diagrams/drawing1.xml", drawing_xml)

    svgs = pptx_render.slide_svgs(patched)
    assert len(svgs) == 2
    assert "Query Latency" in svgs[0] and "Q1" in svgs[0]
    assert "Modalities" in svgs[0] and "FHIR" in svgs[0]
    assert "Ingest Step" in svgs[1]

    imgs = pptx_render.render_pptx(patched)
    assert len(imgs) == 2 and all(im.size == (1920, 1080) for im in imgs)


def test_xml_special_chars_and_control_chars_escaped(tmp_path):
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(1), Inches(1), Inches(7), Inches(2))
    tb.text_frame.text = "R&D <Healthcare> & \"AI\" 'v1'\x0bNext Line\x00Hidden"

    pptx_path = tmp_path / "escape.pptx"
    prs.save(str(pptx_path))

    imgs = pptx_render.render_pptx(pptx_path)
    assert len(imgs) == 1
    assert imgs[0].size == (1920, 1080)


def test_table_grid_widths_win_over_stale_graphic_frame_xfrm(tmp_path):
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(5.625)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    # Add 2x2 table initially narrow in graphicFrame xfrm, then widen tblGrid columns directly
    gf = s.shapes.add_table(2, 2, Inches(0.5), Inches(1.0), Inches(3.0), Inches(1.5))
    gf.table.columns[0].width = Inches(4.5)
    gf.table.columns[1].width = Inches(4.5)
    gf.table.cell(0, 0).fill.solid()
    gf.table.cell(0, 0).fill.fore_color.rgb = RGBColor(0x42, 0x85, 0xF4)
    gf.table.cell(0, 1).fill.solid()
    gf.table.cell(0, 1).fill.fore_color.rgb = RGBColor(0xEA, 0x43, 0x35)

    pptx_path = tmp_path / "wide_tbl_grid.pptx"
    prs.save(str(pptx_path))

    imgs = pptx_render.render_pptx(pptx_path)
    im = imgs[0]
    # Second column spans x = 5.0in..9.5in (50%..95% of 1920px = 960..1824px).
    # Sample at x=7.5in (1440px), y=1.35in (259px) -> must be red (#EA4335), not blank white.
    px = im.getpixel((int(1920 * 7.5 / 10.0), int(1080 * 1.35 / 5.625)))
    assert px[0] > 200 and px[1] < 90 and px[2] < 80
