from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Schedule(BaseModel):
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def _validateOrder(self) -> "Schedule":
        if self.end_at <= self.start_at:
            raise ValueError("end_at 은 start_at 이후여야 합니다")
        return self


class EventBase(BaseModel):
    title: str = Field(max_length=20)
    body: str | None = None
    schedule: Schedule
    img_urls: list[str] = Field(default_factory=list)
    total_seats: int = Field(ge=1)


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=20)
    body: str | None = None
    schedule: Schedule | None = None
    img_urls: list[str] | None = None
    total_seats: int | None = Field(default=None, ge=1)


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    user_id: UUID
    created_at: date
    last_modified: date | None


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    page: int
    size: int
