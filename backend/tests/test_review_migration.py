from alembic import command
from sqlalchemy import text

from conftest import login
from tracker.db import engine
from tracker.schema import REVIEWS


def test_upgrade_preserves_existing_review_and_maturity(migrated_database, client):
    config = migrated_database
    command.downgrade(config, "dde01f06eaf1")
    person = login(client)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO boards (id, identifier, base, active, schematic_ri_id, maturity,
                                created_at, updated_at, created_by, updated_by)
            VALUES (101, 'SRC00001', 'SRC00001', true, :person, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :person, :person)
        """), {"person": person["id"]})
        conn.execute(text("""
            INSERT INTO reviews (id, board_id, kind, state, date)
            VALUES (52, 101, :kind, 'Complete', NULL)
        """), {"kind": REVIEWS[0]})

    command.upgrade(config, "head")
    board = client.get("/api/boards/101").json()
    assert board["maturity"] == 0
    assert board["reviews"] == [
        {"id": 52, "board_id": 101, "kind": REVIEWS[0], "state": "Complete", "date": None, "url": None}
    ]
