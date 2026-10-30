"""Columns added after a database was first created reach it on the next start."""

import sqlite3
from pathlib import Path

from sqlalchemy import inspect

from app.db.session import create_db_engine
from app.demo import DEMO_WORKSPACE_NAME

# The step 17 schema of the two tables that gain columns
OLD_SCHEMA = """
CREATE TABLE workspaces (
    id VARCHAR(32) PRIMARY KEY, name VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL
);
CREATE TABLE conversations (
    id VARCHAR(32) PRIMARY KEY,
    workspace_id VARCHAR(32) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL, created_at DATETIME NOT NULL
);
INSERT INTO workspaces VALUES ('demo', '{demo}', '2026-10-01 10:00:00');
INSERT INTO workspaces VALUES ('acme', 'Acme Dental', '2026-10-01 10:00:00');
"""


def make_old_db(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data_dir / "app.db") as connection:
        connection.executescript(OLD_SCHEMA.format(demo=DEMO_WORKSPACE_NAME))


def test_missing_columns_are_added_to_an_existing_database(tmp_path: Path) -> None:
    make_old_db(tmp_path)

    engine = create_db_engine(tmp_path)

    columns = {c["name"] for c in inspect(engine).get_columns("workspaces")}
    assert {"is_demo", "owner_hash", "expires_at"} <= columns
    assert "owner_hash" in {c["name"] for c in inspect(engine).get_columns("conversations")}
    assert "llm_usage_days" in inspect(engine).get_table_names()


def test_the_existing_demo_workspace_is_flagged_by_name_once(tmp_path: Path) -> None:
    make_old_db(tmp_path)

    create_db_engine(tmp_path)

    with sqlite3.connect(tmp_path / "app.db") as connection:
        flags = dict(connection.execute("SELECT id, is_demo FROM workspaces").fetchall())
    assert flags == {"demo": 1, "acme": 0}


def test_starting_twice_is_harmless(tmp_path: Path) -> None:
    make_old_db(tmp_path)
    create_db_engine(tmp_path).dispose()

    create_db_engine(tmp_path)  # nothing left to add; must not raise
