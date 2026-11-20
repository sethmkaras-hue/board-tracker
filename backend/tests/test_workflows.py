from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import quote
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from conftest import login
from tracker import auth, worker
from tracker.db import Session, engine, now
from tracker.main import app
from tracker.models import Board, Digest, DigestCycle, Review
from tracker.schema import REVIEWS


REVIEW_DATE = "2025-05-15"


def board_payload(person, identifier="SRC00123A"):
    return {"identifier": identifier, "schematic_ri_id": person["id"],
            "reviews": {kind: {"date": REVIEW_DATE} for kind in REVIEWS}}


def create(client, person, identifier="SRC00123A", **fields):
    result = client.post("/api/boards", json={**board_payload(person, identifier), **fields})
    assert result.status_code == 201, result.text
    return result.json()


def edit(client, path, changes, expected, method="PATCH", overwrite=False):
    return client.request(method, path, json={"changes":changes,"expected":expected,"overwrite":overwrite})


def test_validation_and_authorization(client):
    assert client.get("/api/boards").status_code == 401
    person = login(client)
    for body in (
        {}, {"identifier":"SRC00123"}, {"schematic_ri_id":person["id"]},
        {"identifier":"src00123","schematic_ri_id":person["id"]},
        {"identifier":"SRC00123ZZ","schematic_ri_id":person["id"]},
        {"identifier":"SRC00123","schematic_ri_id":person["id"],"notes":"é"*2049},
        {"identifier":"SRC00123","schematic_ri_id":person["id"],"overview_url":"javascript:alert(1)"},
    ):
        assert client.post("/api/boards", json={"reviews": board_payload(person)["reviews"], **body}).status_code == 422
    board = create(client, person, notes="é"*2048)
    assert board["active"] is True
    assert len(board["reviews"]) == 5
    assert client.post("/api/boards",json=board_payload(person, board["identifier"])).status_code == 409
    path = f"/api/boards/{board['id']}"
    assert client.post(path+"/lifecycle",json={"action":"delete"}).status_code == 403
    assert client.get("/api/admin/status").status_code == 403
    assert client.post("/api/boards", headers={"X-CSRF-Token":"wrong"},json={"identifier":"SRC00123","schematic_ri_id":person["id"]}).status_code == 403


def test_lifecycle_and_field_conflicts(client):
    actor = login(client, "maintainer", grant=True)
    first = create(client, actor)
    second = create(client, actor, "SRC00123B")
    path = f"/api/boards/{first['id']}"
    assert client.get(path).json()["revisions"] == [{"id":second["id"],"identifier":"SRC00123B"}]
    assert edit(client,path,{"notes":"first"},{"notes":None}).status_code == 200
    with TestClient(app) as other:
        login(other,"reviewer")
        result = edit(other,path,{"active":False},{"active":True})
        assert result.json()["notes"] == "first"
        result = edit(other,path,{"notes":"second"},{"notes":None})
        assert result.status_code == 409
        assert result.json()["detail"]["fields"]["notes"] == {"current":"first","proposed":"second"}
        assert edit(other,path,{"notes":"second"},{"notes":None},overwrite=True).status_code == 200
    assert client.post(path+"/lifecycle",json={"action":"delete"}).status_code == 200
    assert client.get("/api/boards").json()["total"] == 1
    assert client.get("/api/boards?deleted=true").json()["total"] == 1
    with TestClient(app) as other:
        login(other,"reviewer")
        assert other.get(path).status_code == 404
        assert other.get("/api/boards?deleted=true").status_code == 403
    assert client.post(path+"/lifecycle",json={"action":"restore"}).status_code == 200
    events = client.get("/api/activity",params={"board_id":first["id"]}).json()["items"]
    assert any(row["field"] == "notes" and row["previous"] == "first" and row["value"] == "second" and row["username"] == "reviewer" for row in events)
    assert {"delete","restore"} <= {row["action"] for row in events}
    if engine.dialect.name == "postgresql":
        with pytest.raises(DBAPIError, match="append-only"), Session.begin() as db:
            db.execute(text("DELETE FROM audit_events"))


def test_program_parent_review_filter_and_exports(client):
    person = login(client)
    program = client.post("/api/programs",json={"name":"Example","manager_ids":[person["id"]]}).json()
    assert program["manager_ids"] == [person["id"]]
    assert client.post("/api/programs",json={"name":"Example","manager_ids":[person["id"]]}).status_code == 409
    assert edit(client,f"/api/programs/{program['id']}",{"name":"Renamed"},{"name":"Example"}).status_code == 200
    board = create(client,person,board_type="RF",complexity="High",notes="=HYPERLINK()",overview_url="https://example.test/spec",program_ids=[program["id"]])
    create(client,person,"SRC00124",board_type="RF",complexity="Low")
    create(client,person,"SRC00125",board_type="Power",complexity="High")
    path = f"/api/boards/{board['id']}"
    for name, units in (("Top",0),("Bottom",3)):
        result = client.post(path+"/parents",json={"name":name,"quantity":units,"url":"https://example.test/parent"})
        assert result.status_code == 201, result.text
    assert client.post(path+"/parents",json={"name":"Bad","quantity":-1}).status_code == 422
    assert client.get("/api/parents/options").json() == ["Bottom", "Top"]
    assert client.get("/api/boards",params=[("parent","Top"),("parent","Unrelated")]).json()["total"] == 1
    parent = result.json()["parents"][0]
    assert edit(client,path+"/parents/"+str(parent["id"]),{"quantity":1},{"quantity":0}).status_code == 200
    verify = path+"/reviews/"+quote(REVIEWS[-1])
    assert edit(client,verify,{"state":"Complete","date":"2026-01-01"},{"state":"Not Started","date":REVIEW_DATE},"PUT").status_code == 200
    filters = [("board_type","RF"),("board_type","Antenna"),("complexity","High"),("verification","Complete"),("review_from","2026-01-01"),("review_to","2026-01-01")]
    assert client.get("/api/boards",params=filters).json()["total"] == 1
    today = now().date().isoformat()
    activity={"activity_from":today,"activity_to":today,"board_type":"RF","complexity":"High"}
    assert client.get("/api/boards",params=activity).json()["total"] == 1
    assert edit(client,path,{"complexity":"Medium"},{"complexity":"High"}).status_code == 200
    assert client.get("/api/boards",params=activity).json()["total"] == 0
    assert client.get("/api/programs/"+str(program["id"])).json()["boards"][0]["identifier"] == board["identifier"]
    params={"program_ids":program["id"],"limit":1,"page":2}
    response = client.get("/api/export/boards",params=params)
    assert response.status_code == 200
    workbook=load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["Boards","Parent Systems","Reviews","Programs"]
    assert workbook["Boards"].max_row == 2
    assert any(c.hyperlink and c.hyperlink.target == "https://example.test/spec" for c in workbook["Boards"][2])
    assert any(c.value == "'=HYPERLINK()" for c in workbook["Boards"][2])
    assert workbook["Parent Systems"].max_row == 3
    assert "'=HYPERLINK()" in client.get("/api/export/boards",params={**params,"fmt":"csv"}).text
    assert client.get("/api/export/activity").status_code == 200
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["active"] == 3
    assert dashboard["types"] == {"RF":2,"Power":1}
    assert dashboard["verification"] == {"Not Started":2,"Complete":1}
    assert dashboard["programs"] == {"Renamed":1}


def test_directory_mock_and_production_rejection(monkeypatch):
    monkeypatch.setenv("APP_ENV","production")
    with pytest.raises(RuntimeError, match="disabled"):
        auth.validate_config()
    monkeypatch.setenv("DEV_AUTH","0")
    monkeypatch.setenv("LDAP_BIND_DN","cn=lookup")
    monkeypatch.setenv("LDAP_BIND_PASSWORD","lookup")
    monkeypatch.setenv("LDAP_BASE_DN","dc=example")
    monkeypatch.setattr(auth,"ldap_server",lambda:("server","tls"))
    lookup=MagicMock()
    lookup.__enter__.return_value.entries=[SimpleNamespace(entry_dn="cn=user",displayName=SimpleNamespace(value="Example"),mail=SimpleNamespace(value="test@example.test"))]
    bind=MagicMock()
    factory=MagicMock(side_effect=[lookup,bind])
    monkeypatch.setattr(auth,"Connection",factory)
    assert auth.authenticate("x*)(uid=*)","user-password") == ("Example","test@example.test")
    assert "\\2a" in lookup.__enter__.return_value.search.call_args.args[1]
    assert factory.call_args.args == ("server","cn=user","user-password")


def test_midnight_dedup_deletion_and_retry(client,monkeypatch):
    actor=login(client,"admin",grant=True)
    with TestClient(app) as manager:
        manager_person=login(manager,"manager")
    program=client.post("/api/programs",json={"name":"Example","manager_ids":[manager_person["id"]],"deputy_ids":[actor["id"]]}).json()
    board=create(client,actor,layout_ri_id=actor["id"],board_ri_ids=[actor["id"]],program_ids=[program["id"]])
    assert client.post(f"/api/boards/{board['id']}/lifecycle",json={"action":"delete"}).status_code == 200
    zone=ZoneInfo("America/New_York")
    monkeypatch.setenv("NOTIFICATION_TIMEZONE",zone.key)
    present=now().astimezone(zone)
    tomorrow=(present+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    with Session() as db:
        before=tomorrow-timedelta(seconds=1)
        assert worker.generate(db,before) == 0
        assert worker.generate(db,tomorrow) == 2
        assert worker.generate(db,tomorrow) == 0
        digests=list(db.scalars(select(Digest)))
        assert len(digests)==2
        assert all(any(row["action"]=="delete" for row in d.payload) for d in digests)
        assert len(list(db.scalars(select(DigestCycle)))) == 2
        smtp=MagicMock(side_effect=OSError("relay unreachable"))
        monkeypatch.setattr(worker,"send",smtp)
        worker.deliver(db,tomorrow.astimezone(timezone.utc))
        assert all(d.status=="retry" and d.attempts==1 for d in digests)
        smtp.side_effect=None
        worker.deliver(db,(tomorrow+timedelta(minutes=3)).astimezone(timezone.utc))
        assert all(d.status=="sent" and d.attempts==2 for d in digests)
    record=client.get("/api/notifications").json()[0]
    assert client.patch("/api/notifications/"+str(record["id"]),json={"read":True}).json()=={"read":True}


def test_simultaneous_disjoint_edits(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent write check uses PostgreSQL")
    actor = login(client)
    board = create(client, actor)
    path = f"/api/boards/{board['id']}"
    barrier = Barrier(2)

    def save(username, key, proposed, expected):
        with TestClient(app) as other:
            login(other, username)
            barrier.wait(timeout=10)
            result = edit(other, path, {key:proposed}, {key:expected})
            return result.status_code

    with ThreadPoolExecutor(2) as pool:
        calls = [pool.submit(save, "layout", "active", False, True),
                 pool.submit(save, "schematic", "notes", "independent edit", None)]
        assert [call.result(timeout=15) for call in calls] == [200, 200]
    result = client.get(path).json()
    assert result["active"] is False and result["notes"] == "independent edit"


def test_saved_views_and_session_expiration(client):
    import time
    from tracker.models import SessionRecord

    login(client)
    result = client.post("/api/views", json={"name":"My RF boards","query":"board_type=RF&active=true"})
    assert result.status_code == 201
    with TestClient(app) as other:
        login(other, "someone-else")
        assert other.get("/api/views").json() == []
        assert other.delete(f"/api/views/{result.json()['id']}").status_code == 404
    assert client.get("/api/views").json()[0]["query"] == "board_type=RF&active=true"
    with Session.begin() as db:
        for record in db.scalars(select(SessionRecord)):
            record.expires = int(time.time()) - 1
    assert client.get("/api/auth/me").status_code == 401


def test_email_message_and_transport(monkeypatch):
    relay = MagicMock()
    smtp = MagicMock(return_value=relay)
    relay.__enter__.return_value = relay
    monkeypatch.setattr(worker.smtplib, "SMTP", smtp)
    monkeypatch.setenv("PUBLIC_URL", "https://tracker.example.test")
    monkeypatch.setenv("SMTP_FROM", "tracker@example.test")
    monkeypatch.setenv("SMTP_HOST", "relay.example.test")
    monkeypatch.setenv("SMTP_TLS", "starttls")
    digest = SimpleNamespace(id=11, day="2026-01-01", payload=[{
        "board_id":7,"board":"SRC00123","action":"update","field":"state","previous":"Scheduled",
        "value":"Complete","username":"engineer","timestamp":"2025-12-31T23:00:00+00:00",
    }])
    worker.send(digest, SimpleNamespace(display_name="Recipient", email="recipient@example.test"))
    relay.starttls.assert_called_once()
    message = relay.send_message.call_args.args[0]
    assert message["Message-ID"] == "<board-tracker-11@example.test>"
    assert "https://tracker.example.test/boards/7" in message.get_content()
    assert '"Scheduled" → "Complete"' in message.get_content()



def test_production_session_cookie_and_verbatim_password(monkeypatch):
    from tracker import main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(main, "validate_config", lambda: None)
    directory = MagicMock(return_value=("Directory User", "directory@example.test"))
    monkeypatch.setattr(main, "authenticate", directory)
    with TestClient(app, base_url="https://tracker.example.test") as client:
        result = client.post("/api/auth/login",json={"username":"directory","password":" leading and trailing "})
        assert result.status_code == 200
        directory.assert_called_once_with("directory", " leading and trailing ")
        cookie = result.headers["set-cookie"].lower()
        assert all(value in cookie for value in ("secure", "httponly", "samesite=lax", "max-age=28800"))
        assert client.post("/api/auth/logout").status_code == 403
        assert client.post("/api/auth/logout",headers={"X-CSRF-Token":result.json()["csrf"]}).status_code == 204
        assert client.get("/api/auth/me").status_code == 401


def test_review_creation_updates_audit_and_exports(client):
    person = login(client)
    payload = board_payload(person)
    kind = REVIEWS[0]
    review = payload["reviews"][kind]
    review.update(state="Working Action Items", url="http://example.test/first")
    missing = {key: value for key, value in payload["reviews"].items() if key != kind}
    assert client.post("/api/boards", json={**payload, "reviews": missing}).status_code == 422
    for invalid in ({"url": "ftp://example.test/a"}, {"date": None}, {"state": "Invalid"}):
        reviews = payload["reviews"] | {kind: review | invalid}
        assert client.post("/api/boards", json={**payload, "reviews": reviews}).status_code == 422
    without_reviews = {key: value for key, value in payload.items() if key != "reviews"}
    assert client.post("/api/boards", json=without_reviews).status_code == 422

    board = create(client, person, reviews=payload["reviews"])
    path = f"/api/boards/{board['id']}"
    current = next(row for row in board["reviews"] if row["kind"] == kind)
    assert {key: current[key] for key in review} == review
    endpoint = path + "/reviews/" + quote(kind)
    assert edit(client, endpoint, {"url": "javascript:alert(1)"}, current, "PUT").status_code == 422
    assert edit(client, endpoint, {"url": "https://example.test/updated"}, current, "PUT").status_code == 200
    assert edit(client, endpoint, {"url": None}, current, "PUT").status_code == 409
    assert client.get("/api/boards", params={"review_state": "Working Action Items"}).json()["total"] == 1
    refreshed = client.get(path).json()
    persisted = next(row for row in refreshed["reviews"] if row["kind"] == kind)
    assert persisted["url"] == "https://example.test/updated"

    events = client.get("/api/activity", params={"board_id": board["id"]}).json()["items"]
    urls = [row for row in events if row["field"] == kind + ".url"]
    assert [(row["previous"], row["value"]) for row in urls] == [
        ("http://example.test/first", "https://example.test/updated"),
        (None, "http://example.test/first"),
    ]
    assert any(row["field"] == kind + ".date" and row["value"] == REVIEW_DATE for row in events)
    workbook = load_workbook(BytesIO(client.get("/api/export/boards").content))
    assert any(row[2].value == "Working Action Items" and row[4].hyperlink.target == persisted["url"]
               for row in workbook["Reviews"].iter_rows(min_row=2))
    assert persisted["url"] in client.get("/api/export/boards?fmt=csv").text
    assert edit(client, endpoint, {"url": None}, persisted, "PUT").status_code == 200


def test_legacy_undated_reviews_and_maturity_zero_remain_editable(client):
    person = login(client)
    assert client.post("/api/boards", json={**board_payload(person), "maturity": 0}).status_code == 422
    board = create(client, person, maturity=1)
    with Session.begin() as db:
        db.get(Board, board["id"]).maturity = 0
        for review in db.scalars(select(Review).where(Review.board_id == board["id"])):
            review.date = None

    path = f"/api/boards/{board['id']}"
    legacy = client.get(path).json()
    assert legacy["maturity"] == 0
    assert all(review["date"] is None for review in legacy["reviews"])
    assert edit(client, path, {"complexity": "High"}, {"complexity": None}).json()["maturity"] == 0
    assert edit(client, path, {"maturity": 0}, {"maturity": 0}).status_code == 422
    assert client.get("/api/boards?maturity=0").status_code == 422
    assert edit(client, path, {"maturity": 4}, {"maturity": 0}).status_code == 200
    endpoint = path + "/reviews/" + quote(REVIEWS[0])
    assert edit(client, endpoint, {"state": "Scheduled"}, {"state": "Not Started"}, "PUT").status_code == 200
    assert edit(client, endpoint, {"date": REVIEW_DATE}, {"date": None}, "PUT").status_code == 200


def test_program_review_and_activity_scope(client):
    actor = login(client)
    program_id = client.post("/api/programs", json={"name": "Alpha"}).json()["id"]
    other_id = client.post("/api/programs", json={"name": "Other"}).json()["id"]
    attached = create(client, actor, "SRC00042", program_ids=[program_id, other_id])
    outside = create(client, actor, "SRC00043", program_ids=[other_id])

    path = f"/api/programs/{program_id}"
    scope = {"program_id": program_id}
    records = client.get(path).json()["boards"]
    assert [board["identifier"] for board in records] == [attached["identifier"]]
    assert {review["kind"] for review in records[0]["reviews"]} == set(REVIEWS)
    assert all(review["date"] == REVIEW_DATE for review in records[0]["reviews"])

    board_path = f"/api/boards/{attached['id']}"
    review_path = board_path + "/reviews/" + quote(REVIEWS[0])
    change = {"date": "2027-04-10", "state": "Working Action Items"}
    assert edit(client, review_path, change, {"date": REVIEW_DATE, "state": "Not Started"}, "PUT").status_code == 200
    review = next(row for row in client.get(path).json()["boards"][0]["reviews"] if row["kind"] == REVIEWS[0])
    assert {key: review[key] for key in change} == change

    assert edit(client, f"/api/programs/{other_id}", {"notes": "Other program notes"}, {"notes": None}).status_code == 200
    events = client.get("/api/activity", params=scope).json()["items"]
    assert {event["board_id"] for event in events} == {None, attached["id"]}
    assert any(event["value"] == "Working Action Items" for event in events)
    assert all(event["value"] != "Other program notes" for event in events)
    export = client.get("/api/export/activity", params={**scope, "fmt": "csv"}).text
    assert "Working Action Items" in export
    assert outside["identifier"] not in export and "Other program notes" not in export

    assert edit(client, board_path, {"program_ids": [other_id]}, {"program_ids": [program_id, other_id]}).status_code == 200
    assert client.get(path).json()["boards"] == []
    assert all(event["board_id"] is None for event in client.get("/api/activity", params=scope).json()["items"])
    outside_path = f"/api/boards/{outside['id']}"
    assert edit(client, outside_path, {"program_ids": [program_id, other_id]}, {"program_ids": [other_id]}).status_code == 200
    assert [board["identifier"] for board in client.get(path).json()["boards"]] == [outside["identifier"]]
