from datetime import date as calendar_date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, StrictInt, StringConstraints, field_validator, model_validator

TYPES = ("External IO", "Power", "Digital", "RF", "Antenna", "Backplane", "Other")
LEVELS = ("Low", "Medium", "High", "Very High")
TOOLS = ("Altium", "PADS", "Other")
CHECKS = ("Not Started", "In Progress", "Complete")
STATES = ("Not Started", "Scheduled", "In-Review", "Working Action Items", "Complete")
ALLOCATION_STATUSES = ("Not Allocated", "Allocated")
REVIEWS = ("Functional Overview Review", "Detailed Design Review", "Schematic Review", "Artwork Review", "Board Verification (Unit Test)")
Identifier = Annotated[str, Field(pattern=r"^SRC[0-9]{5}[A-Z]?$")]
PersonId = Annotated[StrictInt, Field(gt=0)]
Name = Annotated[str, Field(min_length=1, max_length=200)]


def document_url(value):
    if value.username or value.password:
        raise ValueError("Document links must not contain credentials")
    return value


DocumentUrl = Annotated[HttpUrl, AfterValidator(document_url)]
Notes = Annotated[str, StringConstraints(strip_whitespace=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def validate_text(cls, value):
        if isinstance(value, str) and "\0" in value:
            raise ValueError("Text cannot contain null characters")
        return value


class BoardFields(Input):
    identifier: Identifier | None = None
    active: bool | None = None
    schematic_ri_id: PersonId | None = None
    layout_ri_id: PersonId | None = None
    board_ri_ids: list[PersonId] | None = None
    program_ids: list[PersonId] | None = None
    board_type: Literal[TYPES] | None = None
    complexity: Literal[LEVELS] | None = None
    reuse_level: Literal[LEVELS] | None = None
    maturity: Annotated[StrictInt, Field(ge=1, le=4)] | None = None
    schematic_tool: Literal[TOOLS] | None = None
    layout_tool: Literal[TOOLS] | None = None
    components_status: Literal[CHECKS] | None = None
    aras_board_url: DocumentUrl | None = None
    aras_export_url: DocumentUrl | None = None
    overview_url: DocumentUrl | None = None
    notes: Notes | None = None

    @field_validator("notes")
    @classmethod
    def notes_capacity(cls, value):
        if value is not None and len(value.encode("utf-8")) > 4096:
            raise ValueError("Notes must fit within 4096 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def required_when_present(self):
        for field in ("identifier", "active", "schematic_ri_id", "board_ri_ids", "program_ids"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProgramFields(Input):
    name: Name
    epm_id: PersonId | None = None
    notes: Notes | None = None
    manager_ids: list[PersonId] = Field(default_factory=list)
    deputy_ids: list[PersonId] = Field(default_factory=list)


class ParentFields(Input):
    name: Name
    quantity: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    url: DocumentUrl | None = None
    notes: Notes | None = None


class ReviewAssignmentFields(Input):
    reviewer_id: PersonId
    allocation_status: Literal[ALLOCATION_STATUSES] = "Not Allocated"


class ReviewFields(Input):
    state: Literal[STATES]
    date: calendar_date | None = None
    url: DocumentUrl | None = None
    review_start_date: calendar_date | None = None
    assignments: list[ReviewAssignmentFields] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_review_window(self):
        if self.review_start_date is not None and (self.date is None or self.review_start_date > self.date):
            raise ValueError("Review start date requires a meeting date and must be on or before it")
        ids = {assignment.reviewer_id for assignment in self.assignments}
        if len(ids) != len(self.assignments):
            raise ValueError("A reviewer can only be assigned once per review")
        return self


class NewReview(ReviewFields):
    state: Literal[STATES] = "Not Started"
    date: calendar_date


class BoardCreate(BoardFields):
    identifier: Identifier
    schematic_ri_id: PersonId
    active: bool = True
    reviews: dict[Literal[REVIEWS], NewReview]

    @field_validator("reviews")
    @classmethod
    def require_each_review(cls, reviews):
        missing = [kind for kind in REVIEWS if kind not in reviews]
        if missing:
            raise ValueError("Review dates are required for: " + ", ".join(missing))
        return reviews


class Edit(Input):
    changes: dict
    expected: dict
    overwrite: bool = False
