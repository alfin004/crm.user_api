import uuid
from enum import StrEnum
import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


MOBILE_NUMBER_PATTERN = re.compile(r"^\+?[1-9]\d{9,14}$")
SPECIAL_CHARACTER_PATTERN = re.compile(r"[^A-Za-z0-9]")
LETTER_PATTERN = re.compile(r"[A-Za-z]")
FULL_DAY = "FULL_DAY"
HALF_DAY = "HALF_DAY"
ABSENT = "ABSENT"

class UserRole(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    USER = "USER"


class UserBase(BaseModel):
    username: str = Field(min_length=8, max_length=100)
    email: EmailStr | None = None
    mobile_number: str | None = Field(default=None, max_length=30)
    role: UserRole = UserRole.USER
    is_active: bool = True

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not MOBILE_NUMBER_PATTERN.fullmatch(value):
            raise ValueError("Mobile number must be 10 to 15 digits and may start with +")
        return value


class UserCreate(UserBase):
    mobile_number: str = Field(min_length=4, max_length=30)
    created_by: uuid.UUID | None = None


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=8, max_length=100)
    email: EmailStr | None = None
    mobile_number: str | None = Field(default=None, max_length=30)
    role: UserRole | None = None
    is_active: bool | None = None
    current_login_status: bool | None = None
    updated_by: uuid.UUID | None = None

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not MOBILE_NUMBER_PATTERN.fullmatch(value):
            raise ValueError("Mobile number must be 10 to 15 digits and may start with +")
        return value


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr | None
    mobile_number: str | None
    role: UserRole
    is_active: bool
    current_login_status: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)


class UserWithPermissions(UserResponse):
    permissions: list[str]


class PaginatedUsersResponse(BaseModel):
    data: list[UserResponse]
    total_count: int
    total_pages: int
    limit: int
    offset: int


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not LETTER_PATTERN.search(value):
            raise ValueError("Password must contain at least one letter")
        if not SPECIAL_CHARACTER_PATTERN.search(value):
            raise ValueError("Password must contain at least one special character")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    message: str


# Attendance Section
class PunchResponse(BaseModel):
    message: str
    attendance_date: date
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    status: Optional[str] = None

class AttendanceHistory(BaseModel):

    attendance_date: date

    punch_in: Optional[datetime]

    punch_out: Optional[datetime]

    working_minutes: int

    status: str

    remarks: Optional[str]

class AttendanceSummary(BaseModel):

    total_days: int

    full_days: int

    half_days: int

    absent_days: int

    total_working_minutes: int

class StaffAttendanceItem(BaseModel):

    attendance_date: date

    punch_in: Optional[datetime]

    punch_out: Optional[datetime]

    working_minutes: int

    status: str

    remarks: Optional[str]

    class Config:
        from_attributes = True

class StaffAttendanceReport(BaseModel):

    staff_id: int

    month: int

    year: int

    total_days: int

    full_days: int

    half_days: int

    absent_days: int

    working_minutes: int

    records: list[StaffAttendanceItem]
    
class MonthlySummaryItem(BaseModel):

    staff_id: int

    staff_name: str

    full_days: int

    half_days: int

    absent_days: int

    total_minutes: int

class MonthlySummaryResponse(BaseModel):

    month: int

    year: int

    total_staffs: int

    data: list[MonthlySummaryItem]                    
