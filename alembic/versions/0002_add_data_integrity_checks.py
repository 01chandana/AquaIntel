"""add database integrity checks

Revision ID: 0002_integrity_checks
Revises: 0001_initial
"""
from alembic import op

revision = "0002_integrity_checks"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assets") as batch:
        batch.create_check_constraint(
            "ck_assets_status",
            "status IN ('active','maintenance','inactive')",
        )
    with op.batch_alter_table("telemetry") as batch:
        batch.create_check_constraint(
            "ck_telemetry_reading_type",
            "length(reading_type) > 0",
        )
    with op.batch_alter_table("alert_rules") as batch:
        batch.create_check_constraint(
            "ck_alert_rules_reading_type",
            "length(reading_type) > 0",
        )


def downgrade():
    with op.batch_alter_table("alert_rules") as batch:
        batch.drop_constraint("ck_alert_rules_reading_type", type_="check")
    with op.batch_alter_table("telemetry") as batch:
        batch.drop_constraint("ck_telemetry_reading_type", type_="check")
    with op.batch_alter_table("assets") as batch:
        batch.drop_constraint("ck_assets_status", type_="check")
