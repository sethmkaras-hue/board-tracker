import logging
import os
import smtplib
import ssl
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from .auth import enabled
from .db import Session, lock_writes, now
from .models import Audit, Board, Digest, DigestCycle, Person, Setting
from .service import recipients

log = logging.getLogger(__name__)


def generate(db, instant):
    lock_writes(db)
    config = db.get(Setting, "notification_timezone")
    zone = ZoneInfo(config.value if config else os.getenv("NOTIFICATION_TIMEZONE", "UTC"))
    local_day = instant.astimezone(zone).date()
    day = local_day.isoformat()
    if db.get(DigestCycle, day):
        return 0
    cutoff = datetime.combine(local_day, time.min, zone).astimezone(timezone.utc)
    prior = db.scalar(select(DigestCycle).order_by(DigestCycle.through_id.desc()).limit(1))
    through = prior.through_id if prior else 0
    events = list(db.scalars(select(Audit).where(Audit.id > through, Audit.timestamp < cutoff).order_by(Audit.id)))
    # Commit order is enforced by the advisory lock. Stop at the first audit beyond midnight.
    boundary = db.scalar(select(Audit.id).where(Audit.id > through, Audit.timestamp >= cutoff).order_by(Audit.id).limit(1))
    if boundary:
        events = [event for event in events if event.id < boundary]
    grouped = defaultdict(list)
    cache = {}
    for event in events:
        if event.board_id is None:
            continue
        if event.board_id not in cache:
            cache[event.board_id] = db.get(Board, event.board_id)
        board = cache[event.board_id]
        ids = event.deletion_recipients if event.action == "delete" else recipients(board)
        for person_id in ids:
            grouped[person_id].append({
                "board_id": event.board_id, "board": event.board_label, "action": event.action,
                "field": event.field, "previous": event.previous, "value": event.value,
                "username": event.username, "timestamp": (event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)).isoformat(),
            })
    for person_id, payload in grouped.items():
        person = db.get(Person, person_id)
        status = "queued" if person.email else "in_app_only"
        db.add(Digest(day=day, person_id=person_id, payload=payload, status=status))
    db.add(DigestCycle(day=day, through_id=events[-1].id if events else through))
    db.commit()
    return len(grouped)


def send(digest, person):
    import json

    base = os.environ["PUBLIC_URL"].rstrip("/")
    sender = os.environ["SMTP_FROM"]
    message = EmailMessage()
    message["From"] = sender
    message["To"] = formataddr((person.display_name, person.email))
    message["Subject"] = f"Circuit card changes · {digest.day}"
    message["Message-ID"] = f"<board-tracker-{digest.id}@{sender.rsplit('@', 1)[-1]}>"
    lines = []
    for event in digest.payload:
        old, new = (json.dumps(event[k], ensure_ascii=False) for k in ("previous", "value"))
        lines.append(f"{event['board']} · {event['action']} · {event['field']}\n"
                     f"{old} → {new}\n{event['username']} · {event['timestamp']}\n{base}/boards/{event['board_id']}")
    message.set_content("\n\n".join(lines))
    with smtp_connection() as relay:
        relay.send_message(message)


@contextmanager
def smtp_connection():
    use_starttls = "SMTP_STARTTLS" not in os.environ or enabled("SMTP_STARTTLS")
    mode = os.getenv("SMTP_TLS") or ("starttls" if use_starttls else "none")
    username = os.getenv("SMTP_USERNAME")
    if username and mode == "none":
        raise ValueError("SMTP credentials require TLS")
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT") or ("465" if mode == "implicit" else "25"))
    context = ssl.create_default_context(cafile=os.getenv("SMTP_CA_FILE") or None) if mode != "none" else None
    if mode == "implicit":
        relay = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    elif mode in ("starttls", "none"):
        relay = smtplib.SMTP(host, port, timeout=15)
    else:
        raise ValueError("Invalid SMTP_TLS")
    with relay:
        if mode == "starttls":
            relay.starttls(context=context)
        if username:
            relay.login(username, os.environ["SMTP_PASSWORD"])
        yield relay


def deliver(db, instant):
    for _ in range(50):
        query = select(Digest).where(Digest.status.in_(("queued", "retry")), Digest.next_attempt <= instant)
        digest = db.scalar(query.order_by(Digest.next_attempt, Digest.id).limit(1).with_for_update(skip_locked=True))
        if not digest:
            break
        digest.attempts += 1
        try:
            send(digest, db.get(Person, digest.person_id))
            digest.status, digest.error = "sent", None
        except (OSError, smtplib.SMTPException, ValueError, KeyError) as error:
            digest.status = "failed" if digest.attempts >= 10 else "retry"
            digest.error = type(error).__name__
            digest.next_attempt = instant + timedelta(minutes=min(2 ** digest.attempts, 360))
            log.warning("Digest %s delivery failed (%s)", digest.id, digest.error)
        db.commit()


def run():
    if os.getenv("APP_ENV", "production") == "development" and not enabled("DEV_NOTIFICATIONS"):
        return
    instant = now()
    with Session() as db:
        generate(db, instant)
    with Session() as db:
        deliver(db, instant)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = BlockingScheduler(timezone=timezone.utc)
    scheduler.add_job(run, "cron", minute="*", coalesce=True, max_instances=1, misfire_grace_time=120)
    scheduler.start()
