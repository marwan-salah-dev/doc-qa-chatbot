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


def test_every_setting_is_documented_in_env_example():
    # CLAUDE.md: every new setting must also be added to backend/.env.example with a comment
    from pathlib import Path

    from app.config import Settings

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    documented = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line}
    missing = {name.upper() for name in Settings.model_fields} - documented
    assert not missing


def test_config_says_whether_this_is_the_public_demo(make_client):
    assert make_client().get("/config").json()["public_demo"] is False
    assert make_client(public_demo=True).get("/config").json()["public_demo"] is True


def test_demo_limits_have_safe_defaults():
    from app.config import Settings

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.public_demo is False  # local dev and client deployments are unchanged
    # Below Groq's free 200K tokens/day, with room for the turns already in flight
    assert 0 < settings.daily_token_cap <= 160_000
    assert settings.visitor_workspace_ttl_hours == 24
