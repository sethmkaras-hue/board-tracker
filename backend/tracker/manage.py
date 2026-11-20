import argparse
import re

from sqlalchemy import select

from .auth import enabled
from .db import Session, lock_writes
from .models import Board, Person, Program, Review
from .schema import REVIEWS
from .service import apply_board, audit, commit


def bootstrap(db, username):
    person = db.scalar(select(Person).where(Person.username == username.lower()))
    if not person or not person.email:
        raise SystemExit("Sign in through LDAP first and ensure the resulting account has a directory email.")
    if not person.admin:
        person.admin = True
        audit(db, person, "person", person.id, "bootstrap", "admin", False, True)
        commit(db)


def seed(db):
    import os

    if os.getenv("APP_ENV") != "development" or not enabled("DEV_AUTH"):
        raise SystemExit("Synthetic data requires development authentication.")
    usernames = ("demo.admin", "maya.chen", "alex.morgan", "jordan.lee")
    people = []
    for username in usernames:
        person = db.scalar(select(Person).where(Person.username == username))
        if not person:
            person = Person(username=username, display_name=username.replace(".", " ").title(),
                            email=f"{username}@example.test", admin=username == "demo.admin")
            db.add(person)
            db.flush()
            audit(db, person, "person", person.id, "seed", "directory_profile", value={"username": username})
        people.append(person)
    for name in ("Synthetic · Atlas", "Synthetic · Horizon", "Synthetic · Meridian"):
        if not db.scalar(select(Program).where(Program.name == name)):
            program = Program(name=name, managers=[people[2]], deputies=[people[3]], notes="Synthetic development program.")
            db.add(program)
            db.flush()
            audit(db, people[0], "program", program.id, "seed", "name", value=name)
    programs = list(db.scalars(select(Program).where(Program.name.startswith("Synthetic ·")).order_by(Program.name)))
    types = ("Digital", "RF", "Power", "External IO", "Backplane", "Antenna")
    levels = ("Low", "Medium", "High", "Very High")
    states = ("Not Started", "Scheduled", "In-Review", "Complete")
    for index in range(18):
        identifier = f"SRC{91001 + index:05}"
        if db.scalar(select(Board).where(Board.identifier == identifier)):
            continue
        board = Board(created_by=people[0].id)
        apply_board(db, board, people[0], {
            "identifier": identifier, "active": index not in (10, 15, 17),
            "schematic_ri_id": people[index % len(people)].id, "board_type": types[index % len(types)],
            "complexity": levels[index % 4], "maturity": 1 + index % 4,
            "program_ids": [programs[index % len(programs)].id],
            "notes": "Synthetic development record.",
        }, creating=True)
        board.reviews = [Review(kind=kind, state=states[(index + offset) % 4]) for offset, kind in enumerate(REVIEWS)]
    commit(db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap-admin").add_argument("username")
    commands.add_parser("seed")
    args = parser.parse_args()
    with Session() as db:
        lock_writes(db)
        if args.command == "seed":
            seed(db)
        elif not re.fullmatch(r"[A-Za-z0-9._@-]{1,128}", args.username):
            parser.error("Invalid directory username")
        else:
            bootstrap(db, args.username)
