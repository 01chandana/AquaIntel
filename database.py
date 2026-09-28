import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
configured_url = os.getenv("DATABASE_URL", "").strip()

if not configured_url:
    DATABASE_URL = "sqlite:///" + os.path.join(BASE_DIR, "aquaintel.db")
elif configured_url.startswith("sqlite:///./"):
    relative_path = configured_url[len("sqlite:///./"):]
    DATABASE_URL = "sqlite:///" + os.path.abspath(os.path.join(BASE_DIR, relative_path))
else:
    DATABASE_URL = configured_url

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
