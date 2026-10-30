from io import BytesIO

import pytest
from builders import (
    make_docx,
    make_encrypted_pdf,
    make_image_only_pdf,
    make_pdf,
    make_sized_pdf,
)
from docx import Document

from app.services.parsers import Location, ParseError, file_kind, parse_document


def test_pdf_one_segment_per_page_skipping_blank_pages():
    segments = parse_document("a.pdf", make_pdf(["First page", "", "Third page"]))

    assert [s.text for s in segments] == ["First page", "Third page"]
    assert [s.location for s in segments] == [
        Location("pdf", page=1),
        Location("pdf", page=3),
    ]


def test_pdf_splits_pages_into_sections_at_headings_set_in_a_larger_font():
    body, heading = 10.0, 14.0
    data = make_sized_pdf(
        [
            [
                ("Handbook", 20.0),
                ("Welcome.", body),
                ("Refunds", heading),
                ("Within 5 days.", body),
            ],
            [("Card refunds too.", body), ("Shipping", heading), ("We ship.", body)],
        ]
    )

    segments = parse_document("a.pdf", data)

    assert [(s.text, s.location) for s in segments] == [
        ("Handbook\nWelcome.", Location("pdf", page=1, heading="Handbook")),
        ("Refunds\nWithin 5 days.", Location("pdf", page=1, heading="Refunds")),
        # The section carries on over the page break, still under its heading
        ("Card refunds too.", Location("pdf", page=2, heading="Refunds")),
        ("Shipping\nWe ship.", Location("pdf", page=2, heading="Shipping")),
    ]
    sections = [s.section for s in segments]
    assert sections[1] == sections[2]
    assert len(set(sections)) == 3


def test_pdf_with_one_font_size_is_a_single_section():
    segments = parse_document("a.pdf", make_pdf(["First page", "Second page"]))

    assert {s.section for s in segments} == {0}
    assert all(s.location.heading is None for s in segments)


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
    # Each heading opens a new section; the table row stays in the section it sits under
    assert [s.section for s in segments] == [0, 1, 1, 2, 2, 2]


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


def test_txt_without_structure_is_a_single_section():
    segments = parse_document("a.txt", b"first\nsecond\n\nthird")

    assert {s.section for s in segments} == {0}
    assert all(s.location.heading is None for s in segments)


def test_txt_faq_pairs_are_sections_headed_by_their_question():
    data = b"Clinic FAQ\n\nQ: Are you open on Sundays?\nA: No.\n\nQ: Do you take cards?\nA: Yes.\n"

    segments = parse_document("faq.txt", data)

    assert [(s.text, s.location.heading, s.location.start, s.section) for s in segments] == [
        ("Clinic FAQ", None, 1, 0),
        ("Q: Are you open on Sundays?", "Are you open on Sundays?", 3, 1),
        ("A: No.", "Are you open on Sundays?", 4, 1),
        ("Q: Do you take cards?", "Do you take cards?", 6, 2),
        ("A: Yes.", "Do you take cards?", 7, 2),
    ]


def test_txt_markdown_headings_open_sections():
    segments = parse_document("notes.txt", b"# Refunds\nWithin 5 days.\n## Shipping\nWorldwide.")

    assert [(s.location.heading, s.section) for s in segments] == [
        ("Refunds", 1),
        ("Refunds", 1),
        ("Shipping", 2),
        ("Shipping", 2),
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
        (Location("pdf", page=2, heading="Payments and refunds"), "Payments and refunds · page 2"),
        (Location("pdf", page=1, page_end=2, heading="Refunds"), "Refunds · pages 1-2"),
        (Location("txt", heading="Take cards?", start=6, end=7), "Take cards? · lines 6-7"),
        (Location("txt", start=4, end=4), "line 4"),
        (Location("txt", start=4, end=9), "lines 4-9"),
        (Location("docx", heading="Refunds", start=2, end=5), "Refunds · paragraphs 2-5"),
        (Location("docx", start=2, end=2), "paragraph 2"),
    ],
)
def test_location_labels(location: Location, label: str):
    assert location.label() == label
