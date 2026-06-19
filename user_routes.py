import uuid
from math import ceil
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import hash_password, require_permission
from database import get_db
from models import User
from schemas import (
    MessageResponse,
    PaginatedUsersResponse,
    UserCreate,
    UserResponse,
    UserRole,
    UserUpdate,
)


router = APIRouter(prefix="/users", tags=["users"])


def get_user_or_404(user_id: uuid.UUID, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def build_default_password(username: str, mobile_number: str | None) -> str:
    if not mobile_number or len(mobile_number) < 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mobile number must contain at least 4 characters to generate default password",
        )
    return f"{username[:4]}{mobile_number[:4]}"


def validate_unique_user_fields(
    db: Session,
    username: str | None = None,
    email: str | None = None,
    mobile_number: str | None = None,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    checks = [
        ("username", User.username, username),
        ("email", User.email, email),
        ("mobile_number", User.mobile_number, mobile_number),
    ]

    for field_name, column, value in checks:
        if value is None:
            continue

        query = db.query(User).filter(column == value)
        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)

        if query.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{field_name} already exists",
            )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("USER_CREATE"))],
)
def create_user(user_data: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
    validate_unique_user_fields(
        db=db,
        username=user_data.username,
        email=str(user_data.email) if user_data.email else None,
        mobile_number=user_data.mobile_number,
    )

    user = User(
        username=user_data.username,
        password_hash=hash_password(
            build_default_password(user_data.username, user_data.mobile_number)
        ),
        email=str(user_data.email) if user_data.email else None,
        mobile_number=user_data.mobile_number,
        role=user_data.role.value,
        is_active=user_data.is_active,
        created_by=user_data.created_by,
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username, email, or mobile number already exists",
        ) from exc

    db.refresh(user)
    return user


@router.get(
    "",
    response_model=PaginatedUsersResponse,
    dependencies=[Depends(require_permission("USER_VIEW"))],
)
def get_users(
    db: Annotated[Session, Depends(get_db)],
    roles: Annotated[
        list[str] | None,
        Query(description="Filter by roles. Use repeated params or comma-separated values."),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Search username, email, or mobile number."),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Filter active/inactive users. Omit to return all statuses."),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return."),
    ] = 10,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of records to skip."),
    ] = 0,
) -> PaginatedUsersResponse:
    query = db.query(User)

    if roles:
        role_values = []
        for role in roles:
            role_values.extend(item.strip().upper() for item in role.split(",") if item.strip())

        invalid_roles = sorted(set(role_values) - {item.value for item in UserRole})
        if invalid_roles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid roles: {', '.join(invalid_roles)}",
            )

        if role_values:
            query = query.filter(User.role.in_(role_values))

    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.username.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.mobile_number.ilike(search_pattern),
            )
        )

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total_count = query.count()
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    return PaginatedUsersResponse(
        data=users,
        total_count=total_count,
        total_pages=ceil(total_count / limit) if total_count else 0,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("USER_VIEW"))],
)
def get_user(user_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> User:
    return get_user_or_404(user_id, db)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_permission("USER_UPDATE"))],
)
def update_user(
    user_id: uuid.UUID,
    user_data: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = get_user_or_404(user_id, db)
    updates = user_data.model_dump(exclude_unset=True)

    validate_unique_user_fields(
        db=db,
        username=updates.get("username"),
        email=str(updates["email"]) if updates.get("email") else None,
        mobile_number=updates.get("mobile_number"),
        exclude_user_id=user_id,
    )

    for field, value in updates.items():
        if field == "email" and value is not None:
            value = str(value)
        if field == "role" and value is not None:
            value = value.value
        setattr(user, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username, email, or mobile number already exists",
        ) from exc

    db.refresh(user)
    return user


@router.post(
    "/{user_id}/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(require_permission("USER_UPDATE"))],
)
def reset_user_password(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    user = get_user_or_404(user_id, db)
    user.password_hash = hash_password(build_default_password(user.username, user.mobile_number))
    db.commit()
    return MessageResponse(message="Password reset to default password")


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("USER_DELETE"))],
)
def delete_user(user_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]) -> Response:
    user = get_user_or_404(user_id, db)
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
