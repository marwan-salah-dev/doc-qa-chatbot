from app.api.schemas import MAX_QUESTION_CHARS


def test_config_exposes_the_upload_limit(client):
    response = client.get("/config")

    assert response.status_code == 200
    assert response.json()["max_upload_mb"] == 20


def test_config_follows_the_setting(make_client):
    client = make_client(max_upload_mb=5)

    assert client.get("/config").json()["max_upload_mb"] == 5


def test_config_exposes_the_question_limit(client):
    # The composer enforces the same limit as MessageCreate, so the UI never keeps its own copy
    assert client.get("/config").json()["max_question_chars"] == MAX_QUESTION_CHARS
