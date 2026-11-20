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
        {"id": 52, "board_id": 101, "kind": REVIEWS[0], "state": "Complete", "date": None, "url": None,
         "review_start_date": None, "effective_review_start_date": None, "assignments": []}
    ]


def test_review_window_migration_keeps_meeting_and_existing_audit(migrated_database, client):
    person = login(client)
    command.downgrade(migrated_database, "9f2618a85e01")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO boards (id, identifier, base, active, schematic_ri_id,
                                created_at, updated_at, created_by, updated_by)
            VALUES (101, 'SRC00001', 'SRC00001', true, :person,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :person, :person)
        """), {"person": person["id"]})
        conn.execute(text("""
            INSERT INTO reviews (id, board_id, kind, state, date, url)
            VALUES (52, 101, :kind, 'Scheduled', '2024-03-06', 'https://example.test/review')
        """), {"kind": REVIEWS[0]})
    previous = client.get("/api/activity").json()
    command.upgrade(migrated_database, "head")
    saved = client.get("/api/boards/101").json()["reviews"][0]
    assert saved["date"] == "2024-03-06"
    assert saved["url"] == "https://example.test/review"
    assert saved["review_start_date"] is None
    assert saved["effective_review_start_date"] == "2024-02-28"
    assert saved["assignments"] == []
    assert client.get("/api/activity").json() == previous
