import os
from collections.abc import Sequence
from typing import Any

from flask_sqlalchemy import SQLAlchemy

from .settings import Settings

db = SQLAlchemy()
try:
    from flask_migrate import Migrate

    migrate = Migrate()
except Exception:
    migrate = None


class DBIntegrityError(Exception):
    """Compatibility error used by existing route code."""


def get_database_url() -> str:
    db_url = Settings.DATABASE_URL or os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is required.")
    # Render provides postgres://, SQLAlchemy expects postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url


class CompatCursor:
    """DB-API compatibility cursor backed by SQLAlchemy engine connection."""

    def __init__(self, cursor: Any):
        self._cursor = cursor
        self.lastrowid = None

    @staticmethod
    def _adapt_query(query: str) -> str:
        # Existing codebase uses sqlite-style placeholders.
        return query.replace("?", "%s")

    def execute(self, query: str, params: Sequence[Any] | None = None):
        query_pg = self._adapt_query(query)
        try:
            self._cursor.execute(query_pg, tuple(params or ()))
            if query_pg.strip().upper().startswith("INSERT"):
                try:
                    self._cursor.execute("SELECT LASTVAL()")
                    row = self._cursor.fetchone()
                    self.lastrowid = row[0] if row else None
                except Exception:
                    self.lastrowid = None
            return self
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "integrity" in name or "unique" in str(exc).lower():
                raise DBIntegrityError(str(exc)) from exc
            raise

    class CompatRow:
        """Row object supporting both index and column-name access."""

        def __init__(self, columns: list[str], values: Sequence[Any]):
            self._columns = columns
            self._values = tuple(values)
            self._index = {name: idx for idx, name in enumerate(columns)}

        def __getitem__(self, key):
            if isinstance(key, int):
                return self._values[key]
            if isinstance(key, str):
                return self._values[self._index[key]]
            raise KeyError(key)

        def get(self, key: str, default=None):
            idx = self._index.get(key)
            if idx is None:
                return default
            return self._values[idx]

        def keys(self):
            return list(self._columns)

        def values(self):
            return list(self._values)

        def items(self):
            return [(name, self._values[idx]) for idx, name in enumerate(self._columns)]

        def __iter__(self):
            return iter(self._values)

        def __len__(self):
            return len(self._values)

        def __repr__(self):
            return f"CompatRow({dict(self.items())!r})"

    def _to_mapping(self, row: Any):
        if row is None:
            return None
        if isinstance(row, self.CompatRow):
            return row
        cols = [desc[0] for desc in self._cursor.description or []]
        if isinstance(row, dict):
            values = [row.get(col) for col in cols]
            return self.CompatRow(cols, values)
        return self.CompatRow(cols, row)

    def fetchone(self):
        return self._to_mapping(self._cursor.fetchone())

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [self._to_mapping(row) for row in rows]


class CompatConnection:
    """Compatibility wrapper expected by route layer."""

    def __init__(self, raw_connection: Any):
        self._conn = raw_connection

    def cursor(self) -> CompatCursor:
        return CompatCursor(self._conn.cursor())

    def execute(self, query: str, params: Sequence[Any] | None = None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def get_db() -> CompatConnection:
    # Uses SQLAlchemy engine only; no direct psycopg2 dependency in app code.
    raw_connection = db.engine.raw_connection()
    return CompatConnection(raw_connection)


def init_db(app) -> None:
    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    db.init_app(app)
    if migrate is not None:
        migrate.init_app(app, db)

    with app.app_context():
        # Import models lazily so model -> database imports don't create cycles.
        from . import models  # noqa: F401

        if os.getenv("AUTO_CREATE_TABLES", "1").strip().lower() in {"1", "true", "yes", "on"}:
            db.create_all()