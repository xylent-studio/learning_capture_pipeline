from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PilotBatchRecord(Base):
    __tablename__ = "pilot_batch"

    batch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    account_alias: Mapped[str] = mapped_column(String(255))
    runtime_config_path: Mapped[str] = mapped_column(Text())
    runtime_config_fingerprint: Mapped[str] = mapped_column(String(64))
    runner_version: Mapped[str] = mapped_column(String(64))
    artifact_root: Mapped[str] = mapped_column(Text())
    batch_status: Mapped[str] = mapped_column(String(64))
    selected_course_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)

    runs: Mapped[list["PilotRunRecord"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class PilotRunRecord(Base):
    __tablename__ = "pilot_run"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("pilot_batch.batch_id"))
    capture_session_id: Mapped[str] = mapped_column(String(128))
    course_title: Mapped[str] = mapped_column(Text())
    source_url: Mapped[str] = mapped_column(Text())
    permission_basis: Mapped[str] = mapped_column(String(255))
    rights_status: Mapped[str] = mapped_column(String(128))
    account_alias: Mapped[str] = mapped_column(String(255))
    lifecycle_status: Mapped[str] = mapped_column(String(64))
    run_manifest_path: Mapped[str] = mapped_column(Text())
    qa_report_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    preflight_result_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    preflight_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_bundle_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)

    batch: Mapped[PilotBatchRecord] = relationship(back_populates="runs")
    qa_summary: Mapped["PilotQaSummaryRecord | None"] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )


class PilotQaSummaryRecord(Base):
    __tablename__ = "pilot_qa_summary"

    qa_summary_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pilot_run.run_id"))
    readiness_status: Mapped[str] = mapped_column(String(64))
    recommended_status: Mapped[str] = mapped_column(String(64))
    recapture_reasons: Mapped[str] = mapped_column(Text())
    warnings: Mapped[str] = mapped_column(Text())
    qa_report_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)

    run: Mapped[PilotRunRecord] = relationship(back_populates="qa_summary")
