import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL as DatabaseURL
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def database_url():
    # Keep URL overrides for local development, tests, and existing installations.
    if override := os.getenv("DATABASE_URL"):
        return override
    query = {"sslmode": os.getenv("POSTGRES_SSLMODE", "prefer"), "connect_timeout": "5"}
    if root := os.getenv("POSTGRES_SSLROOTCERT"):
        query["sslrootcert"] = root
    return DatabaseURL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "circuit_card_tracking"),
        query=query,
    )


engine = create_engine(database_url(), pool_pre_ping=True, hide_parameters=True)
Session = sessionmaker(engine, expire_on_commit=False)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


def lock_writes(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(687532104)"))


def database():
    with Session() as db:
        yield db
