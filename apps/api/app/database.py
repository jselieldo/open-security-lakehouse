from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, create_engine, text
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
