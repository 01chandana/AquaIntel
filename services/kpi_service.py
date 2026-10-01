from datetime import datetime, timedelta, timezone
from math import isfinite

from sqlalchemy.orm import Session

from models import Asset, Telemetry


def _window_start(hours: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=hours
    )


def _calculate_statistics(values: list[float]) -> dict:
    if not values:
        return {
            "count": 0,
            "average": None,
            "minimum": None,
            "maximum": None,
        }

    return {
        "count": len(values),
        "average": sum(values) / len(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def get_asset_kpis(
    db: Session,
    asset_id: int,
    hours: int = 24,
) -> dict:
    """Calculate operational KPIs from telemetry for one asset."""

    if hours < 1 or hours > 168:
        raise ValueError("hours must be between 1 and 168")

    asset = db.query(Asset).filter(Asset.id == asset_id).first()

    if asset is None:
        raise ValueError("Asset not found")

    readings = (
        db.query(Telemetry)
        .filter(
            Telemetry.asset_id == asset_id,
            Telemetry.recorded_at >= _window_start(hours),
        )
        .order_by(Telemetry.recorded_at.asc())
        .all()
    )

    valid_readings = [
        reading
        for reading in readings
        if isfinite(reading.value)
    ]

    values = [
        reading.value
        for reading in valid_readings
    ]

    overall = _calculate_statistics(values)

    by_reading_type: dict[str, dict] = {}

    for reading in valid_readings:
        reading_type = reading.reading_type

        by_reading_type.setdefault(
            reading_type,
            [],
        ).append(reading.value)

    by_reading_type = {
        reading_type: _calculate_statistics(type_values)
        for reading_type, type_values in sorted(
            by_reading_type.items()
        )
    }

    return {
        "asset_id": asset.id,
        "asset_name": asset.name,
        "status": asset.status,
        "window_hours": hours,
        "telemetry_count": len(valid_readings),
        "reading_type_count": len(by_reading_type),
        "reading_types": list(by_reading_type.keys()),
        "average_value": overall["average"],
        "minimum_value": overall["minimum"],
        "maximum_value": overall["maximum"],
        "by_reading_type": by_reading_type,
    }