import getpass
import os

from database import Base, SessionLocal, engine
import auth
import models

Base.metadata.create_all(bind=engine)

email = input("Admin email: ").strip().lower()
password = getpass.getpass("Admin password (8-72 UTF-8 bytes): ")
confirm = getpass.getpass("Confirm password: ")

if password != confirm:
    raise SystemExit("Passwords do not match.")
if len(password) < 8 or len(password.encode("utf-8")) > 72:
    raise SystemExit("Password must be 8-72 UTF-8 bytes.")

with SessionLocal() as db:
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        existing.role = "admin"
        existing.password_hash = auth.hash_password(password)
    else:
        db.add(models.User(email=email, password_hash=auth.hash_password(password), role="admin"))
    db.commit()

print(f"Admin account ready: {email}")
