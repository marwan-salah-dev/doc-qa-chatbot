"""Small in-memory PDF and DOCX files for tests (no fixture files on disk)."""

from io import BytesIO

from docx import Document
from pypdf import PdfReader, PdfWriter


def build_pdf(page_streams: list[bytes], *, image: bool = False) -> bytes:
    """Hand-build a minimal valid PDF with one content stream per page."""
    n = len(page_streams)
    # Objects: 1 catalog, 2 pages, 3 font, 4 image, then a (page, content) pair per page.
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Length 1 >>\nstream\n\x80\nendstream",
    ]
    resources = "/Font << /F1 3 0 R >>" + (" /XObject << /Im0 4 0 R >>" if image else "")
    for i, stream in enumerate(page_streams):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {6 + 2 * i} 0 R "
            f"/Resources << {resources} >> >>".encode()
        )
        objects.append(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref)
    return bytes(out)


def make_pdf(pages: list[str]) -> bytes:
    streams = [f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b"" for text in pages]
    return build_pdf(streams)


def make_image_only_pdf() -> bytes:
    return build_pdf([b"q 200 0 0 200 100 100 cm /Im0 Do Q"], image=True)


def make_encrypted_pdf() -> bytes:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(make_pdf(["Secret"]))))
    writer.encrypt("pw", algorithm="RC4-128")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_docx() -> bytes:
    doc = Document()
    doc.add_paragraph("Intro before any heading.")
    doc.add_heading("Refunds", level=1)
    doc.add_paragraph("")
    doc.add_paragraph("Refunds take 5 days.")
    doc.add_heading("Shipping", level=2)
    doc.add_paragraph("We ship worldwide.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Plan"
    table.rows[0].cells[1].text = "Price"
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
