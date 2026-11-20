import csv
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from sqlalchemy import and_, exists, select
from sqlalchemy.exc import IntegrityError

from .db import now
from .models import Audit, Board, ParentSystem, Person, Program, Review, ReviewAssignment
from .schema import BoardFields, REVIEWS

REVIEW_PLANNING_ENTITY = "review_planning"


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A unique value already exists or a reference is invalid") from None


def columns(row, omit=()):
    return {
        column.key: getattr(row, column.key)
        for column in row.__table__.columns if column.key not in omit
    }


def json_value(value):
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def audit(db, actor, entity, row_id, action, field, previous=None, value=None, board=None, recipients=None):
    db.add(Audit(actor_id=actor.id, username=actor.username, entity=entity, entity_id=row_id,
                 board_id=board.id if board else None, board_label=board.identifier if board else None,
                 action=action, field=field, previous=json_value(previous), value=json_value(value),
                 deletion_recipients=recipients))


def program_data(program):
    return dict(columns(program), manager_ids=[p.id for p in program.managers],
                deputy_ids=[p.id for p in program.deputies])


def board_data(board):
    return dict(
        {key: json_value(value) for key, value in columns(board).items()},
        board_ri_ids=[p.id for p in board.board_ris],
        program_ids=[p.id for p in board.programs],
        programs=[program_data(p) for p in board.programs],
        parents=[columns(parent) for parent in board.parents],
        reviews=[review_data(review) for review in board.reviews],
    )


def assignment_values(review):
    return [{"reviewer_id": item.reviewer_id, "allocation_status": item.allocation_status}
            for item in sorted(review.assignments, key=lambda item: item.reviewer_id)]


def review_data(review):
    return dict(
        {key: json_value(value) for key, value in columns(review).items()},
        effective_review_start_date=json_value(review.effective_review_start_date),
        assignments=[
            dict(reviewer_id=item.reviewer_id, reviewer_name=item.reviewer.display_name,
                 allocation_status=item.allocation_status)
            for item in sorted(review.assignments, key=lambda item: item.reviewer_id)
        ],
    )


def apply_review_assignments(db, actor, board, review, assignments):
    current = {item.reviewer_id: item for item in review.assignments}
    requested = {item["reviewer_id"]: item["allocation_status"] for item in assignments}
    new_ids = requested.keys() - current.keys()
    for person in references(db, Person, new_ids):
        status = requested[person.id]
        review.assignments.append(ReviewAssignment(reviewer_id=person.id, reviewer=person, allocation_status=status))
        audit(db, actor, REVIEW_PLANNING_ENTITY, review.id, "assign", f"{review.kind}.reviewer",
              value=f"{person.display_name} ({person.username}) · {status}", board=board)
    for reviewer_id, item in current.items():
        label = f"{item.reviewer.display_name} ({item.reviewer.username})"
        if reviewer_id not in requested:
            review.assignments.remove(item)
            audit(db, actor, REVIEW_PLANNING_ENTITY, review.id, "unassign", f"{review.kind}.reviewer",
                  previous=f"{label} · {item.allocation_status}", board=board)
        elif item.allocation_status != requested[reviewer_id]:
            status = requested[reviewer_id]
            audit(db, actor, REVIEW_PLANNING_ENTITY, review.id, "update", f"{review.kind}.allocation_status",
                  previous=f"{label} · {item.allocation_status}", value=f"{label} · {status}", board=board)
            item.allocation_status = status


def get(db, model, identifier, lock=False):
    statement = select(model).where(model.id == identifier)
    instance = db.scalar(statement.with_for_update() if lock else statement)
    if instance is None:
        raise HTTPException(404, "Record not found")
    return instance


def get_board(db, identifier, actor, lock=False, include_deleted=False):
    board = get(db, Board, identifier, lock)
    if board.deleted_at and (not actor.admin or not include_deleted):
        raise HTTPException(404, "Board not found")
    return board


def references(db, model, ids):
    ids = sorted(set(ids))
    rows = db.scalars(select(model).where(model.id.in_(ids)).order_by(model.id)).all() if ids else []
    if len(rows) != len(ids):
        raise HTTPException(422, "A selected record does not exist")
    return rows


def recipients(board):
    result = {board.schematic_ri_id, board.layout_ri_id}
    result.update(p.id for p in board.board_ris)
    for program in board.programs:
        result.update(p.id for p in program.managers + program.deputies)
    result.discard(None)
    return sorted(result)


def touch(board, actor):
    board.updated_at, board.updated_by = now(), actor.id


def conflict(edit, current, changes):
    if edit.overwrite:
        return
    conflicts = {}
    for key, proposed in changes.items():
        actual = current[key]
        if key not in edit.expected or (actual != edit.expected[key] and actual != proposed):
            conflicts[key] = {"current": actual, "proposed": proposed}
    if conflicts:
        raise HTTPException(409, {"message": "This record changed while you were editing.", "fields": conflicts})


def describe(db, key, value):
    if key in ("schematic_ri_id", "layout_ri_id", "epm_id", "board_ri_ids", "manager_ids", "deputy_ids", "program_ids"):
        model = Program if key == "program_ids" else Person
        if value is None:
            return None
        rows = references(db, model, value if isinstance(value, list) else [value])
        labels = [{"id": row.id, "name": row.name if model is Program else row.display_name} for row in rows]
        return labels if isinstance(value, list) else labels[0]
    return value


def apply_board(db, board, actor, values, creating=False):
    current = {} if creating else board_data(board)
    changed = {}
    for key, value in values.items():
        if key in ("schematic_ri_id", "layout_ri_id") and value is not None:
            references(db, Person, [value])
        if key in ("program_ids", "board_ri_ids"):
            value = sorted(set(value))
        before = current.get(key)
        if before == value:
            continue
        if key == "program_ids":
            board.programs = references(db, Program, value)
        elif key == "board_ri_ids":
            board.board_ris = references(db, Person, value)
        else:
            setattr(board, key, value)
            if key == "identifier":
                board.base = value[:8]
        changed[key] = before, value
    if creating or changed:
        touch(board, actor)
        db.add(board)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Board identifier already exists") from None
    for key, (before, value) in changed.items():
        audit(db, actor, "board", board.id, "create" if creating else "update", key,
              describe(db, key, before), describe(db, key, value), board)


ENUM_FILTERS = ("board_type", "complexity", "reuse_level", "maturity", "schematic_tool", "layout_tool", "components_status")
SORTS = ("identifier", "active", "board_type", "complexity", "maturity", "created_at", "updated_at")


def calendar_range(query, key, column, is_date=False):
    result = []
    try:
        zone = ZoneInfo(query.get("tz", "UTC"))
        start = date.fromisoformat(query[f"{key}_from"]) if query.get(f"{key}_from") else None
        end = date.fromisoformat(query[f"{key}_to"]) if query.get(f"{key}_to") else None
        if start and end and start > end:
            raise ValueError
        if start:
            result.append(column >= (start if is_date else datetime.combine(start, time.min, zone).astimezone(timezone.utc)))
        if end:
            result.append(column <= end if is_date else column < datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(timezone.utc))
    except (ValueError, KeyError, OverflowError):
        raise HTTPException(422, "Invalid date range or timezone") from None
    return result


def board_query(query, actor):
    stmt = select(Board)
    if query.get("deleted") == "true":
        if not actor.admin:
            raise HTTPException(403, "Administrator privileges required")
        stmt = stmt.where(Board.deleted_at.is_not(None))
    else:
        stmt = stmt.where(Board.deleted_at.is_(None))
    if term := query.get("q"):
        stmt = stmt.where(Board.identifier.icontains(term, autoescape=True))
    values = query.getlist("active")
    if values:
        if any(value not in ("true", "false") for value in values):
            raise HTTPException(422, "Invalid active filter")
        stmt = stmt.where(Board.active.in_([value == "true" for value in values]))
    try:
        for key in ENUM_FILTERS:
            if values := query.getlist(key):
                if key == "maturity":
                    levels = [int(value) for value in values]
                    if any(level not in range(1, 5) for level in levels):
                        raise HTTPException(422, "Maturity filter values must be between 1 and 4")
                    stmt = stmt.where(Board.maturity.in_(levels))
                else:
                    stmt = stmt.where(getattr(Board, key).in_(values))
        for key in ("schematic_ri_id", "layout_ri_id", "board_ri_ids", "program_ids"):
            if values := query.getlist(key):
                ids = [int(v) for v in values]
                if key == "board_ri_ids":
                    stmt = stmt.where(Board.board_ris.any(Person.id.in_(ids)))
                elif key == "program_ids":
                    stmt = stmt.where(Board.programs.any(Program.id.in_(ids)))
                else:
                    stmt = stmt.where(getattr(Board, key).in_(ids))
    except ValueError:
        raise HTTPException(422, "Invalid numeric filter") from None
    if query.get("assigned") == "me":
        stmt = stmt.where((Board.schematic_ri_id == actor.id) | (Board.layout_ri_id == actor.id) | Board.board_ris.any(Person.id == actor.id))
    if query.get("stale") == "true":
        stmt = stmt.where(~exists(select(Audit.id).where(
            Audit.board_id == Board.id, Audit.timestamp >= now() - timedelta(days=30)
        )))
    if values := query.getlist("parent"):
        stmt = stmt.where(Board.parents.any(ParentSystem.name.in_(values)))
    review_terms = calendar_range(query, "review", Review.date, True)
    if values := query.getlist("review_kind"):
        review_terms.append(Review.kind.in_(values))
    if values := query.getlist("review_state"):
        review_terms.append(Review.state.in_(values))
    if review_terms:
        stmt = stmt.where(Board.reviews.any(and_(*review_terms)))
    if values := query.getlist("verification"):
        stmt = stmt.where(Board.reviews.any((Review.kind == REVIEWS[-1]) & Review.state.in_(values)))
    activity = calendar_range(query, "activity", Audit.timestamp)
    if activity:
        stmt = stmt.where(exists(select(Audit.id).where(Audit.board_id == Board.id, *activity)))
    for key in ("created", "updated"):
        stmt = stmt.where(*calendar_range(query, key, getattr(Board, key + "_at")))
    sort = query.get("sort", "identifier")
    descending = sort.startswith("-")
    key = sort.removeprefix("-")
    if key not in SORTS:
        raise HTTPException(422, "Unknown sort column")
    column = getattr(Board, key)
    return stmt.order_by(column.desc() if descending else column.asc(), Board.id)


def safe_cell(value):
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
        formula = re.match(r"^[\s\ufeff]*[=+@-]", value)
        if formula or value[:1] in ("\t", "\r", "\n"):
            return "'" + value
    return value


def export(rows, headers, fmt, sheets=()):
    stream = io.BytesIO()
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows([safe_cell(value) for value in row] for row in rows)
        return output.getvalue().encode("utf-8-sig"), "text/csv"
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, keys, records in [("Boards" if sheets else "Activity", headers, rows), *sheets]:
        worksheet = workbook.create_sheet(title)
        worksheet.append(keys)
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
        for row in records:
            worksheet.append([safe_cell(value) for value in row])
            for cell, key in zip(worksheet[worksheet.max_row], keys):
                if str(key).endswith("url") and isinstance(cell.value, str) and cell.value.startswith(("https://", "http://")):
                    cell.hyperlink = cell.value
                    cell.style = "Hyperlink"
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
    workbook.save(stream)
    return stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
