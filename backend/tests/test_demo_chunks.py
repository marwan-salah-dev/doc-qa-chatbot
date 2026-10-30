"""The committed demo files chunk into one chunk per section, labelled by heading."""

from app.services.chunking import chunk_segments
from app.services.parsers import parse_document
from scripts.seed_demo import DEMO_DATA_DIR, DEMO_FILES

PDF_NAME, DOCX_NAME, TXT_NAME = DEMO_FILES


def labels(filename: str) -> list[str]:
    segments = parse_document(filename, (DEMO_DATA_DIR / filename).read_bytes())
    return [chunk.location.label() for chunk in chunk_segments(segments)]


def test_handbook_pdf_is_one_chunk_per_section_with_its_page():
    assert labels(PDF_NAME) == [
        "BrightSmile Dental Patient Handbook · page 1",
        "1. Opening hours · page 1",
        "2. Booking and cancellations · page 1",
        "3. Insurance · page 1",
        "4. Payments and refunds · page 2",
        "5. Dental emergencies · page 2",
        "6. Aftercare · page 2",
    ]


def test_price_list_docx_keeps_the_table_under_its_heading():
    assert labels(DOCX_NAME) == [
        "BrightSmile Dental Price List 2026 · paragraphs 1-2",
        "Treatments and prices · paragraphs 3-16",
        "Payment and cancellation notes · paragraphs 17-19",
    ]


def test_faq_txt_is_one_chunk_per_question():
    found = labels(TXT_NAME)

    assert len(found) == 11  # the title line, then ten Q/A pairs
    assert found[1] == "Where is the clinic? · lines 3-4"
    assert "Do you accept my insurance? · lines 21-22" in found
