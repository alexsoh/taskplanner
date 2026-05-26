import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Profile")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#38bdf8")
    run_latest_per_channel_on_activation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    actions = relationship(
        "ScheduledAction",
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class ScheduledAction(Base):
    __tablename__ = "scheduled_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="Action")
    days_of_week: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: [0])  # [0=Mon, 1=Tue, ..., 6=Sun]
    time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notification_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    profile: Mapped["Profile"] = relationship(back_populates="actions")


class ExecutionRun(Base):
    __tablename__ = "execution_runs"
    __table_args__ = (
        Index("uq_execution_run_action_slot", "scheduled_action_id", "scheduled_for", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scheduled_action_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("scheduled_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    profile_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | failed | skipped
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class AppSettingsRow(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mqtt_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    telegram_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    upgrade_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evalex_base: Mapped[str] = mapped_column(String(255), nullable=False, default="https://evalex.duckdns.org")
    allowed_ips_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    server_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8200)
