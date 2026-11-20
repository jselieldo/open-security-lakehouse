from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class PlatformState(Base):
    __tablename__ = "platform_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    batch_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    normalized_object_key: Mapped[str | None] = mapped_column(Text)
    quarantine_object_key: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceCatalog(Base):
    __tablename__ = "source_catalog"

    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="unclassified")
    hostname: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    expected_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    configured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), index=True)
    primary_ip: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_addresses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    owner: Mapped[str | None] = mapped_column(String(200))
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssetChange(Base):
    __tablename__ = "asset_changes"

    change_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    old_value: Mapped[str | None] = mapped_column(String(500))
    new_value: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    alert_id: Mapped[str | None] = mapped_column(String(36), index=True)


class DetectionRun(Base):
    __tablename__ = "detection_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alert_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(100), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(64), index=True)
    asset_display_name: Mapped[str | None] = mapped_column(String(255))
    asset_criticality: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_subject: Mapped[str | None] = mapped_column(String(255), index=True)
    assignee_username: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertComment(Base):
    __tablename__ = "alert_comments"

    comment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.alert_id"), index=True)
    author_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    author_username: Mapped[str] = mapped_column(String(150), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class AlertHistory(Base):
    __tablename__ = "alert_history"

    history_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.alert_id"), index=True)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_username: Mapped[str] = mapped_column(String(150), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.alert_id"), index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255))
    roles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_username: Mapped[str] = mapped_column(String(150), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(500), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    client_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


def build_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)


def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
