from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User


ALGORITHM = "HS256"
ROLE_PERMISSIONS = {
    "ADMIN": ["USER_CREATE", "USER_UPDATE", "USER_DELETE", "USER_VIEW"],
    "MANAGER": [],
    "USER": [],
}

bearer_scheme = HTTPBearer(auto_error=True)


def normalize_bcrypt_password(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(normalize_bcrypt_password(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(normalize_bcrypt_password(plain_password), password_hash.encode("utf-8"))


def create_access_token(subject: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expires_at = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise credentials_exception
        return subject
    except JWTError as exc:
        raise credentials_exception from exc


def get_permissions(role: str) -> list[str]:
    return ROLE_PERMISSIONS.get(role, [])


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user_id = decode_access_token(credentials.credentials)
    try:
        parsed_user_id = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, parsed_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def require_permission(permission: str) -> Callable[[User], User]:
    def dependency(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if permission not in get_permissions(current_user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied",
            )
        return current_user

    return dependency
