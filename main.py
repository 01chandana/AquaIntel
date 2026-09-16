from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import engine, SessionLocal, Base
import models
import auth
import statistics
from dependencies import get_current_user, require_admin

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
def read_root():
    return {"message": "Welcome to AquaIntel"}

@app.get("/dashboard")
def dashboard():
    return FileResponse("dashboard.html")

@app.get("/assets-page")
def assets_page():
    return FileResponse("assets.html")

@app.get("/alerts-page")
def alerts_page():
    return FileResponse("alerts.html")

@app.get("/login-page")
def login_page():
    return FileResponse("login.html")

@app.get("/asset-detail")
def asset_detail_page():
    return FileResponse("asset-detail.html")

@app.get("/assets")
def get_assets():
    db = SessionLocal()
    assets = db.query(models.Asset).all()
    db.close()
    return assets

@app.get("/assets/{asset_id}")
def get_asset_detail(asset_id: int):
    db = SessionLocal()
    asset = db.query(models.Asset).filter(models.Asset.id == asset_id).first()
    readings = db.query(models.Telemetry).filter(models.Telemetry.asset_id == asset_id).all()
    db.close()

    if not asset:
        return {"error": "Asset not found"}

    return {
        "asset": {"id": asset.id, "name": asset.name, "status": asset.status},
        "readings": readings
    }

@app.get("/assets/{asset_id}/anomalies")
def detect_anomalies(asset_id: int):
    db = SessionLocal()
    readings = db.query(models.Telemetry).filter(models.Telemetry.asset_id == asset_id).all()
    db.close()

    values = [r.value for r in readings]
    if len(values) < 3:
        return {"message": "Not enough data yet (need at least 3 readings)", "anomalies": []}

    mean = statistics.mean(values)
    stdev = statistics.stdev(values)
    threshold = 2

    anomalies = []
    for r in readings:
        if stdev > 0 and abs(r.value - mean) > threshold * stdev:
            anomalies.append({
                "id": r.id,
                "value": r.value,
                "recorded_at": r.recorded_at,
                "deviation": round(abs(r.value - mean) / stdev, 2)
            })

    return {
        "mean": round(mean, 2),
        "std_dev": round(stdev, 2),
        "total_readings": len(values),
        "anomalies_found": len(anomalies),
        "anomalies": anomalies
    }

@app.get("/activity")
def get_recent_activity():
    db = SessionLocal()
    readings = db.query(models.Telemetry).order_by(models.Telemetry.recorded_at.desc()).limit(5).all()
    alerts = db.query(models.Alert).order_by(models.Alert.triggered_at.desc()).limit(5).all()
    db.close()

    events = []
    for r in readings:
        events.append({"type": "telemetry", "text": f"{r.reading_type} reading: {r.value} (asset {r.asset_id})", "time": r.recorded_at})
    for al in alerts:
        events.append({"type": "alert", "text": al.message, "time": al.triggered_at})

    events.sort(key=lambda e: e["time"], reverse=True)
    return events[:10]

@app.post("/assets")
def create_asset(name: str, status: str = "active", current_user: dict = Depends(require_admin)):
    db = SessionLocal()
    new_asset = models.Asset(name=name, status=status)
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    db.close()
    return new_asset

@app.put("/assets/{asset_id}")
def update_asset(asset_id: int, name: str, status: str, current_user: dict = Depends(require_admin)):
    db = SessionLocal()
    asset = db.query(models.Asset).filter(models.Asset.id == asset_id).first()
    if not asset:
        db.close()
        return {"error": "Asset not found"}

    asset.name = name
    asset.status = status
    db.commit()
    db.refresh(asset)
    db.close()
    return asset

@app.post("/telemetry")
def add_telemetry(asset_id: int, reading_type: str, value: float):
    db = SessionLocal()
    new_reading = models.Telemetry(asset_id=asset_id, reading_type=reading_type, value=value)
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

    rules = db.query(models.AlertRule).filter(
        models.AlertRule.asset_id == asset_id,
        models.AlertRule.reading_type == reading_type
    ).all()

    for rule in rules:
        if value > rule.max_value:
            alert = models.Alert(
                asset_id=asset_id,
                reading_type=reading_type,
                value=value,
                message=f"{reading_type} value {value} exceeded limit {rule.max_value}"
            )
            db.add(alert)
            db.commit()

    db.close()
    return new_reading

@app.get("/telemetry")
def get_telemetry():
    db = SessionLocal()
    readings = db.query(models.Telemetry).all()
    db.close()
    return readings

@app.post("/alert-rules")
def create_alert_rule(asset_id: int, reading_type: str, max_value: float, current_user: dict = Depends(require_admin)):
    db = SessionLocal()
    rule = models.AlertRule(asset_id=asset_id, reading_type=reading_type, max_value=max_value)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    db.close()
    return rule

@app.get("/alerts")
def get_alerts():
    db = SessionLocal()
    alerts = db.query(models.Alert).all()
    db.close()
    return alerts

@app.post("/signup")
def signup(email: str, password: str, role: str = "viewer"):
    db = SessionLocal()
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        db.close()
        return {"error": "Email already registered"}

    new_user = models.User(email=email, password_hash=auth.hash_password(password), role=role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    db.close()
    return {"id": new_user.id, "email": new_user.email, "role": new_user.role}

@app.post("/login")
def login(email: str, password: str):
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).first()
    db.close()

    if not user or not auth.verify_password(password, user.password_hash):
        return {"error": "Invalid email or password"}

    token = auth.create_access_token(user.email, user.role)
    return {"access_token": token, "token_type": "bearer", "role": user.role}

@app.get("/assets/{asset_id}/predict")
def predict_threshold_breach(asset_id: int, reading_type: str = "pressure", threshold: float = 80.0):
    db = SessionLocal()
    readings = db.query(models.Telemetry).filter(
        models.Telemetry.asset_id == asset_id,
        models.Telemetry.reading_type == reading_type
    ).order_by(models.Telemetry.recorded_at).all()
    db.close()

    if len(readings) < 4:
        return {"message": "Not enough data yet (need at least 4 readings)", "prediction": None}

    # Convert timestamps to seconds since first reading, for simple linear regression
    times = [(r.recorded_at - readings[0].recorded_at).total_seconds() for r in readings]
    values = [r.value for r in readings]

    n = len(times)
    mean_t = sum(times) / n
    mean_v = sum(values) / n

    numerator = sum((times[i] - mean_t) * (values[i] - mean_v) for i in range(n))
    denominator = sum((times[i] - mean_t) ** 2 for i in range(n))

    if denominator == 0:
        return {"message": "Not enough variation to predict a trend", "prediction": None}

    slope = numerator / denominator
    intercept = mean_v - slope * mean_t

    current_value = values[-1]

    if slope <= 0:
        return {
            "trend": "stable_or_decreasing",
            "current_value": current_value,
            "threshold": threshold,
            "message": "Value is stable or trending down — no breach predicted.",
            "prediction": None
        }

    # Solve for time when value = threshold: threshold = slope * t + intercept
    seconds_to_breach = (threshold - intercept) / slope - times[-1]

    if seconds_to_breach < 0:
        return {
            "trend": "increasing",
            "current_value": current_value,
            "threshold": threshold,
            "message": "Threshold already exceeded based on trend.",
            "prediction": None
        }

    hours_to_breach = round(seconds_to_breach / 3600, 2)

    return {
        "trend": "increasing",
        "current_value": current_value,
        "threshold": threshold,
        "estimated_hours_to_breach": hours_to_breach,
        "message": f"At current trend, {reading_type} may reach {threshold} in approximately {hours_to_breach} hours."
    }