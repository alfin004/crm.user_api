import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from attendance_router import router as attendance_router
import models
from auth import hash_password
from auth_routes import router as auth_router
from config import settings
from database import Base, SessionLocal, engine
from models import User
from user_routes import router as user_router


logger = logging.getLogger(__name__)


def create_tables() -> None:
    inspector = inspect(engine)

    existing_tables = set(inspector.get_table_names())

    Base.metadata.create_all(bind=engine)

    for table in Base.metadata.tables.keys():
        if table in existing_tables:
            logger.info(f"Database table already exists: {table}")
        else:
            logger.info(f"Database table created: {table}")


def seed_default_admin() -> None:
    if not settings.admin_password:
        logger.info("Default admin user skipped: ADMIN_PASSWORD is not configured")
        return

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").one_or_none()
        if admin is None:
            admin = User(
                username="admin",
                password_hash=hash_password(settings.admin_password),
                email="admin@example.com",
                role="ADMIN",
                is_active=True,
            )
            db.add(admin)
            logger.info("Default admin user created: admin")
        else:
            admin.password_hash = hash_password(settings.admin_password)
            admin.role = "ADMIN"
            admin.is_active = True
            logger.info("Default admin user updated from ADMIN_PASSWORD: admin")

        db.commit()
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="User Management API")
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    create_tables()
    seed_default_admin()

    app.include_router(auth_router)
    app.include_router(user_router)
    app.include_router(attendance_router)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


__all__ = ["app", "models"]
