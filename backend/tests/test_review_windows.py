from datetime import timedelta
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import pytest

from conftest import login
from test_workflows import create, edit
from tracker.db import Session, now
from tracker.main import app
from tracker.models import Digest, ReviewAssignment
from tracker.schema import REVIEWS
from tracker.worker import generate


def review_payload(board, kind=REVIEWS[0]):
    return next(review for review in board["reviews"] if review["kind"] == kind)


def test_review_start_defaults_overrides_and_meeting_edits(client):
    person = login(client)
    board = create(client, person)
    review = review_payload(board)
    endpoint = f"/api/boards/{board['id']}/reviews/{quote(review['kind'])}"
    assert review["date"] == "2025-05-15"
    assert review["review_start_date"] is None
    assert review["effective_review_start_date"] == "2025-05-08"

    def save(changes, expected):
        return edit(client, endpoint, changes, expected, "PUT")

    changed = save({"date": "2024-03-06"}, {"date": review["date"]})
    assert changed.status_code == 200
    assert review_payload(changed.json())["effective_review_start_date"] == "2024-02-28"
    override = save({"review_start_date": "2024-03-01"}, {"review_start_date": None})
    assert review_payload(override.json())["review_start_date"] == "2024-03-01"
    assert review_payload(override.json())["effective_review_start_date"] == "2024-03-01"
    moved = save({"date": "2024-03-09"}, {"date": "2024-03-06"})
    assert review_payload(moved.json())["effective_review_start_date"] == "2024-03-01"
    assert save({"date": "2024-02-28"}, {"date": "2024-03-09"}).status_code == 422
    assert save({"date": None}, {"date": "2024-03-09"}).status_code == 422
    cleared = save({"review_start_date": None}, {"review_start_date": "2024-03-01"})
    assert review_payload(cleared.json())["effective_review_start_date"] == "2024-03-02"
    unscheduled = save({"date": None}, {"date": "2024-03-09"})
    assert review_payload(unscheduled.json())["effective_review_start_date"] is None
    assert save({"review_start_date": "2024-03-09"}, {"review_start_date": None}).status_code == 422


def test_assignments_are_independent_validated_and_audited(client):
    actor = login(client)
    with TestClient(app) as other:
        reviewer = login(other, "reviewer")
    first = {"reviewer_id": actor["id"]}
    second = {"reviewer_id": reviewer["id"]}
    board = create(client, actor, reviews={
        kind: dict(date="2025-05-15", **(
            {"review_start_date": "2025-05-15", "assignments": [second, first]} if kind == REVIEWS[0]
            else {"assignments": [first]} if kind == REVIEWS[1] else {}
        )) for kind in REVIEWS
    })
    review = review_payload(board)
    assert review["effective_review_start_date"] == review["date"]
    assert [item["reviewer_id"] for item in review["assignments"]] == [actor["id"], reviewer["id"]]
    baseline = [{**item, "allocation_status": "Not Allocated"} for item in (first, second)]
    endpoint = f"/api/boards/{board['id']}/reviews/{quote(review['kind'])}"

    def save(assignments, expected=baseline):
        return edit(client, endpoint, {"assignments": assignments}, {"assignments": expected}, "PUT")

    assert save([first, first]).status_code == 422
    assert save([{"reviewer_id": 123456}]).status_code == 422
    assert save([{**first, "allocation_status": "External"}]).status_code == 422
    allocated = [{**first, "allocation_status": "Allocated"}, baseline[1]]
    updated = save(allocated)
    assert updated.status_code == 200
    assert [item["allocation_status"] for item in review_payload(updated.json())["assignments"]] == ["Allocated", "Not Allocated"]
    assert review_payload(updated.json(), REVIEWS[1])["assignments"][0]["allocation_status"] == "Not Allocated"
    assert save([second]).status_code == 409
    removed = save([first], allocated)
    assert removed.status_code == 200
    assert [item["allocation_status"] for item in review_payload(removed.json())["assignments"]] == ["Allocated"]

    with pytest.raises(IntegrityError), Session.begin() as db:
        db.add(ReviewAssignment(review_id=review["id"], reviewer_id=actor["id"]))
        db.flush()
    events = client.get("/api/activity", params={"board_id": board["id"]}).json()["items"]
    assert any(item["action"] == "unassign" and "Reviewer" in item["previous"] for item in events)
    assert any(item["field"].endswith(".allocation_status") and item["value"].endswith("· Allocated") for item in events)
    assert any(item["field"].endswith(".review_start_date") and item["value"] == "2025-05-15" for item in events)
    assert any(item["action"] == "assign" and "Reviewer" in item["value"] for item in events)


def test_planning_audit_changes_do_not_change_digests(client):
    actor = login(client)
    with TestClient(app) as other:
        reviewer = login(other, "reviewer")
    board = create(client, actor)
    endpoint = f"/api/boards/{board['id']}/reviews/{quote(REVIEWS[0])}"
    changes = {"review_start_date": "2025-05-04", "assignments": [{"reviewer_id": reviewer["id"]}]}
    assert edit(client, endpoint, changes, {"review_start_date": None, "assignments": []}, "PUT").status_code == 200
    with Session() as db:
        assert generate(db, now() + timedelta(days=2)) == 1
        digest = db.scalar(select(Digest))
        assert digest.person_id == actor["id"]
        assert not any(event["field"].endswith((".review_start_date", ".reviewer")) for event in digest.payload)
