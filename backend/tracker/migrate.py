"""Apply production migrations and provision a least-privilege runtime role."""
import os

from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from .db import Base, engine
from . import models


def migrate():
    runtime = make_url(os.environ["APP_DATABASE_URL"])
    if not runtime.username or not runtime.password or runtime.username == engine.url.username:
        raise SystemExit("The application requires a separate password-protected PostgreSQL role.")
    if runtime.database != engine.url.database or runtime.host != engine.url.host or runtime.port != engine.url.port:
        raise SystemExit("Migration and runtime URLs must point to the same database.")
    command.upgrade(Config("alembic.ini"), "head")
    role = sql.Identifier(runtime.username)
    password = sql.Literal(runtime.password)
    with engine.begin() as connection, connection.connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname = %s",
                       (runtime.username,))
        existing = cursor.fetchone()
        if existing and existing[0]:
            raise SystemExit("The runtime role must not have elevated PostgreSQL privileges.")
        if not existing:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(role, password))
        else:
            cursor.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(role, password))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        cursor.execute(sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {}").format(role))
        for table in Base.metadata.sorted_tables:
            permissions = sql.SQL("SELECT, INSERT") if table.name == "audit_events" else sql.SQL("SELECT, INSERT, UPDATE, DELETE")
            if table.name == "audit_events":
                cursor.execute(sql.SQL("REVOKE ALL ON TABLE public.audit_events FROM {}").format(role))
            cursor.execute(sql.SQL("GRANT {} ON TABLE public.{} TO {}").format(permissions, sql.Identifier(table.name), role))
    check = create_engine(runtime)
    try:
        with check.connect() as connection:
            connection.exec_driver_sql("SELECT id FROM boards LIMIT 0")
    finally:
        check.dispose()


if __name__ == "__main__":
    migrate()
