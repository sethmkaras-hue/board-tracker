import hashlib
import logging
import os
import re
import secrets
import ssl
import time
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from ldap3 import AUTO_BIND_NO_TLS, AUTO_BIND_TLS_BEFORE_BIND, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import select

from .db import database, lock_writes
from .models import LoginAttempt, Person, SessionRecord

log = logging.getLogger(__name__)


def enabled(name):
    return os.getenv(name, "").lower() in ("true", "1")


def validate_config():
    if os.getenv("APP_ENV", "production") == "production":
        if enabled("DEV_AUTH"):
            raise RuntimeError("DEV_AUTH must be disabled in production")
        for name in ("LDAP_URL", "LDAP_BASE_DN", "LDAP_BIND_DN", "LDAP_BIND_PASSWORD"):
            if not os.getenv(name):
                raise RuntimeError(f"Missing {name}")
        ldap_server()


def ldap_server():
    url = urlsplit(os.environ["LDAP_URL"])
    starttls = url.scheme == "ldap" and enabled("LDAP_STARTTLS")
    if url.scheme != "ldaps" and not starttls:
        raise RuntimeError("LDAP requires LDAPS or StartTLS")
    if not url.hostname or url.username or url.password:
        raise RuntimeError("Invalid LDAP URL")
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=os.getenv("LDAP_CA_FILE") or None)
    return Server(url.hostname, port=url.port, use_ssl=not starttls, tls=tls, connect_timeout=6), (
        AUTO_BIND_TLS_BEFORE_BIND if starttls else AUTO_BIND_NO_TLS
    )


def authenticate(username, password):
    if not password:
        return None
    if enabled("DEV_AUTH") and os.getenv("APP_ENV") == "development":
        if secrets.compare_digest(password, os.getenv("DEV_PASSWORD", "")):
            return username.replace(".", " ").title(), f"{username}@example.test"
        return None
    server, mode = ldap_server()
    attribute = os.getenv("LDAP_USERNAME_ATTRIBUTE", "sAMAccountName")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", attribute):
        raise RuntimeError("Invalid LDAP username attribute")
    try:
        with Connection(server, os.environ["LDAP_BIND_DN"], os.environ["LDAP_BIND_PASSWORD"],
                        auto_bind=mode, receive_timeout=8, raise_exceptions=True) as lookup:
            lookup.search(os.environ["LDAP_BASE_DN"], f"({attribute}={escape_filter_chars(username)})",
                          attributes=["mail", "displayName"], size_limit=2)
            if len(lookup.entries) != 1:
                return None
            entry = lookup.entries[0]
            with Connection(server, entry.entry_dn, password, auto_bind=mode,
                            receive_timeout=8, raise_exceptions=True):
                return entry.displayName.value or username, entry.mail.value
    except LDAPException as exc:
        if type(exc).__name__ == "LDAPInvalidCredentialsResult":
            return None
        log.warning("LDAP operation failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Directory service unavailable") from None


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def limit_login(db, address):
    key = token_hash(address)
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
    current = int(time.time())
    row = db.get(LoginAttempt, key)
    if row is None:
        db.add(LoginAttempt(key=key, count=1, expires=current + 300))
    elif row.expires <= current:
        row.count, row.expires = 1, current + 300
    elif row.count >= 15:
        raise HTTPException(429, "Too many login attempts. Try again shortly.")
    else:
        row.count += 1
    db.commit()


def session(request: Request, db=Depends(database)):
    token = request.cookies.get("tracker_session")
    record = db.get(SessionRecord, token_hash(token)) if token else None
    if not record or record.expires <= int(time.time()):
        raise HTTPException(401, "Please sign in")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(record.csrf, supplied):
            raise HTTPException(403, "Invalid CSRF token")
        lock_writes(db)
    return record


def user(record=Depends(session), db=Depends(database)):
    return db.get(Person, record.person_id)


def admin(person=Depends(user)):
    if not person.admin:
        raise HTTPException(403, "Administrator privileges required")
    return person
