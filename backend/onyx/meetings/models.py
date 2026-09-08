from datetime import datetime
from typing import Literal
from typing import Self
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


class Segment(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    text: str
    speaker: str = "UNKNOWN"

    @model_validator(mode="after")
    def ordered_timestamps(self) -> Self:
        if self.end < self.start:
            raise ValueError("Segment end must not precede start")
        return self


class Topic(BaseModel):
    title: str
    segment_ids: list[int]
    category: Literal["agenda", "off_topic", "repeated", "unknown"]
    explanation: str


class Action(BaseModel):
    task: str
    owner: str | None
    deadline: str | None


class Analysis(BaseModel):
    summary: str
    minutes: str
    decisions: list[str]
    actions: list[Action]
    topics: list[Topic]
    effectiveness_score: int = Field(ge=0, le=100)
    explanation: str


class MeetingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    agenda: str
    status: str
    created_at: datetime
    updated_at: datetime
    duration: float | None
    error: str | None


class MeetingSnapshot(MeetingSummary):
    segments: list[Segment]
    analysis: dict | None
