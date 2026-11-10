import logging
import time
import uuid
from contextlib import asynccontextmanager

from eventsphere_common.security import hash_password
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import User, UserRole
from .routers import auth, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def ensure_bootstrap_admin() -> None:
    """Public registration cannot create admins, so the first one comes from env."""
    if not (settings.admin_email and settings.admin_password):
        return
    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == settings.admin_email)).scalar_one_or_none()
        if existing:
            if existing.role != UserRole.ADMIN:
                logging.getLogger("eventsphere.identity").warning("ADMIN_EMAIL belongs to a non-admin account; not changing it")
            return
        db.add(User(
            email=settings.admin_email,
            full_name="Platform Admin",
            password_hash=hash_password(settings.admin_password),
            role=UserRole.ADMIN,
        ))
        db.commit()
        logging.getLogger("eventsphere.identity").info("Created bootstrap admin account")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bootstrap_admin()
    yield


app = FastAPI(title="EventSphere Identity Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    start = time.time()
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    duration_ms = int((time.time() - start) * 1000)
    logging.getLogger("eventsphere.access").info(
        "%s %s %s status=%s duration_ms=%s corr_id=%s",
        settings.service_name, request.method, request.url.path, response.status_code, duration_ms, correlation_id,
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


app.include_router(auth.router)
app.include_router(users.router)
