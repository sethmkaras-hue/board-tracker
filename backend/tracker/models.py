from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, now


def association(name, left, right):
    return Table(
        name, Base.metadata,
        Column("owner_id", ForeignKey(left, ondelete="CASCADE"), primary_key=True),
        Column("member_id", ForeignKey(right, ondelete="RESTRICT"), primary_key=True, index=True),
    )


board_people = association("board_people", "boards.id", "people.id")
board_programs = association("board_programs", "boards.id", "programs.id")
program_managers = association("program_managers", "programs.id", "people.id")
program_deputies = association("program_deputies", "programs.id", "people.id")


class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(256))
    email = mapped_column(String(320))
    admin: Mapped[bool] = mapped_column(Boolean, default=False)


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (CheckConstraint("maturity BETWEEN 0 AND 4", name="maturity_range"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    identifier: Mapped[str] = mapped_column(String(9), unique=True)
    base: Mapped[str] = mapped_column(String(8), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deleted_at = mapped_column(DateTime(timezone=True), index=True)
    schematic_ri_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    layout_ri_id = mapped_column(ForeignKey("people.id"), index=True)
    board_type = mapped_column(String(24), index=True)
    complexity = mapped_column(String(16), index=True)
    reuse_level = mapped_column(String(16), index=True)
    maturity = mapped_column(Integer, index=True)
    schematic_tool = mapped_column(String(16))
    layout_tool = mapped_column(String(16))
    components_status = mapped_column(String(20))
    aras_board_url = mapped_column(Text)
    aras_export_url = mapped_column(Text)
    overview_url = mapped_column(Text)
    notes = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), default=now, nullable=False, index=True)
    updated_at = mapped_column(DateTime(timezone=True), default=now, nullable=False, index=True)
    created_by = mapped_column(ForeignKey("people.id"), nullable=False)
    updated_by = mapped_column(ForeignKey("people.id"), nullable=False)
    board_ris = relationship("Person", secondary=board_people, lazy="selectin", order_by=Person.id)
    programs = relationship("Program", secondary=board_programs, lazy="selectin", order_by="Program.id")
    parents = relationship("ParentSystem", lazy="selectin", cascade="all, delete-orphan", order_by="ParentSystem.id")
    reviews = relationship("Review", lazy="selectin", cascade="all, delete-orphan", order_by="Review.kind")


class Program(Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    epm_id = mapped_column(ForeignKey("people.id"))
    notes = mapped_column(Text)
    managers = relationship("Person", secondary=program_managers, lazy="selectin", order_by=Person.id)
    deputies = relationship("Person", secondary=program_deputies, lazy="selectin", order_by=Person.id)


class ParentSystem(Base):
    __tablename__ = "parent_systems"
    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity_nonnegative"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    board_id = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    url = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    notes = mapped_column(Text)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("board_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    board_id = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    date = mapped_column(Date, index=True)
    url = mapped_column(Text)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp = mapped_column(DateTime(timezone=True), default=now, nullable=False, index=True)
    actor_id = mapped_column(ForeignKey("people.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(128))
    entity: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    board_id = mapped_column(ForeignKey("boards.id"), index=True)
    board_label = mapped_column(String(9))
    action: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(80))
    previous = mapped_column(JSON)
    value = mapped_column(JSON)
    deletion_recipients = mapped_column(JSON)


class SavedView(Base):
    __tablename__ = "saved_views"
    __table_args__ = (UniqueConstraint("person_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id = mapped_column(ForeignKey("people.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120))
    query: Mapped[str] = mapped_column(Text)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires: Mapped[int] = mapped_column(Integer)


class SessionRecord(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    csrf: Mapped[str] = mapped_column(String(64))


class Setting(Base):
    __tablename__ = "settings"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class DigestCycle(Base):
    __tablename__ = "digest_cycles"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    completed_at = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    through_id: Mapped[int] = mapped_column(Integer)


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("day", "person_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[str] = mapped_column(String(10))
    person_id = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    payload = mapped_column(JSON, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    error = mapped_column(String(200))
