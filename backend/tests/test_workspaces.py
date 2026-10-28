from sqlalchemy import select

from app.db.models import Conversation, Document, DocumentStatus, Message, MessageRole


def create(client, name="Acme Dental"):
    response = client.post("/workspaces", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_create_and_get(client):
    created = create(client)
    assert created["name"] == "Acme Dental"
    assert len(created["id"]) == 32

    fetched = client.get(f"/workspaces/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_name_is_trimmed_and_validated(client):
    assert create(client, "  Padded  ")["name"] == "Padded"
    for bad in ("", "   ", "x" * 101):
        assert client.post("/workspaces", json={"name": bad}).status_code == 422


def test_list_newest_first(client):
    first = create(client, "First")
    second = create(client, "Second")
    ids = [w["id"] for w in client.get("/workspaces").json()]
    assert ids == [second["id"], first["id"]]


def test_rename(client):
    created = create(client)
    response = client.patch(f"/workspaces/{created['id']}", json={"name": "Renamed"})
    assert response.status_code == 200
    assert client.get(f"/workspaces/{created['id']}").json()["name"] == "Renamed"


def test_missing_workspace_returns_404(client):
    assert client.get("/workspaces/nope").status_code == 404
    assert client.patch("/workspaces/nope", json={"name": "x"}).status_code == 404
    assert client.delete("/workspaces/nope").status_code == 404


def test_delete_cascades_to_children(client):
    workspace = create(client)
    other = create(client, "Other")
    session_factory = client.app.state.session_factory

    with session_factory() as db:
        doc = Document(
            workspace_id=workspace["id"],
            filename="faq.txt",
            content_type="text/plain",
            size_bytes=10,
            sha256="a" * 64,
        )
        convo = Conversation(workspace_id=workspace["id"])
        convo.messages.append(
            Message(role=MessageRole.ASSISTANT, content="Hi [1]", citations=[{"n": 1}])
        )
        db.add_all(
            [
                doc,
                convo,
                Document(
                    workspace_id=other["id"],
                    filename="faq.txt",
                    content_type="text/plain",
                    size_bytes=10,
                    sha256="a" * 64,
                ),
            ]
        )
        db.commit()
        assert doc.status == DocumentStatus.PENDING

    assert client.delete(f"/workspaces/{workspace['id']}").status_code == 204
    assert client.get(f"/workspaces/{workspace['id']}").status_code == 404

    with session_factory() as db:
        assert len(db.scalars(select(Document)).all()) == 1  # the other workspace's survives
        assert db.scalars(select(Conversation)).all() == []
        assert db.scalars(select(Message)).all() == []
    assert client.get(f"/workspaces/{other['id']}").status_code == 200


def test_duplicate_file_in_workspace_rejected(client):
    from sqlalchemy.exc import IntegrityError

    workspace = create(client)

    def make_doc():
        return Document(
            workspace_id=workspace["id"],
            filename="a.txt",
            content_type="text/plain",
            size_bytes=1,
            sha256="b" * 64,
        )

    with client.app.state.session_factory() as db:
        db.add(make_doc())
        db.commit()
        db.add(make_doc())
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("duplicate sha256 in one workspace should be rejected")
