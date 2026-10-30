"""The BrightSmile Dental demo: the committed sample files and the seed script that loads them."""

import hashlib
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.db.models import Document, DocumentStatus
from app.demo import DEMO_STARTER_QUESTIONS, DEMO_WORKSPACE_NAME
from app.services.parsers import parse_document
from scripts import demo_content as content
from scripts.seed_demo import DEMO_DATA_DIR, DEMO_FILES, SeedError, admin_headers, seed

PDF, DOCX, TXT = DEMO_FILES


def file_bytes(name: str) -> bytes:
    return (DEMO_DATA_DIR / name).read_bytes()


def parsed_text(name: str) -> str:
    return "\n".join(segment.text for segment in parse_document(name, file_bytes(name)))


def flat_text(name: str) -> str:
    """Parsed text with all whitespace runs as one space, so a PDF line wrap can't split a fact."""
    return " ".join(parsed_text(name).split())


def workspaces(client: TestClient) -> list[dict]:
    response = client.get("/workspaces")
    assert response.status_code == 200
    return response.json()


def documents(client: TestClient, workspace_id: str) -> list[dict]:
    response = client.get(f"/workspaces/{workspace_id}/documents")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


# --- The committed files -------------------------------------------------------------------


def test_the_pdf_handbook_has_two_or_three_pages_and_every_section() -> None:
    pages = PdfReader(BytesIO(file_bytes(PDF))).pages
    assert 2 <= len(pages) <= 3
    text = parsed_text(PDF)
    for heading, _ in content.HANDBOOK_SECTIONS:
        assert heading in text


def test_the_price_list_is_a_table_of_treatments_and_prices() -> None:
    text = parsed_text(DOCX)
    for treatment, price, _ in content.PRICES:
        assert f"{treatment} | {price}" in text


def test_the_faq_has_8_to_12_questions() -> None:
    lines = parsed_text(TXT).splitlines()
    questions = [line for line in lines if line.startswith("Q: ")]
    assert 8 <= len(questions) <= 12
    assert len(questions) == len(content.FAQ)


def test_key_facts_match_across_files() -> None:
    pdf, docx, txt = flat_text(PDF), flat_text(DOCX), flat_text(TXT)
    for text in (pdf, txt):
        assert content.PHONE in text
        assert content.CANCELLATION_FEE in text
        assert content.EMERGENCY_PHONE in text
    for text in (docx, pdf):
        assert content.IMPLANT_PRICE in text
        assert content.PLAN_THRESHOLD in text
    assert content.CHECKUP_PRICE in docx
    assert content.CHECKUP_PRICE in txt


def test_contact_details_are_clearly_fictional() -> None:
    assert "555-01" in content.PHONE
    assert "555-01" in content.EMERGENCY_PHONE
    assert content.EMAIL.endswith("example.com")


def test_the_pdf_disclaimer_is_one_closing_line_on_the_last_page() -> None:
    # Not a per-page footer: that text would lead every page's chunk and every PDF citation
    pages = [page.extract_text() or "" for page in PdfReader(BytesIO(file_bytes(PDF))).pages]
    assert all(content.DISCLAIMER not in text for text in pages[:-1])
    assert pages[-1].count(content.DISCLAIMER) == 1
    assert pages[-1].rstrip().endswith(content.DISCLAIMER)
    assert pages[0].lstrip().startswith(content.HANDBOOK_TITLE)


def test_the_docx_disclaimer_is_a_footer_that_parsing_ignores() -> None:
    docx = DocxDocument(BytesIO(file_bytes(DOCX)))
    assert content.DISCLAIMER in "\n".join(p.text for p in docx.sections[0].footer.paragraphs)
    # Our DOCX parser reads the body only, so the footer never reaches a chunk or citation
    assert content.DISCLAIMER not in parsed_text(DOCX)


def test_the_faq_has_no_disclaimer() -> None:
    assert "fictional" not in file_bytes(TXT).decode().lower()


def test_no_file_mentions_parking() -> None:
    # The refusal starter question asks about parking: it must stay unanswerable
    for name in DEMO_FILES:
        assert "parking" not in parsed_text(name).lower()


def test_the_starter_questions_include_the_unanswerable_one() -> None:
    assert 4 <= len(DEMO_STARTER_QUESTIONS) <= 6
    assert any("parking" in question.lower() for question in DEMO_STARTER_QUESTIONS)


# --- Seeding -------------------------------------------------------------------------------


def test_seed_creates_the_demo_workspace_with_three_ready_documents(client: TestClient) -> None:
    result = seed(client, poll_interval=0)

    assert result.created_workspace
    assert sorted(result.uploaded) == sorted(DEMO_FILES)
    [workspace] = [w for w in workspaces(client) if w["name"] == DEMO_WORKSPACE_NAME]
    assert workspace["id"] == result.workspace_id
    assert workspace["is_demo"] is True
    assert workspace["starter_questions"] == list(DEMO_STARTER_QUESTIONS)
    docs = documents(client, result.workspace_id)
    assert sorted(d["filename"] for d in docs) == sorted(DEMO_FILES)
    assert {d["status"] for d in docs} == {"ready"}


def test_seeding_twice_creates_nothing_new(client: TestClient) -> None:
    first = seed(client, poll_interval=0)
    ids_before = {d["id"] for d in documents(client, first.workspace_id)}

    second = seed(client, poll_interval=0)

    assert second.workspace_id == first.workspace_id
    assert not second.created_workspace
    assert second.uploaded == []
    assert sorted(second.skipped) == sorted(DEMO_FILES)
    assert [w["name"] for w in workspaces(client)].count(DEMO_WORKSPACE_NAME) == 1
    assert {d["id"] for d in documents(client, first.workspace_id)} == ids_before


def test_seed_finds_the_demo_by_its_flag_not_its_name(client: TestClient) -> None:
    copycat = client.post("/workspaces", json={"name": DEMO_WORKSPACE_NAME}).json()

    result = seed(client, poll_interval=0)

    assert result.created_workspace
    assert result.workspace_id != copycat["id"]
    assert documents(client, copycat["id"]) == []


def test_on_the_public_demo_the_seed_needs_the_admin_key(
    make_client: Callable[..., TestClient],
) -> None:
    public = make_client(public_demo=True, admin_api_key="seed-key-for-tests")

    with pytest.raises(SeedError, match="403"):
        seed(public, poll_interval=0)

    public.headers.update(admin_headers("seed-key-for-tests"))
    result = seed(public, poll_interval=0)
    assert {d["status"] for d in documents(public, result.workspace_id)} == {"ready"}


def test_admin_headers_are_only_sent_when_a_key_is_set() -> None:
    assert admin_headers("") == {}
    assert admin_headers("k") == {"X-Admin-Key": "k"}


def test_seed_leaves_other_workspaces_alone(client: TestClient) -> None:
    acme = client.post("/workspaces", json={"name": "Acme Dental"}).json()
    client.post(
        f"/workspaces/{acme['id']}/documents",
        files={"file": ("faq.txt", b"We are open 9 to 5.", "text/plain")},
    )
    acme_docs = documents(client, acme["id"])

    seed(client, poll_interval=0)

    assert [w for w in workspaces(client) if w["id"] == acme["id"]] == [acme]
    assert documents(client, acme["id"]) == acme_docs


def test_seed_reindexes_a_failed_demo_document(client: TestClient) -> None:
    first = seed(client, poll_interval=0)
    faq = next(d for d in documents(client, first.workspace_id) if d["filename"] == TXT)
    with client.app.state.session_factory() as db:  # pyright: ignore[reportAttributeAccessIssue]
        db.get(Document, faq["id"]).status = DocumentStatus.FAILED
        db.commit()

    second = seed(client, poll_interval=0)

    assert second.reindexed == [TXT]
    assert {d["status"] for d in documents(client, first.workspace_id)} == {"ready"}


def copy_demo_files(tmp_path: Path) -> Path:
    data_dir = tmp_path / "demo"
    data_dir.mkdir()
    for name in DEMO_FILES:
        (data_dir / name).write_bytes(file_bytes(name))
    return data_dir


def test_seed_replaces_a_demo_document_whose_file_changed(
    client: TestClient, tmp_path: Path
) -> None:
    data_dir = copy_demo_files(tmp_path)
    first = seed(client, data_dir=data_dir, poll_interval=0)
    before = {d["filename"]: d for d in documents(client, first.workspace_id)}
    changed = file_bytes(TXT) + b"Q: Do you open late on Thursdays?\nA: No.\n"
    (data_dir / TXT).write_bytes(changed)

    second = seed(client, data_dir=data_dir, poll_interval=0)

    assert second.replaced == [TXT]
    assert sorted(second.skipped) == sorted([PDF, DOCX])
    after = {d["filename"]: d for d in documents(client, first.workspace_id)}
    assert sorted(after) == sorted(DEMO_FILES)
    assert after[TXT]["id"] != before[TXT]["id"]
    assert after[TXT]["sha256"] == hashlib.sha256(changed).hexdigest()
    assert after[PDF]["id"] == before[PDF]["id"]
    assert {d["status"] for d in after.values()} == {"ready"}
    # The old document is gone, so its chunks and stored file went with it
    response = client.get(f"/workspaces/{first.workspace_id}/documents/{before[TXT]['id']}")
    assert response.status_code == 404


def test_seed_reports_a_document_that_fails_to_index(client: TestClient, tmp_path: Path) -> None:
    data_dir = copy_demo_files(tmp_path)
    (data_dir / PDF).write_bytes(b"%PDF-1.4 not really a pdf")

    with pytest.raises(SeedError, match=PDF):
        seed(client, data_dir=data_dir, poll_interval=0)


# --- Starter questions in the API ----------------------------------------------------------


def test_only_the_demo_workspace_has_starter_questions(client: TestClient) -> None:
    # The flag decides, not the name: a visitor could call a workspace anything
    client.post("/workspaces", json={"name": DEMO_WORKSPACE_NAME, "is_demo": True})
    client.post("/workspaces", json={"name": DEMO_WORKSPACE_NAME + " (copy)"})
    client.post("/workspaces", json={"name": "Acme Dental"})

    by_name = {w["name"]: w["starter_questions"] for w in workspaces(client)}

    assert by_name[DEMO_WORKSPACE_NAME] == list(DEMO_STARTER_QUESTIONS)
    assert by_name[DEMO_WORKSPACE_NAME + " (copy)"] == []
    assert by_name["Acme Dental"] == []
