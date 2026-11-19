"""Test deployment connections without printing credentials or remote responses."""
import argparse
from email.message import EmailMessage
import os
import socket
from urllib.request import urlopen

from ldap3 import Connection
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from .auth import ldap_server, validate_config
from .db import Base, engine
from . import models
from .worker import smtp_connection


def check_database():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()


def check_dns():
    addresses = socket.getaddrinfo(engine.url.host, engine.url.port, type=socket.SOCK_STREAM)
    print("Resolved database addresses:", ", ".join(sorted({entry[4][0] for entry in addresses})))


def check_schema():
    revisions = ScriptDirectory.from_config(Config("alembic.ini"))
    with engine.connect() as connection:
        missing = Base.metadata.tables.keys() - set(inspect(connection).get_table_names())
        if missing:
            raise RuntimeError(f"Missing application tables: {', '.join(sorted(missing))}")
        if set(MigrationContext.configure(connection).get_current_heads()) != set(revisions.get_heads()):
            raise RuntimeError("Database is not at the expected Alembic revision")
    print(f"Verified {len(Base.metadata.tables)} application tables and the Alembic revision")


def check_http():
    with urlopen("http://127.0.0.1:8000/api/health", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("HTTP health check failed")


def check_ldap():
    validate_config()
    server, mode = ldap_server()
    with Connection(server, os.environ["LDAP_BIND_DN"], os.environ["LDAP_BIND_PASSWORD"],
                    auto_bind=mode, receive_timeout=8, raise_exceptions=True):
        pass


def check_smtp(recipient):
    with smtp_connection() as relay:
        if recipient:
            message = EmailMessage()
            message["From"] = os.environ["SMTP_FROM"]
            message["To"] = recipient
            message["Subject"] = "Board Tracker relay test"
            message.set_content("Board Tracker SMTP delivery check.")
            relay.send_message(message)
        elif relay.noop()[0] != 250:
            raise RuntimeError("SMTP NOOP failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("db", "dns", "schema", "http", "ldap", "smtp"))
    parser.add_argument("--send-to", help="Send a test message to this address (SMTP only)")
    args = parser.parse_args()
    if args.send_to and args.service != "smtp":
        parser.error("--send-to requires smtp")
    try:
        if args.service == "smtp":
            check_smtp(args.send_to)
        elif args.service == "dns":
            check_dns()
        elif args.service == "schema":
            check_schema()
        elif args.service == "http":
            check_http()
        elif args.service == "ldap":
            check_ldap()
        else:
            check_database()
    except Exception as error:
        state = getattr(getattr(error, "orig", None), "sqlstate", None)
        hint = f", SQLSTATE {state}" if state else ""
        parser.exit(1, f"{args.service}: failed ({type(error).__name__}{hint})\n")
    print(f"{args.service}: OK")


if __name__ == "__main__":
    main()
