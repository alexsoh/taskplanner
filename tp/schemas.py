from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

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
    day_of_week: int = Field(ge=0, le=6)
    time: str
    channel: Channel
    enabled: bool = True
    notification_config: Dict[str, Any] = Field(default_factory=dict)


class ActionUpdate(BaseModel):
    label: Optional[str] = None
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    time: Optional[str] = None
    channel: Optional[Channel] = None
    enabled: Optional[bool] = None
    notification_config: Optional[Dict[str, Any]] = None


class ActionOut(BaseModel):
    id: str
    profile_id: str
    label: str
    day_of_week: int
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
