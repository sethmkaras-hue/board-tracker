import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


URL = os.getenv("DATABASE_URL", "postgresql+psycopg://tracker:tracker@localhost/tracker")
engine = create_engine(URL, pool_pre_ping=True, hide_parameters=True)
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
