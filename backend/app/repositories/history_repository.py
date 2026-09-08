from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend.app.core.config import settings


class HistoryStorageUnavailable(RuntimeError):
    """The common PostgreSQL server cannot be used right now."""


class Base(DeclarativeBase):
    pass


class AnalysisHistoryRecord(Base):
    __tablename__ = "ky_analysis_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    work_content: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    main_risk: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    image_name: Mapped[str] = mapped_column(String(500), nullable=False)
    image_mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="image/jpeg")
    photo_relative_path: Mapped[str] = mapped_column(String(700), nullable=False)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_display_label: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)


class HistoryRepository:
    def __init__(self) -> None:
        self._engine = None
        self._session_factory = None

    def _ensure_database(self) -> None:
        if self._session_factory is not None:
            return
        if not settings.DATABASE_URL.strip():
            raise HistoryStorageUnavailable("DATABASE_URL is not configured")
        try:
            engine_options = {"pool_pre_ping": True}
            if settings.DATABASE_URL.startswith("postgresql"):
                engine_options.update({"pool_size": 5, "max_overflow": 5, "connect_args": {"connect_timeout": 5}})
            self._engine = create_engine(settings.DATABASE_URL, **engine_options)
            self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        except SQLAlchemyError as exc:
            raise HistoryStorageUnavailable("Cannot configure PostgreSQL") from exc

    def initialize_schema(self) -> None:
        self._ensure_database()
        try:
            assert self._engine is not None
            Base.metadata.create_all(self._engine)
        except SQLAlchemyError as exc:
            raise HistoryStorageUnavailable("Cannot initialize PostgreSQL schema") from exc

    @contextmanager
    def session(self):
        self._ensure_database()
        assert self._session_factory is not None
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except (OperationalError, SQLAlchemyError) as exc:
            db.rollback()
            raise HistoryStorageUnavailable("PostgreSQL connection failed") from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list(self, *, created_from: datetime | None = None, created_to: datetime | None = None,
             site_name: str | None = None, work_content: str | None = None,
             created_by: str | None = None, keyword: str | None = None) -> list[AnalysisHistoryRecord]:
        with self.session() as db:
            stmt = select(AnalysisHistoryRecord).where(AnalysisHistoryRecord.deleted_at.is_(None))
            if created_from:
                stmt = stmt.where(AnalysisHistoryRecord.created_at >= created_from)
            if created_to:
                stmt = stmt.where(AnalysisHistoryRecord.created_at < created_to)
            if site_name:
                stmt = stmt.where(AnalysisHistoryRecord.site_name.ilike(f"%{site_name}%"))
            if work_content:
                stmt = stmt.where(AnalysisHistoryRecord.work_content.ilike(f"%{work_content}%"))
            if created_by:
                stmt = stmt.where(AnalysisHistoryRecord.created_by.ilike(f"%{created_by}%"))
            if keyword:
                term = f"%{keyword}%"
                stmt = stmt.where(
                    AnalysisHistoryRecord.site_name.ilike(term)
                    | AnalysisHistoryRecord.work_content.ilike(term)
                    | AnalysisHistoryRecord.main_risk.ilike(term)
                    | AnalysisHistoryRecord.markdown.ilike(term)
                    | AnalysisHistoryRecord.image_name.ilike(term)
                )
            return list(db.scalars(stmt.order_by(AnalysisHistoryRecord.created_at.desc())).all())

    def get(self, entry_id: str) -> AnalysisHistoryRecord | None:
        with self.session() as db:
            return db.scalar(select(AnalysisHistoryRecord).where(
                AnalysisHistoryRecord.id == entry_id,
                AnalysisHistoryRecord.deleted_at.is_(None),
            ))

    def get_any(self, entry_id: str) -> AnalysisHistoryRecord | None:
        """Find a record even if it has already been logically deleted."""
        with self.session() as db:
            return db.scalar(select(AnalysisHistoryRecord).where(AnalysisHistoryRecord.id == entry_id))

    def add(self, record: AnalysisHistoryRecord) -> AnalysisHistoryRecord:
        with self.session() as db:
            db.add(record)
        return record

    def soft_delete(self, entry_id: str, deleted_at: datetime) -> bool:
        with self.session() as db:
            record = db.scalar(select(AnalysisHistoryRecord).where(
                AnalysisHistoryRecord.id == entry_id,
                AnalysisHistoryRecord.deleted_at.is_(None),
            ))
            if record is None:
                return False
            record.deleted_at = deleted_at
            record.updated_at = deleted_at
            return True


history_repository = HistoryRepository()
