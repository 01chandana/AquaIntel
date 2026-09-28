from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (CheckConstraint("status IN ('active','maintenance','inactive')", name="ck_assets_status"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="active")

    telemetry = relationship("Telemetry", cascade="all, delete-orphan", back_populates="asset")
    rules = relationship("AlertRule", cascade="all, delete-orphan", back_populates="asset")
    alerts = relationship("Alert", cascade="all, delete-orphan", back_populates="asset")


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        CheckConstraint("length(reading_type) > 0", name="ck_telemetry_reading_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    reading_type = Column(String(50), nullable=False, index=True)
    value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)

    asset = relationship("Asset", back_populates="telemetry")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint("asset_id", "reading_type", name="uq_alert_rule_asset_type"),
        CheckConstraint("length(reading_type) > 0", name="ck_alert_rules_reading_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    reading_type = Column(String(50), nullable=False)
    max_value = Column(Float, nullable=False)

    asset = relationship("Asset", back_populates="rules")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    reading_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    message = Column(String(500), nullable=False)
    triggered_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    acknowledged_at = Column(DateTime, nullable=True)

    asset = relationship("Asset", back_populates="alerts")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
