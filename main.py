import logging
import math
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

import numpy as np

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError

import auth
import models
from database import SessionLocal
from dependencies import get_current_user, require_admin


# ============================================================
# Application setup
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


# ============================================================
# Production logging
# ============================================================

LOG_LEVEL = os.getenv("AQUAINTEL_LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("aquaintel")


app = FastAPI(
    title="AquaIntel API",
    version="2.0.0",
)


# ============================================================
# Request / response logging
# ============================================================

@app.middleware("http")
async def request_logging(request: Request, call_next):
    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "%s %s -> %s (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response

    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.exception(
            "%s %s failed after %.2f ms",
            request.method,
            request.url.path,
            duration_ms,
        )

        raise


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error: %s %s",
        request.method,
        request.url.path,
    )

    errors = []

    for error in exc.errors():
        errors.append({
            "type": error.get("type"),
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg"),
        })

    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )


# ============================================================
# CORS
# ============================================================

cors_origins = [
    x.strip()
    for x in os.getenv("AQUAINTEL_CORS_ORIGINS", "").split(",")
    if x.strip()
]

if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


# ============================================================
# Security headers
# ============================================================

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    # Swagger UI uses assets from jsdelivr.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    return response


# ============================================================
# Request models
# ============================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class SignupRequest(LoginRequest):
    pass


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    status: Literal["active", "maintenance", "inactive"] = "active"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Asset name is required")

        return value


class AssetUpdate(AssetCreate):
    pass


class TelemetryCreate(BaseModel):
    asset_id: int = Field(gt=0)
    reading_type: str = Field(min_length=1, max_length=50)
    value: float
    recorded_at: datetime | None = None

    @field_validator("reading_type")
    @classmethod
    def clean_type(cls, value):
        value = value.strip().lower()

        if not re.fullmatch(r"[a-z0-9_-]+", value):
            raise ValueError(
                "Reading type may contain only letters, numbers, "
                "hyphens and underscores"
            )

        return value

    @field_validator("value")
    @classmethod
    def finite_value(cls, value):
        if not math.isfinite(value):
            raise ValueError("Telemetry value must be finite")

        return value


class AlertRuleCreate(BaseModel):
    asset_id: int = Field(gt=0)
    reading_type: str = Field(min_length=1, max_length=50)
    max_value: float

    @field_validator("reading_type")
    @classmethod
    def clean_type(cls, value):
        value = value.strip().lower()

        if not re.fullmatch(r"[a-z0-9_-]+", value):
            raise ValueError(
                "Reading type may contain only letters, numbers, "
                "hyphens and underscores"
            )

        return value

    @field_validator("max_value")
    @classmethod
    def finite_max(cls, value):
        if not math.isfinite(value):
            raise ValueError("Maximum value must be finite")

        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str


# ============================================================
# Login rate limiting
# ============================================================

FAILED_LOGINS: dict[str, deque[float]] = defaultdict(deque)

LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_FAILURES = 5


def _prune_login_attempts(now: float):
    stale = []

    for key, attempts in FAILED_LOGINS.items():
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()

        if not attempts:
            stale.append(key)

    for key in stale:
        FAILED_LOGINS.pop(key, None)


def _check_login_rate_limit(keys):
    now = time.monotonic()

    _prune_login_attempts(now)

    for key in keys:
        if len(FAILED_LOGINS[key]) >= LOGIN_MAX_FAILURES:
            logger.warning("Login rate limit triggered")
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


def _record_login_failure(keys):
    now = time.monotonic()

    for key in keys:
        FAILED_LOGINS[key].append(now)


def _clear_login_failures(keys):
    for key in keys:
        FAILED_LOGINS.pop(key, None)


# ============================================================
# Date/time helpers
# ============================================================

def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


def _iso(value: datetime | None):
    if value is None:
        return None

    return (
        value.replace(tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ============================================================
# Serialization helpers
# ============================================================

def _asset_dict(asset):
    return {
        "id": asset.id,
        "name": asset.name,
        "status": asset.status,
    }


def _reading_dict(reading):
    return {
        "id": reading.id,
        "asset_id": reading.asset_id,
        "reading_type": reading.reading_type,
        "value": reading.value,
        "recorded_at": _iso(reading.recorded_at),
    }


def _rule_dict(rule):
    return {
        "id": rule.id,
        "asset_id": rule.asset_id,
        "reading_type": rule.reading_type,
        "max_value": rule.max_value,
    }


def _alert_dict(alert):
    return {
        "id": alert.id,
        "asset_id": alert.asset_id,
        "reading_type": alert.reading_type,
        "value": alert.value,
        "message": alert.message,
        "triggered_at": _iso(alert.triggered_at),
        "acknowledged": alert.acknowledged,
        "acknowledged_at": _iso(alert.acknowledged_at),
    }


# ============================================================
# Frontend pages
# ============================================================

def page(name: str):
    return FileResponse(os.path.join(BASE_DIR, name))


@app.get("/", include_in_schema=False)
def read_root():
    return {
        "message": "Welcome to AquaIntel",
        "docs": "/docs",
        "login": "/login-page",
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return page("dashboard.html")


@app.get("/assets-page", include_in_schema=False)
def assets_page():
    return page("assets.html")


@app.get("/alerts-page", include_in_schema=False)
def alerts_page():
    return page("alerts.html")


@app.get("/login-page", include_in_schema=False)
def login_page():
    return page("login.html")


@app.get("/asset-detail", include_in_schema=False)
def asset_detail_page():
    return page("asset-detail.html")


# Only expose the dedicated static directory.
app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


# ============================================================
# Assets
# ============================================================

@app.get("/assets")
def get_assets(current_user=Depends(get_current_user)):
    db = SessionLocal()

    try:
        return [
            _asset_dict(asset)
            for asset in db.query(models.Asset)
            .order_by(models.Asset.id)
            .all()
        ]

    finally:
        db.close()


@app.get("/assets/{asset_id}")
def get_asset_detail(
    asset_id: int,
    reading_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == asset_id)
            .first()
        )

        if not asset:
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        q = db.query(models.Telemetry).filter(
            models.Telemetry.asset_id == asset_id
        )

        if reading_type:
            normalized_type = reading_type.strip().lower()

            if not re.fullmatch(
                r"[a-z0-9_-]+",
                normalized_type,
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid reading type",
                )

            q = q.filter(
                models.Telemetry.reading_type == normalized_type
            )

        readings = (
            q.order_by(models.Telemetry.recorded_at.desc())
            .limit(limit)
            .all()
        )

        readings.reverse()

        return {
            "asset": _asset_dict(asset),
            "readings": [
                _reading_dict(reading)
                for reading in readings
            ],
        }

    finally:
        db.close()


@app.post("/assets", status_code=201)
def create_asset(
    data: AssetCreate,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        new_asset = models.Asset(
            name=data.name,
            status=data.status,
        )

        db.add(new_asset)
        db.commit()
        db.refresh(new_asset)

        return _asset_dict(new_asset)

    finally:
        db.close()


@app.put("/assets/{asset_id}")
def update_asset(
    asset_id: int,
    data: AssetUpdate,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == asset_id)
            .first()
        )

        if not asset:
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        asset.name = data.name
        asset.status = data.status

        db.commit()
        db.refresh(asset)

        return _asset_dict(asset)

    finally:
        db.close()


@app.delete("/assets/{asset_id}", status_code=204)
def delete_asset(
    asset_id: int,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == asset_id)
            .first()
        )

        if not asset:
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        db.delete(asset)
        db.commit()

    finally:
        db.close()


# ============================================================
# Telemetry
# ============================================================

@app.post("/telemetry", status_code=201)
def add_telemetry(
    data: TelemetryCreate,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == data.asset_id)
            .first()
        )

        if not asset:
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        recorded_at = _utc(data.recorded_at)

        new_reading = models.Telemetry(
            asset_id=data.asset_id,
            reading_type=data.reading_type,
            value=data.value,
            recorded_at=recorded_at,
        )

        db.add(new_reading)
        db.flush()

        rules = (
            db.query(models.AlertRule)
            .filter(
                models.AlertRule.asset_id == data.asset_id,
                models.AlertRule.reading_type == data.reading_type,
            )
            .all()
        )

        for rule in rules:
            if data.value > rule.max_value:
                db.add(
                    models.Alert(
                        asset_id=data.asset_id,
                        reading_type=data.reading_type,
                        value=data.value,
                        message=(
                            f"{data.reading_type} value {data.value} "
                            f"exceeded limit {rule.max_value}"
                        ),
                    )
                )

        db.commit()
        db.refresh(new_reading)

        return _reading_dict(new_reading)

    except HTTPException:
        db.rollback()
        raise

    finally:
        db.close()


@app.get("/telemetry")
def get_telemetry(
    asset_id: int | None = Query(
        default=None,
        gt=0,
    ),
    reading_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        q = db.query(models.Telemetry)

        if asset_id:
            q = q.filter(
                models.Telemetry.asset_id == asset_id
            )

        if reading_type:
            normalized_type = reading_type.strip().lower()

            if not re.fullmatch(
                r"[a-z0-9_-]+",
                normalized_type,
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid reading type",
                )

            q = q.filter(
                models.Telemetry.reading_type == normalized_type
            )

        rows = (
            q.order_by(models.Telemetry.recorded_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            _reading_dict(reading)
            for reading in rows
        ]

    finally:
        db.close()


# ============================================================
# Shared analytics helper
# ============================================================

def _get_readings_for_asset(
    db,
    asset_id: int,
    reading_type: str,
):
    asset = (
        db.query(models.Asset)
        .filter(models.Asset.id == asset_id)
        .first()
    )

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    return (
        db.query(models.Telemetry)
        .filter(
            models.Telemetry.asset_id == asset_id,
            models.Telemetry.reading_type == reading_type,
        )
        .order_by(models.Telemetry.recorded_at)
        .all()
    )


# ============================================================
# Statistical anomaly detection
# ============================================================

@app.get("/assets/{asset_id}/anomalies")
def detect_anomalies(
    asset_id: int,
    reading_type: str = Query(
        default="pressure",
        min_length=1,
        max_length=50,
    ),
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        reading_type = reading_type.strip().lower()

        if not re.fullmatch(
            r"[a-z0-9_-]+",
            reading_type,
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid reading type",
            )

        readings = _get_readings_for_asset(
            db,
            asset_id,
            reading_type,
        )

        values = [
            reading.value
            for reading in readings
        ]

        if len(values) < 3:
            return {
                "message": "Not enough data yet (need at least 3 readings)",
                "anomalies": [],
            }

        mean = float(np.mean(values))
        stdev = float(np.std(values, ddof=1))

        anomalies = []

        for reading in readings:
            if (
                stdev > 0
                and abs(reading.value - mean) > 2 * stdev
            ):
                anomalies.append(
                    {
                        "id": reading.id,
                        "value": reading.value,
                        "recorded_at": _iso(
                            reading.recorded_at
                        ),
                        "deviation": round(
                            abs(reading.value - mean) / stdev,
                            2,
                        ),
                    }
                )

        return {
            "reading_type": reading_type,
            "mean": round(mean, 2),
            "std_dev": round(stdev, 2),
            "total_readings": len(values),
            "anomalies_found": len(anomalies),
            "anomalies": anomalies,
        }

    finally:
        db.close()


# ============================================================
# ML anomaly detection
# ============================================================

@app.get("/assets/{asset_id}/ml-anomalies")
def ml_anomaly_detection(
    asset_id: int,
    reading_type: str = Query(
        default="pressure",
        min_length=1,
        max_length=50,
    ),
    hours: int = Query(
        default=24,
        ge=1,
        le=168,
    ),
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        reading_type = reading_type.strip().lower()

        if not re.fullmatch(
            r"[a-z0-9_-]+",
            reading_type,
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid reading type",
            )

        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == asset_id)
            .first()
        )

        if not asset:
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        cutoff = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=hours)
        )

        readings = (
            db.query(models.Telemetry)
            .filter(
                models.Telemetry.asset_id == asset_id,
                models.Telemetry.reading_type == reading_type,
                models.Telemetry.recorded_at >= cutoff,
            )
            .order_by(models.Telemetry.recorded_at)
            .all()
        )

        if len(readings) < 10:
            return {
                "message": (
                    f"Not enough recent data yet "
                    f"(need at least 10 readings in the last {hours} hours)"
                ),
                "anomalies": [],
            }

        values = np.array(
            [
                [reading.value]
                for reading in readings
            ],
            dtype=float,
        )

        from sklearn.ensemble import IsolationForest

        model = IsolationForest(
            n_estimators=100,
            contamination="auto",
            random_state=42,
        )

        model.fit(values)

        predictions = model.predict(values)
        scores = model.decision_function(values)

        anomalies = [
            {
                "id": reading.id,
                "value": reading.value,
                "recorded_at": _iso(
                    reading.recorded_at
                ),
                "anomaly_score": round(
                    float(scores[index]),
                    4,
                ),
            }
            for index, reading in enumerate(readings)
            if predictions[index] == -1
        ]

        return {
            "model": "IsolationForest (scikit-learn)",
            "reading_type": reading_type,
            "total_readings": len(values),
            "anomalies_found": len(anomalies),
            "anomalies": anomalies,
        }

    finally:
        db.close()


# ============================================================
# Predictive maintenance
# ============================================================

@app.get("/assets/{asset_id}/predict")
def predict_threshold_breach(
    asset_id: int,
    reading_type: str = Query(
        default="pressure",
        min_length=1,
        max_length=50,
    ),
    threshold: float = Query(
        ...,
        ge=-1_000_000,
        le=1_000_000,
    ),
    current_user=Depends(get_current_user),
):
    if not math.isfinite(threshold):
        raise HTTPException(
            status_code=422,
            detail="Threshold must be finite",
        )

    db = SessionLocal()

    try:
        reading_type = reading_type.strip().lower()

        if not re.fullmatch(
            r"[a-z0-9_-]+",
            reading_type,
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid reading type",
            )

        readings = _get_readings_for_asset(
            db,
            asset_id,
            reading_type,
        )

        if len(readings) < 4:
            return {
                "message": "Not enough data yet (need at least 4 readings)",
                "prediction": None,
            }

        times = [
            (
                reading.recorded_at
                - readings[0].recorded_at
            ).total_seconds()
            for reading in readings
        ]

        values = [
            reading.value
            for reading in readings
        ]

        n = len(times)

        mean_t = sum(times) / n
        mean_v = sum(values) / n

        denominator = sum(
            (t - mean_t) ** 2
            for t in times
        )

        if denominator == 0:
            return {
                "message": (
                    "Not enough time variation to predict a trend"
                ),
                "prediction": None,
            }

        numerator = sum(
            (times[i] - mean_t)
            * (values[i] - mean_v)
            for i in range(n)
        )

        slope = numerator / denominator
        intercept = mean_v - slope * mean_t

        current_value = values[-1]

        if slope <= 0:
            return {
                "trend": "stable_or_decreasing",
                "current_value": current_value,
                "threshold": threshold,
                "message": (
                    "Value is stable or trending down — "
                    "no breach predicted."
                ),
                "prediction": None,
            }

        seconds_to_breach = (
            (threshold - intercept) / slope
            - times[-1]
        )

        if seconds_to_breach < 0:
            return {
                "trend": "increasing",
                "current_value": current_value,
                "threshold": threshold,
                "message": (
                    "Threshold already exceeded based on trend."
                ),
                "prediction": None,
            }

        hours_to_breach = round(
            seconds_to_breach / 3600,
            2,
        )

        return {
            "trend": "increasing",
            "current_value": current_value,
            "threshold": threshold,
            "estimated_hours_to_breach": hours_to_breach,
            "message": (
                f"At current trend, {reading_type} may reach "
                f"{threshold} in approximately "
                f"{hours_to_breach} hours."
            ),
        }

    finally:
        db.close()


# ============================================================
# Alert rules
# ============================================================

@app.post("/alert-rules", status_code=201)
def create_alert_rule(
    data: AlertRuleCreate,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        asset = (
            db.query(models.Asset)
            .filter(models.Asset.id == data.asset_id)
            .first()
        )

        if not asset:
            raise HTTPException(
                status_code=404,
                detail="Asset not found",
            )

        rule = models.AlertRule(
            asset_id=data.asset_id,
            reading_type=data.reading_type,
            max_value=data.max_value,
        )

        db.add(rule)

        try:
            db.commit()

        except IntegrityError:
            db.rollback()

            raise HTTPException(
                status_code=409,
                detail=(
                    "An alert rule already exists "
                    "for this asset and reading type"
                ),
            )

        db.refresh(rule)

        return _rule_dict(rule)

    finally:
        db.close()


@app.get("/alert-rules")
def get_alert_rules(
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        return [
            _rule_dict(rule)
            for rule in db.query(models.AlertRule)
            .order_by(models.AlertRule.id)
            .all()
        ]

    finally:
        db.close()


@app.delete("/alert-rules/{rule_id}", status_code=204)
def delete_alert_rule(
    rule_id: int,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        rule = (
            db.query(models.AlertRule)
            .filter(models.AlertRule.id == rule_id)
            .first()
        )

        if not rule:
            raise HTTPException(
                status_code=404,
                detail="Alert rule not found",
            )

        db.delete(rule)
        db.commit()

    finally:
        db.close()


# ============================================================
# Alerts
# ============================================================

@app.get("/alerts")
def get_alerts(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    active_only: bool = False,
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        q = db.query(models.Alert)

        if active_only:
            q = q.filter(
                models.Alert.acknowledged.is_(False)
            )

        alerts = (
            q.order_by(models.Alert.triggered_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            _alert_dict(alert)
            for alert in alerts
        ]

    finally:
        db.close()


@app.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user=Depends(require_admin),
):
    db = SessionLocal()

    try:
        alert = (
            db.query(models.Alert)
            .filter(models.Alert.id == alert_id)
            .first()
        )

        if not alert:
            raise HTTPException(
                status_code=404,
                detail="Alert not found",
            )

        alert.acknowledged = True
        alert.acknowledged_at = (
            datetime.now(timezone.utc)
            .replace(tzinfo=None)
        )

        db.commit()
        db.refresh(alert)

        return _alert_dict(alert)

    finally:
        db.close()


# ============================================================
# Activity
# ============================================================

@app.get("/activity")
def get_recent_activity(
    current_user=Depends(get_current_user),
):
    db = SessionLocal()

    try:
        readings = (
            db.query(models.Telemetry)
            .order_by(
                models.Telemetry.recorded_at.desc()
            )
            .limit(5)
            .all()
        )

        alerts = (
            db.query(models.Alert)
            .order_by(
                models.Alert.triggered_at.desc()
            )
            .limit(5)
            .all()
        )

        events = [
            {
                "type": "telemetry",
                "text": (
                    f"{reading.reading_type} reading: "
                    f"{reading.value} "
                    f"(asset {reading.asset_id})"
                ),
                "time": _iso(
                    reading.recorded_at
                ),
            }
            for reading in readings
        ]

        events += [
            {
                "type": "alert",
                "text": alert.message,
                "time": _iso(
                    alert.triggered_at
                ),
            }
            for alert in alerts
        ]

        events.sort(
            key=lambda event: event["time"] or "",
            reverse=True,
        )

        return events[:10]

    finally:
        db.close()


# ============================================================
# Current user
# ============================================================

@app.get("/me")
def me(
    current_user=Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }


# ============================================================
# Signup
# ============================================================

@app.post(
    "/signup",
    status_code=201,
    response_model=UserResponse,
)
def signup(data: SignupRequest):
    email = data.email.lower()

    db = SessionLocal()

    try:
        existing_user = (
            db.query(models.User)
            .filter(models.User.email == email)
            .first()
        )

        if existing_user:
            raise HTTPException(
                status_code=409,
                detail="Email already registered",
            )

        # Public signup always creates Viewer accounts.
        new_user = models.User(
            email=email,
            password_hash=auth.hash_password(
                data.password
            ),
            role="viewer",
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("New viewer account created")

        return new_user

    finally:
        db.close()


# ============================================================
# Login
# ============================================================

@app.post("/login")
def login(
    data: LoginRequest,
    request: Request,
):
    ip = request.client.host if request.client else "unknown"
    email = data.email.lower()

    keys = [
        f"ip:{ip}",
        f"email:{email}",
    ]

    _check_login_rate_limit(keys)

    db = SessionLocal()

    try:
        user = (
            db.query(models.User)
            .filter(models.User.email == email)
            .first()
        )

        if not user or not auth.verify_password(
            data.password,
            user.password_hash,
        ):
            _record_login_failure(keys)

            logger.warning(
                "Failed login attempt from IP %s",
                ip,
            )

            raise HTTPException(
                status_code=401,
                detail="Invalid email or password",
            )

        _clear_login_failures(keys)

        token = auth.create_access_token(
            user.email,
            user.role,
        )

        logger.info(
            "Successful login from IP %s",
            ip,
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "role": user.role,
        }

    finally:
        db.close()