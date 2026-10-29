"""Build the BrightSmile Dental demo files into `backend/demo_data/` from `demo_content`.

Run from backend/ after changing the content, then commit the files:

    uv run python -m scripts.build_demo_docs

Needs reportlab, a dev dependency. The seed script only reads the committed files, so it (and
the production image) never needs reportlab. The output is byte-for-byte the same on every run,
so rebuilding without content changes leaves git clean.
"""

import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import cast
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Pt
from docx.styles.style import ParagraphStyle as DocxParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from scripts import demo_content as content
from scripts.seed_demo import DEMO_DATA_DIR, DEMO_FILES

PDF_NAME, DOCX_NAME, TXT_NAME = DEMO_FILES
# A fixed date for file metadata, so the output doesn't change from run to run
FIXED_DATE = datetime(2026, 1, 1, tzinfo=UTC)
BRAND = colors.HexColor("#0E7490")


def build_pdf() -> bytes:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("HandbookTitle", parent=styles["Title"], textColor=BRAND, fontSize=22)
    heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=BRAND,
        spaceBefore=14,
        keepWithNext=1,
    )
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10.5, leading=15)
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=16, bulletIndent=4, spaceBefore=0)

    story = [
        Paragraph(escape(content.HANDBOOK_TITLE), title),
        Paragraph(escape(content.HANDBOOK_INTRO), body),
        Spacer(1, 6),
    ]
    for section, paragraphs in content.HANDBOOK_SECTIONS:
        story.append(Paragraph(escape(section), heading))
        for text in paragraphs:
            if text.startswith("- "):
                story.append(Paragraph(escape(text[2:]), bullet, bulletText="•"))
            else:
                story.append(Paragraph(escape(text), body))
    # Once, at the very end. Not a page footer: footer text is extracted with every page, so it
    # would lead each page's chunk and every PDF citation preview.
    closing = ParagraphStyle("Closing", parent=body, fontSize=8, textColor=colors.grey)
    story += [Spacer(1, 18), Paragraph(escape(content.DISCLAIMER), closing)]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        title=content.HANDBOOK_TITLE,
        author=content.CLINIC,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
        invariant=1,  # no timestamps or random ids in the file
    )
    doc.build(story)
    return buffer.getvalue()


def build_docx() -> bytes:
    doc = Document()
    cast(DocxParagraphStyle, doc.styles["Normal"]).font.size = Pt(10.5)
    doc.add_heading(content.PRICE_LIST_TITLE, level=0)
    doc.add_paragraph(content.PRICE_LIST_INTRO)

    doc.add_heading("Treatments and prices", level=1)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    for cell, label in zip(table.rows[0].cells, ("Treatment", "Price", "Notes"), strict=True):
        cell.text = label
    for row in content.PRICES:
        for cell, value in zip(table.add_row().cells, row, strict=True):
            cell.text = value

    doc.add_heading("Payment and cancellation notes", level=1)
    for note in content.PRICE_LIST_NOTES:
        doc.add_paragraph(note, style="List Bullet")

    doc.sections[0].footer.paragraphs[0].text = content.DISCLAIMER

    props = doc.core_properties
    props.title = content.PRICE_LIST_TITLE
    props.author = props.last_modified_by = content.CLINIC
    props.created = props.modified = FIXED_DATE.replace(tzinfo=None)
    props.revision = 1

    buffer = BytesIO()
    doc.save(buffer)
    return _fixed_zip_dates(buffer.getvalue())


def _fixed_zip_dates(data: bytes) -> bytes:
    """Rewrite a zip (a DOCX) with every entry dated FIXED_DATE: python-docx stamps the time."""
    out = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(data)) as source,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=FIXED_DATE.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, source.read(item))
    return out.getvalue()


def build_txt() -> bytes:
    lines = [content.FAQ_TITLE, ""]
    for question, answer in content.FAQ:
        lines += [f"Q: {question}", f"A: {answer}", ""]
    return "\n".join(lines).encode()


def build_all(out_dir: Path = DEMO_DATA_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    built = {PDF_NAME: build_pdf(), DOCX_NAME: build_docx(), TXT_NAME: build_txt()}
    paths = []
    for name, data in built.items():
        path = out_dir / name
        path.write_bytes(data)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for path in build_all():
        print(f"wrote {path} ({path.stat().st_size:,} bytes)")
