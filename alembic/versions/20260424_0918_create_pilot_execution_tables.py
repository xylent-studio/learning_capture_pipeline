"""create pilot execution tables

Revision ID: 20260424_0918
Revises:
Create Date: 2026-04-24 09:18:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_0918"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pilot_batch",
        sa.Column("batch_id", sa.String(length=128), primary_key=True),
        sa.Column("account_alias", sa.String(length=255), nullable=False),
        sa.Column("runtime_config_path", sa.Text(), nullable=False),
        sa.Column("runtime_config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("runner_version", sa.String(length=64), nullable=False),
        sa.Column("artifact_root", sa.Text(), nullable=False),
        sa.Column("batch_status", sa.String(length=64), nullable=False),
        sa.Column("selected_course_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pilot_run",
        sa.Column("run_id", sa.String(length=128), primary_key=True),
        sa.Column("batch_id", sa.String(length=128), sa.ForeignKey("pilot_batch.batch_id"), nullable=False),
        sa.Column("capture_session_id", sa.String(length=128), nullable=False),
        sa.Column("course_title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("permission_basis", sa.String(length=255), nullable=False),
        sa.Column("rights_status", sa.String(length=128), nullable=False),
        sa.Column("account_alias", sa.String(length=255), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=64), nullable=False),
        sa.Column("run_manifest_path", sa.Text(), nullable=False),
        sa.Column("qa_report_path", sa.Text(), nullable=True),
        sa.Column("preflight_result_path", sa.Text(), nullable=True),
        sa.Column("preflight_status", sa.String(length=64), nullable=True),
        sa.Column("failure_bundle_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pilot_qa_summary",
        sa.Column("qa_summary_id", sa.String(length=128), primary_key=True),
        sa.Column("run_id", sa.String(length=128), sa.ForeignKey("pilot_run.run_id"), nullable=False),
        sa.Column("readiness_status", sa.String(length=64), nullable=False),
        sa.Column("recommended_status", sa.String(length=64), nullable=False),
        sa.Column("recapture_reasons", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("qa_report_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pilot_qa_summary")
    op.drop_table("pilot_run")
    op.drop_table("pilot_batch")
