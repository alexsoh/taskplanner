from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Channel = Literal["mqtt", "telegram", "http", "script", "nvr", "evalex"]


class ProfileCreate(BaseModel):
    name: str = "Profile"
    timezone: str = "UTC"
    enabled: bool = True
    color: str = "#38bdf8"


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    color: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("name must not be empty")
        return v


class ProfileOut(BaseModel):
    id: str
    name: str
    timezone: str
    enabled: bool
    color: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionCreate(BaseModel):
    label: str = "Action"
    days_of_week: list[int] = Field(default=[0], min_length=1)
    time: str
    channel: Channel
    enabled: bool = True
    notification_config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("days_of_week must have at least one day")
        unique_sorted = sorted(set(v))
        for day in unique_sorted:
            if not (0 <= day <= 6):
                raise ValueError(f"day_of_week must be 0-6, got {day}")
        return unique_sorted


class ActionUpdate(BaseModel):
    label: Optional[str] = None
    days_of_week: Optional[list[int]] = Field(default=None, min_length=1)
    time: Optional[str] = None
    channel: Optional[Channel] = None
    enabled: Optional[bool] = None
    notification_config: Optional[Dict[str, Any]] = None

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return None
        if not v:
            raise ValueError("days_of_week must have at least one day")
        unique_sorted = sorted(set(v))
        for day in unique_sorted:
            if not (0 <= day <= 6):
                raise ValueError(f"day_of_week must be 0-6, got {day}")
        return unique_sorted


class ActionOut(BaseModel):
    id: str
    profile_id: str
    label: str
    days_of_week: list[int]
    time: str
    channel: str
    enabled: bool
    notification_config: Dict[str, Any]

    model_config = {"from_attributes": True}


class SettingsOut(BaseModel):
    mqtt: Dict[str, Any]
    telegram: Dict[str, Any]
    upgradeToken: Optional[str] = None
    allowedIps: Optional[List[str]] = None
    serverPort: Optional[int] = None


class SettingsUpdate(BaseModel):
    mqtt: Optional[Dict[str, Any]] = None
    telegram: Optional[Dict[str, Any]] = None
    upgradeToken: Optional[str] = None
    allowedIps: Optional[List[str]] = None
    serverPort: Optional[int] = None


class ExecutionOut(BaseModel):
    id: str
    scheduled_action_id: Optional[str]
    profile_id: Optional[str]
    scheduled_for: datetime
    fired_at: datetime
    status: str
    error: Optional[str]
    channel: str
    label: str
    detail: Optional[Dict[str, Any]]

    model_config = {"from_attributes": True}


class CalendarEvent(BaseModel):
    action_id: str
    profile_id: str
    profile_name: str
    profile_color: str
    label: str
    channel: str
    day_of_week: int
    time: str
    occurrence_utc: datetime
