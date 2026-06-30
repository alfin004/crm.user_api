"""
attendance_router.py

Template attendance router for FastAPI.
NOTE:
- Update imports to match your project.
- Assumes SQLAlchemy 2.0, get_db, get_current_user, Attendance model, User model,
  settings.attendance_config.
"""

from datetime import date, datetime
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

# Update these imports
from database import get_db
from auth import get_current_user
from config import settings
from models import Attendance, User

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _calculate_status(minutes: int) -> str:
    hours = minutes / 60
    env_value = settings.attendance_config
    cfg = json.loads(env_value)
    if hours >= cfg["Full_day"]:
        return "FULL_DAY"
    if hours >= cfg["Half_day"]:
        return "HALF_DAY"
    return "ABSENT"


@router.post("/punch-in")
def punch_in(
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(get_current_user),
):
    today = date.today()

    existing = db.scalar(
        select(Attendance).where(
            Attendance.user_id == current_user.id,
            Attendance.attendance_date == today,
        )
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already punched in today.",
        )

    attendance = Attendance(
        user_id=current_user.id,
        attendance_date=today,
        punch_in=datetime.now(),
        status="IN_PROGRESS",
    )

    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    return {
        "message": "Punch in successful",
        "attendance": attendance,
    }


@router.post("/punch-out")
def punch_out(
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(get_current_user),
):
    today = date.today()

    attendance = db.scalar(
        select(Attendance).where(
            Attendance.user_id == current_user.id,
            Attendance.attendance_date == today,
        )
    )

    if attendance is None:
        raise HTTPException(404, "Punch in not found.")

    if attendance.punch_out:
        raise HTTPException(400, "Already punched out.")

    attendance.punch_out = datetime.now()

    minutes = int(
        (attendance.punch_out - attendance.punch_in).total_seconds() / 60
    )

    attendance.working_minutes = minutes
    attendance.status = _calculate_status(minutes)

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Punch out successful",
        "attendance": attendance,
    }


@router.get("/today")
def today_attendance(
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(get_current_user),
):
    attendance = db.scalar(
        select(Attendance).where(
            Attendance.user_id == current_user.id,
            Attendance.attendance_date == date.today(),
        )
    )

    return attendance


@router.get("/history")
def history(
    month: int = Query(...),
    year: int = Query(...),
    page: int = 1,
    page_size: int = 31,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Attendance)
        .where(
            Attendance.user_id == current_user.id,
            extract("month", Attendance.attendance_date) == month,
            extract("year", Attendance.attendance_date) == year,
        )
        .order_by(Attendance.attendance_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return db.scalars(stmt).all()


@router.get("/summary")
def summary(
    month: int,
    year: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = Depends(get_current_user),
):
    rows = db.scalars(
        select(Attendance).where(
            Attendance.user_id == current_user.id,
            extract("month", Attendance.attendance_date) == month,
            extract("year", Attendance.attendance_date) == year,
        )
    ).all()

    return {
        "total_days": len(rows),
        "full_days": sum(1 for r in rows if r.status == "FULL_DAY"),
        "half_days": sum(1 for r in rows if r.status == "HALF_DAY"),
        "absent_days": sum(1 for r in rows if r.status == "ABSENT"),
        "working_minutes": sum(r.working_minutes for r in rows),
    }


@router.get("/report/staff")
def staff_report(
    staff_id: str,
    month: int,
    year: int,
    db: Annotated[Session, Depends(get_db)],
):
    stmt = (
        select(Attendance)
        .where(
            Attendance.user_id == staff_id,
            extract("month", Attendance.attendance_date) == month,
            extract("year", Attendance.attendance_date) == year,
        )
        .order_by(Attendance.attendance_date)
    )

    return db.scalars(stmt).all()


@router.get("/report/monthly")
def monthly_report(
    month: int,
    year: int,
    db: Annotated[Session, Depends(get_db)],
):
    stmt = (
        select(
            Attendance.user_id,
            func.count().label("days"),
            func.sum(Attendance.working_minutes).label("minutes"),
        )
        .where(
            extract("month", Attendance.attendance_date) == month,
            extract("year", Attendance.attendance_date) == year,
        )
        .group_by(Attendance.user_id)
    )

    return db.execute(stmt).all()
