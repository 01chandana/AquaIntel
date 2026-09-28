"""initial AquaIntel schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.create_index("ix_assets_id", "assets", ["id"], unique=False)
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("telemetry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("reading_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_telemetry_id", "telemetry", ["id"], unique=False)
    op.create_index("ix_telemetry_asset_id", "telemetry", ["asset_id"], unique=False)
    op.create_index("ix_telemetry_reading_type", "telemetry", ["reading_type"], unique=False)
    op.create_index("ix_telemetry_recorded_at", "telemetry", ["recorded_at"], unique=False)
    op.create_table("alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("reading_type", sa.String(length=50), nullable=False),
        sa.Column("max_value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("asset_id", "reading_type", name="uq_alert_rule_asset_type"),
    )
    op.create_index("ix_alert_rules_id", "alert_rules", ["id"], unique=False)
    op.create_index("ix_alert_rules_asset_id", "alert_rules", ["asset_id"], unique=False)
    op.create_table("alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("reading_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alerts_id", "alerts", ["id"], unique=False)
    op.create_index("ix_alerts_asset_id", "alerts", ["asset_id"], unique=False)
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"], unique=False)
    op.create_index("ix_alerts_acknowledged", "alerts", ["acknowledged"], unique=False)


def downgrade():
    op.drop_table("alerts")
    op.drop_table("alert_rules")
    op.drop_table("telemetry")
    op.drop_table("users")
    op.drop_table("assets")
