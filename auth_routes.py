from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from auth import create_access_token, decode_access_token, get_permissions, hash_password, verify_password
from cache import cache
from config import settings
from database import get_db
from models import User
from schemas import (
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    TokenResponse,
    UserResponse,
    UserWithPermissions,
)


router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=True)


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.query(User).filter(User.username == credentials.username).one_or_none()
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    user.last_login_at = datetime.now(timezone.utc)
    user.current_login_status = True
    db.commit()

    token, expires_in = create_access_token(str(user.id))
    cache.delete(token)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout", response_model=MessageResponse)
def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    token = credentials.credentials
    user_id = decode_access_token(token)
    try:
        parsed_user_id = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, parsed_user_id)
    if user is not None:
        user.current_login_status = False
        db.commit()

    cache.delete(token)
    return MessageResponse(message="Logged out successfully")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    password_data: PasswordResetRequest,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    token = credentials.credentials
    user_id = decode_access_token(token)
    try:
        parsed_user_id = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, parsed_user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.password_hash = hash_password(password_data.new_password)
    db.commit()
    cache.delete(token)
    return MessageResponse(message="Password updated successfully")


@router.get("/me", response_model=UserWithPermissions)
def me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> UserWithPermissions:
    token = credentials.credentials
    user_id = decode_access_token(token)
    try:
        parsed_user_id = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    cached_user = cache.get(token)
    if cached_user is not None:
        return UserWithPermissions.model_validate(cached_user)

    user = db.get(User, parsed_user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_payload = UserResponse.model_validate(user).model_dump()
    user_response = UserWithPermissions(
        **user_payload,
        permissions=get_permissions(user.role),
    )
    cache.set(token, user_response.model_dump(mode="json"), settings.user_cache_ttl)
    return user_response
