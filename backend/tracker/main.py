import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import QueryParams

from .auth import admin, authenticate, enabled, home_auth, limit_login, session, session_token_hash, user, validate_config
from .db import database, lock_writes, now
from .models import Audit, Board, Digest, DigestCycle, ParentSystem, Person, Program, Review, SavedView, SessionRecord, Setting, board_programs
from .schema import BoardCreate, BoardFields, Edit, Input, ParentFields, ProgramFields, REVIEWS, ReviewFields
from .service import apply_board, audit, board_data, board_query, columns, commit, conflict, describe, get, get_board, json_value, program_data, recipients, references, touch, export

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_):
    validate_config()
    yield


app = FastAPI(title="Board Tracker", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    return JSONResponse(status_code=422, content={"detail": [
        {"field": ".".join(map(str, error["loc"])), "message": error["msg"]} for error in exc.errors()
    ]})


def parse(model, data):
    try:
        return model.model_validate(data).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(422, [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]) from None


@app.get("/api/health")
def health(db=Depends(database)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[A-Za-z0-9._@-]{1,128}$")
    password: str = Field(min_length=1, max_length=1024)


def identity(person, record=None):
    return dict(columns(person), **({"csrf": record.csrf} if record else {}))


@app.post("/api/auth/login")
def login(data: Login, request: Request, response: Response, db=Depends(database)):
    limit_login(db, request.client.host if request.client else "unknown")
    username = data.username.lower()
    result = authenticate(username, data.password)
    if not result:
        log.info("Directory login rejected")
        raise HTTPException(401, "Invalid username or password")
    if db.bind.dialect.name == "postgresql":
        lock_writes(db)
    person = db.scalar(select(Person).where(Person.username == username))
    display_name, email = result
    if not person:
        person = Person(username=username, display_name=display_name, email=email)
        db.add(person)
        db.flush()
        audit(db, person, "person", person.id, "create", "directory_profile", value={"display_name": display_name, "email": email})
    else:
        for key, value in {"display_name": display_name, "email": email or person.email}.items():
            if getattr(person, key) != value:
                audit(db, person, "person", person.id, "update", key, getattr(person, key), value)
                setattr(person, key, value)
    if home_auth():
        is_admin = username == "home.admin"
        if person.admin != is_admin:
            audit(db, person, "person", person.id, "update", "admin", person.admin, is_admin)
            person.admin = is_admin
    token = secrets.token_urlsafe(32)
    duration = 8 * 3600
    record = SessionRecord(token_hash=session_token_hash(token), person_id=person.id, expires=int(time.time()) + duration,
                           csrf=secrets.token_urlsafe(32))
    db.add(record)
    commit(db)
    response.set_cookie("tracker_session", token, max_age=duration, httponly=True, samesite="lax",
                        secure=os.getenv("APP_ENV") != "development")
    return identity(person, record)


@app.get("/api/auth/me")
def me(actor=Depends(user), record=Depends(session)):
    return identity(actor, record)


@app.post("/api/auth/logout", status_code=204)
def logout(record=Depends(session), db=Depends(database)):
    db.delete(record)
    commit(db)
    response = Response(status_code=204)
    response.delete_cookie("tracker_session", secure=os.getenv("APP_ENV") != "development", httponly=True)
    return response


@app.get("/api/people")
def people(actor=Depends(user), db=Depends(database)):
    return [identity(p) for p in db.scalars(select(Person).order_by(Person.display_name))]


@app.get("/api/parents/options")
def parent_options(actor=Depends(user), db=Depends(database)):
    query = select(ParentSystem.name).join(Board, ParentSystem.board_id == Board.id)
    return list(db.scalars(query.where(Board.deleted_at.is_(None)).distinct().order_by(ParentSystem.name)))


@app.get("/api/boards")
def list_boards(request: Request, page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100),
                actor=Depends(user), db=Depends(database)):
    statement = board_query(request.query_params, actor)
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    return {"total": total, "items": [board_data(row) for row in db.scalars(statement.offset((page-1)*limit).limit(limit))]}


@app.post("/api/boards", status_code=201)
def create_board(data: BoardCreate, actor=Depends(user), db=Depends(database)):
    board = Board(created_by=actor.id)
    values = data.model_dump(mode="json", exclude_unset=True)
    values.setdefault("active", True)
    apply_board(db, board, actor, values, creating=True)
    board.reviews = [Review(kind=kind, state="Not Started") for kind in REVIEWS]
    db.flush()
    for review in board.reviews:
        audit(db, actor, "review", review.id, "create", f"{review.kind}.state", value=review.state, board=board)
    commit(db)
    return board_data(board)


@app.get("/api/boards/{board_id:int}")
def board_detail(board_id: int, actor=Depends(user), db=Depends(database)):
    board = get_board(db, board_id, actor, include_deleted=True)
    siblings = db.execute(select(Board.id, Board.identifier).where(
        Board.base == board.base, Board.id != board.id, Board.deleted_at.is_(None)).order_by(Board.identifier))
    return dict(board_data(board), revisions=[dict(row._mapping) for row in siblings])


@app.patch("/api/boards/{board_id:int}")
def update_board(board_id: int, edit: Edit, actor=Depends(user), db=Depends(database)):
    board = get_board(db, board_id, actor, lock=True)
    values = parse(BoardFields, edit.changes)
    for key in ("board_ri_ids", "program_ids"):
        if key in values:
            values[key] = sorted(set(values[key]))
    conflict(edit, board_data(board), values)
    apply_board(db, board, actor, values)
    commit(db)
    return board_data(board)


@app.post("/api/boards/{board_id:int}/lifecycle")
def lifecycle(board_id: int, action: Literal["delete", "restore"] = Body(embed=True), actor=Depends(admin), db=Depends(database)):
    board = get_board(db, board_id, actor, lock=True, include_deleted=True)
    if bool(board.deleted_at) != (action == "delete"):
        before = board.deleted_at
        board.deleted_at = now() if action == "delete" else None
        touch(board, actor)
        audit(db, actor, "board", board.id, action, "deleted_at", before, board.deleted_at,
              board, recipients(board) if action == "delete" else None)
        commit(db)
    return board_data(board)


@app.put("/api/boards/{board_id:int}/reviews/{kind}")
def update_review(board_id: int, kind: str, edit: Edit, actor=Depends(user), db=Depends(database)):
    board = get_board(db, board_id, actor, lock=True)
    review = next((r for r in board.reviews if r.kind == kind), None)
    if review is None:
        raise HTTPException(404, "Review step not found")
    current = {"state": review.state, "date": json_value(review.date)}
    values = parse(ReviewFields, current | edit.changes)
    conflict(edit, current, {key: values[key] for key in edit.changes})
    validated = ReviewFields.model_validate(values)
    for key in edit.changes:
        value = getattr(validated, key)
        if getattr(review, key) != value:
            audit(db, actor, "review", review.id, "update", f"{kind}.{key}", current[key], value, board)
            setattr(review, key, value)
            touch(board, actor)
    commit(db)
    return board_data(board)


@app.post("/api/boards/{board_id:int}/parents", status_code=201)
def add_parent(board_id: int, data: ParentFields, actor=Depends(user), db=Depends(database)):
    board = get_board(db, board_id, actor, lock=True)
    row = ParentSystem(**data.model_dump(mode="json"))
    board.parents.append(row)
    db.flush()
    for key, value in data.model_dump(mode="json").items():
        audit(db, actor, "parent_system", row.id, "create", key, value=value, board=board)
    touch(board, actor)
    commit(db)
    return board_data(board)


@app.patch("/api/boards/{board_id:int}/parents/{parent_id:int}")
def edit_parent(board_id: int, parent_id: int, edit: Edit, actor=Depends(user), db=Depends(database)):
    board = get_board(db, board_id, actor, lock=True)
    row = next((r for r in board.parents if r.id == parent_id), None)
    if row is None:
        raise HTTPException(404, "Parent system not found")
    current = {key: getattr(row, key) for key in ParentFields.model_fields}
    values = parse(ParentFields, current | edit.changes)
    conflict(edit, current, {key: values[key] for key in edit.changes})
    for key in edit.changes:
        if current[key] != values[key]:
            audit(db, actor, "parent_system", row.id, "update", key, current[key], values[key], board)
            setattr(row, key, values[key])
            touch(board, actor)
    commit(db)
    return board_data(board)


@app.delete("/api/boards/{board_id:int}/parents/{parent_id:int}")
def remove_parent(board_id: int, parent_id: int, actor=Depends(user), db=Depends(database)):
    board = get_board(db, board_id, actor, lock=True)
    row = next((r for r in board.parents if r.id == parent_id), None)
    if row is None:
        raise HTTPException(404, "Parent system not found")
    audit(db, actor, "parent_system", row.id, "remove", "relationship", columns(row), board=board)
    board.parents.remove(row)
    touch(board, actor)
    commit(db)
    return board_data(board)


@app.get("/api/programs")
def programs(actor=Depends(user), db=Depends(database)):
    return [program_data(row) for row in db.scalars(select(Program).order_by(Program.name))]


def patch_program(db, row, values, actor, current=None):
    with db.no_autoflush:
        if values.get("epm_id"):
            references(db, Person, [values["epm_id"]])
        for key, attribute in (("manager_ids", "managers"), ("deputy_ids", "deputies")):
            if key in values:
                setattr(row, attribute, references(db, Person, values[key]))
        for key in ("name", "epm_id", "notes"):
            if key in values:
                setattr(row, key, values[key])
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Program name already exists") from None
    boards = list(db.scalars(select(Board).where(Board.programs.any(Program.id == row.id), Board.deleted_at.is_(None)))) if current else []
    for key, value in values.items():
        before = current.get(key) if current else None
        if before != value:
            previous, proposed = describe(db, key, before), describe(db, key, value)
            audit(db, actor, "program", row.id, "update" if current else "create", key, previous, proposed)
            for board in boards:
                audit(db, actor, "program", row.id, "update", f"{row.name}.{key}", previous, proposed, board)
    commit(db)
    return program_data(row)


@app.post("/api/programs", status_code=201)
def create_program(data: ProgramFields, actor=Depends(user), db=Depends(database)):
    row = Program()
    db.add(row)
    values = data.model_dump(mode="json")
    for key in ("manager_ids", "deputy_ids"):
        values[key] = sorted(set(values[key]))
    return patch_program(db, row, values, actor)


@app.patch("/api/programs/{program_id:int}")
def update_program(program_id: int, edit: Edit, actor=Depends(user), db=Depends(database)):
    row = get(db, Program, program_id, lock=True)
    current = program_data(row)
    values = parse(ProgramFields, {key: current[key] for key in ProgramFields.model_fields} | edit.changes)
    values = {key: sorted(set(values[key])) if key in ("manager_ids", "deputy_ids") else values[key] for key in edit.changes}
    conflict(edit, current, values)
    return patch_program(db, row, values, actor, current)


@app.get("/api/programs/{program_id:int}")
def program_detail(program_id: int, actor=Depends(user), db=Depends(database)):
    row = get(db, Program, program_id)
    boards = db.scalars(board_query(QueryParams({"program_ids": program_id, "sort": "-updated_at"}), actor))
    records = [board_data(board) for board in boards]
    return dict(program_data(row), boards=records, metrics=distributions(db, select(Board.id).where(Board.deleted_at.is_(None), Board.programs.any(Program.id == row.id))))


def distributions(db, board_ids):
    def count_by(column, *conditions):
        return {str(value) if value is not None else "Unspecified": count for value, count in db.execute(
            select(column, func.count()).where(*conditions).group_by(column).order_by(func.count().desc(), column)
        )}

    return {
        "types": count_by(Board.board_type, Board.id.in_(board_ids)),
        "maturity": count_by(Board.maturity, Board.id.in_(board_ids)),
        "complexity": count_by(Board.complexity, Board.id.in_(board_ids)),
        "reviews": count_by(Review.state, Review.board_id.in_(board_ids), Review.kind != REVIEWS[-1]),
        "verification": count_by(Review.state, Review.board_id.in_(board_ids), Review.kind == REVIEWS[-1]),
        "programs": dict(db.execute(
            select(Program.name, func.count()).join(board_programs, board_programs.c.member_id == Program.id)
            .where(board_programs.c.owner_id.in_(board_ids))
            .group_by(Program.name).order_by(func.count().desc(), Program.name)
        ).all()),
    }


@app.get("/api/dashboard")
def dashboard(actor=Depends(user), db=Depends(database)):
    board_ids = select(Board.id).where(Board.deleted_at.is_(None))

    def count(query):
        statement = board_query(QueryParams(query), actor).order_by(None).subquery()
        return db.scalar(select(func.count()).select_from(statement))

    recent = db.scalars(board_query(QueryParams({"sort": "-updated_at"}), actor).limit(8))
    return dict(distributions(db, board_ids), active=count({"active": "true"}),
                inactive=count({"active": "false"}), assigned=count({"assigned": "me"}),
                stale=count({"stale": "true"}), recent=[board_data(board) for board in recent])


def activity_query(actor, board_id=None):
    stmt = select(Audit).order_by(Audit.id.desc())
    if not actor.admin:
        stmt = stmt.where(or_(Audit.board_id.is_(None), Audit.board_id.in_(select(Board.id).where(Board.deleted_at.is_(None)))))
    if board_id:
        stmt = stmt.where(Audit.board_id == board_id)
    return stmt


def audit_data(row):
    return {key: json_value(value) for key, value in columns(row, ("deletion_recipients",)).items()}


@app.get("/api/activity")
def activity(board_id: int | None = None, page: int = Query(1, ge=1), actor=Depends(user), db=Depends(database)):
    query = activity_query(actor, board_id)
    return {"items": [audit_data(row) for row in db.scalars(query.offset((page-1)*50).limit(50))],
            "total": db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))}


def attachment(data, name, fmt):
    body, mime = data
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@app.get("/api/export/activity")
def activity_export(fmt: Literal["csv", "xlsx"] = "xlsx", board_id: int | None = None, actor=Depends(user), db=Depends(database)):
    keys = [c.key for c in Audit.__table__.columns if c.key != "deletion_recipients"]
    rows = [[audit_data(row)[key] for key in keys] for row in db.scalars(activity_query(actor, board_id))]
    return attachment(export(rows, keys, fmt), "activity", fmt)


@app.get("/api/export/boards")
def boards_export(request: Request, fmt: Literal["csv", "xlsx"] = "xlsx", actor=Depends(user), db=Depends(database)):
    records = [board_data(b) for b in db.scalars(board_query(request.query_params, actor))]
    directory = {p.id: f"{p.display_name} ({p.username})" for p in db.scalars(select(Person))}
    keys = [c.key for c in Board.__table__.columns if c.key != "base"] + ["board_ri_ids", "programs"]
    if fmt == "csv":
        keys += ["parents", "reviews"]
    rows = []
    parents, reviews, programs_rows = [], [], []
    for board in records:
        for key in ("schematic_ri_id", "layout_ri_id", "created_by", "updated_by"):
            board[key] = directory.get(board[key])
        board["board_ri_ids"] = [directory[p] for p in board["board_ri_ids"]]
        board["programs"] = [p["name"] for p in board["programs"]]
        rows.append([board[key] for key in keys])
        parents.extend([[board["identifier"], p["name"], p["url"], p["quantity"], p["notes"]] for p in board["parents"]])
        reviews.extend([[board["identifier"], r["kind"], r["state"], r["date"]] for r in board["reviews"]])
        programs_rows.extend([[board["identifier"], name] for name in board["programs"]])
    sheets = [("Parent Systems", ["board", "parent", "url", "quantity", "notes"], parents),
              ("Reviews", ["board", "review", "state", "date"], reviews),
              ("Programs", ["board", "program"], programs_rows)]
    return attachment(export(rows, keys, fmt, sheets), "boards", fmt)


class View(Input):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(max_length=6000)


@app.get("/api/views")
def views(actor=Depends(user), db=Depends(database)):
    return [columns(v) for v in db.scalars(select(SavedView).where(SavedView.person_id == actor.id).order_by(SavedView.name))]


@app.post("/api/views", status_code=201)
def save_view(data: View, actor=Depends(user), db=Depends(database)):
    board_query(QueryParams(data.query), actor)
    row = SavedView(person_id=actor.id, name=data.name, query=data.query)
    db.add(row)
    commit(db)
    return columns(row)


@app.delete("/api/views/{view_id:int}", status_code=204)
def delete_view(view_id: int, actor=Depends(user), db=Depends(database)):
    row = get(db, SavedView, view_id)
    if row.person_id != actor.id:
        raise HTTPException(404, "View not found")
    db.delete(row)
    commit(db)


@app.get("/api/notifications")
def notifications(actor=Depends(user), db=Depends(database)):
    return [columns(d, ("error",)) for d in db.scalars(select(Digest).where(Digest.person_id == actor.id).order_by(Digest.day.desc()).limit(90))]


@app.patch("/api/notifications/{digest_id:int}")
def mark_read(digest_id: int, read: bool = Body(embed=True), actor=Depends(user), db=Depends(database)):
    row = get(db, Digest, digest_id, lock=True)
    if row.person_id != actor.id:
        raise HTTPException(404, "Notification not found")
    row.read = read
    commit(db)
    return {"read": row.read}


@app.patch("/api/admin/people/{person_id:int}")
def change_privilege(person_id: int, grant: bool = Body(embed=True), actor=Depends(admin), db=Depends(database)):
    row = get(db, Person, person_id, lock=True)
    if actor.id == row.id and not grant:
        raise HTTPException(422, "Another administrator must revoke your privileges")
    if grant and not row.email:
        raise HTTPException(422, "An email address is required")
    if row.admin != grant:
        audit(db, actor, "person", row.id, "update", "admin", row.admin, grant)
        row.admin = grant
        commit(db)
    return identity(row)


@app.get("/api/admin/status")
def system_status(actor=Depends(admin), db=Depends(database)):
    config = db.get(Setting, "notification_timezone")
    backup = Path(os.getenv("BACKUP_STATUS_PATH", "/backups/status"))
    return {"database": "ok", "ldap_configured": bool(os.getenv("LDAP_URL")), "smtp_configured": bool(os.getenv("SMTP_HOST")),
            "backup": backup.read_text()[:1000].strip() if backup.is_file() else "No verified backup reported",
            "notification_timezone": config.value if config else os.getenv("NOTIFICATION_TIMEZONE", "UTC"),
            "cycles": [columns(row) for row in db.scalars(select(DigestCycle).order_by(DigestCycle.day.desc()).limit(20))],
            "failures": [columns(row, ("payload",)) for row in db.scalars(select(Digest).where(Digest.status.in_(("retry", "failed"))).limit(100))]}


@app.put("/api/admin/settings")
def settings(timezone: str = Body(embed=True), actor=Depends(admin), db=Depends(database)):
    try:
        ZoneInfo(timezone)
    except (KeyError, ValueError):
        raise HTTPException(422, "Unknown IANA timezone") from None
    row = db.get(Setting, "notification_timezone")
    before = row.value if row else None
    if before != timezone:
        if row:
            row.value = timezone
        else:
            db.add(Setting(name="notification_timezone", value=timezone))
        audit(db, actor, "settings", 0, "update", "notification_timezone", before, timezone)
        commit(db)
    return {"notification_timezone": timezone}
