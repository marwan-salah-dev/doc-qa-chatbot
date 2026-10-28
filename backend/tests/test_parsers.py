from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfReader, PdfWriter

from app.services.parsers import Location, ParseError, file_kind, parse_document


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


def test_pdf_one_segment_per_page_skipping_blank_pages():
    segments = parse_document("a.pdf", make_pdf(["First page", "", "Third page"]))

    assert [s.text for s in segments] == ["First page", "Third page"]
    assert [s.location for s in segments] == [
        Location("pdf", page=1),
        Location("pdf", page=3),
    ]


def test_image_only_pdf_gives_no_text_error():
    with pytest.raises(ParseError, match="No text found"):
        parse_document("scan.pdf", make_image_only_pdf())


def test_corrupt_pdf():
    with pytest.raises(ParseError, match="corrupt"):
        parse_document("bad.pdf", b"this is not a pdf")


def test_password_protected_pdf():
    with pytest.raises(ParseError, match="password"):
        parse_document("locked.pdf", make_encrypted_pdf())


def test_empty_pdf_bytes():
    with pytest.raises(ParseError):
        parse_document("empty.pdf", b"")


def test_docx_tracks_headings_and_paragraph_numbers():
    segments = parse_document("a.docx", make_docx())

    assert [(s.text, s.location.heading, s.location.start) for s in segments] == [
        ("Intro before any heading.", None, 1),
        ("Refunds", "Refunds", 2),
        ("Refunds take 5 days.", "Refunds", 3),  # the empty paragraph is not counted
        ("Shipping", "Shipping", 4),
        ("We ship worldwide.", "Shipping", 5),
        ("Plan | Price", "Shipping", 6),
    ]
    assert all(s.location.kind == "docx" and s.location.start == s.location.end for s in segments)


def test_corrupt_docx():
    with pytest.raises(ParseError, match="corrupt"):
        parse_document("bad.docx", b"not a zip")


def test_empty_docx():
    buffer = BytesIO()
    Document().save(buffer)
    with pytest.raises(ParseError, match="No text"):
        parse_document("empty.docx", buffer.getvalue())


def test_txt_line_numbers_skip_blank_lines():
    segments = parse_document("a.txt", b"first\n\n  second  \r\nthird")

    assert [(s.text, s.location.start, s.location.end) for s in segments] == [
        ("first", 1, 1),
        ("second", 3, 3),
        ("third", 4, 4),
    ]


@pytest.mark.parametrize(
    "encoded",
    [
        "Café crème brûlée, prix 5€".encode("utf-8-sig"),
        "Café crème brûlée, prix 5€".encode("utf-16"),
        # Legacy single-byte encodings are only detectable with enough text.
        (
            "Café crème brûlée : nos horaires d'ouverture sont du lundi au vendredi, de 9h à 18h. "
            "Les remboursements sont traités sous cinq jours ouvrés. Où trouver notre brochure ? "
            "Elle est disponible à l'accueil."
        ).encode("cp1252"),
    ],
)
def test_txt_detects_encoding(encoded: bytes):
    [segment] = parse_document("a.txt", encoded)

    assert segment.text.startswith("Café crème brûlée")


@pytest.mark.parametrize("data", [b"", b"  \n\n \r\n"])
def test_empty_txt(data: bytes):
    with pytest.raises(ParseError, match="empty"):
        parse_document("a.txt", data)


def test_binary_data_is_not_a_txt_file():
    with pytest.raises(ParseError):
        parse_document("a.txt", bytes(range(256)) * 4)


def test_unsupported_extension():
    with pytest.raises(ParseError, match="Unsupported"):
        parse_document("a.exe", b"data")


def test_file_kind_is_case_insensitive():
    assert file_kind("REPORT.PDF") == "pdf"


@pytest.mark.parametrize(
    ("location", "label"),
    [
        (Location("pdf", page=3), "page 3"),
        (Location("txt", start=4, end=4), "line 4"),
        (Location("txt", start=4, end=9), "lines 4-9"),
        (Location("docx", heading="Refunds", start=2, end=5), "Refunds · paragraphs 2-5"),
        (Location("docx", start=2, end=2), "paragraph 2"),
    ],
)
def test_location_labels(location: Location, label: str):
    assert location.label() == label
