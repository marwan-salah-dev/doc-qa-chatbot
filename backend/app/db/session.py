from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Workspace
from app.demo import DEMO_WORKSPACE_NAME


def create_db_engine(data_dir: Path) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{(data_dir / 'app.db').as_posix()}",
        # FastAPI runs sync routes and background tasks on worker threads
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        # SQLite ignores foreign keys (and ON DELETE CASCADE) unless asked
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


# Columns added after a table's first release. create_all only creates missing tables, so a
# database made by an older version (the Docker volume) gets these with ALTER TABLE instead.
_ADDED_COLUMNS = {
    "workspaces": {
        "is_demo": "BOOLEAN NOT NULL DEFAULT 0",
        "owner_hash": "VARCHAR(64)",
        "expires_at": "DATETIME",
    },
    "conversations": {"owner_hash": "VARCHAR(64)"},
}


def _add_missing_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name in existing:
                    continue
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                if (table, name) == ("workspaces", "is_demo"):
                    # Before the flag, the demo workspace was recognised by its name (step 13)
                    connection.execute(
                        update(Workspace)
                        .where(Workspace.name == DEMO_WORKSPACE_NAME)
                        .values(is_demo=True)
                    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
