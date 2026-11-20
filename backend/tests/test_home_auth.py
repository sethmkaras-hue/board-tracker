from tracker.schema import REVIEWS
import pytest

from tracker.auth import validate_config


def configure_home(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_AUTH", "0")
    monkeypatch.setenv("HOME_ADMIN_PASSWORD", "synthetic-admin")
    monkeypatch.setenv("HOME_USER_PASSWORD", "synthetic-user")


@pytest.mark.parametrize("case", ["production", "placeholder", "shared"])
def test_home_auth_fails_closed(monkeypatch, case):
    configure_home(monkeypatch)
    if case == "production":
        monkeypatch.setenv("APP_ENV", "production")
    elif case == "placeholder":
        monkeypatch.setenv("HOME_ADMIN_PASSWORD", "CHANGE_ME")
    else:
        monkeypatch.setenv("HOME_USER_PASSWORD", "synthetic-admin")
    with pytest.raises(RuntimeError):
        validate_config()


def test_home_accounts_and_permissions(client, monkeypatch):
    configure_home(monkeypatch)
    validate_config()
    assert client.get("/api/boards").status_code == 401
    log_in = "/api/auth/login"
    assert client.post(log_in, json={"username": "someone", "password": "synthetic-admin"}).status_code == 401
    assert client.post(log_in, json={"username": "home.admin", "password": "synthetic-user"}).status_code == 401
    user = client.post(log_in, json={"username": "home.user", "password": "synthetic-user"}).json()
    assert not user["admin"]
    record = client.post("/api/boards", headers={"X-CSRF-Token": user["csrf"]},
                         json={"identifier": "SRC00042", "schematic_ri_id": user["id"],
                               "reviews": {kind: {"date": "2026-05-15"} for kind in REVIEWS}})
    assert record.status_code == 201
    path = f"/api/boards/{record.json()['id']}/lifecycle"
    assert client.post(path, headers={"X-CSRF-Token": user["csrf"]}, json={"action": "delete"}).status_code == 403

    admin = client.post(log_in, json={"username": "home.admin", "password": "synthetic-admin"}).json()
    assert admin["admin"]
    assert client.post(path, headers={"X-CSRF-Token": admin["csrf"]}, json={"action": "delete"}).status_code == 200
    monkeypatch.delenv("AUTH_MODE")
    assert client.get("/api/auth/me").status_code == 401
