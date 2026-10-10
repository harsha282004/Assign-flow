import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    role: Literal["FACULTY", "STUDENT"]
    login_id: str = Field(min_length=1, max_length=32)
    # SecretStr keeps the password out of reprs/logs; the length cap bounds Argon2 work per request.
    password: SecretStr = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    login_id: str
    full_name: str
    role: Literal["FACULTY", "STUDENT"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut


class SectionOut(BaseModel):
    id: uuid.UUID
    label: str
    semester: int
    name: str


class SubjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class StudentSubjectOut(SubjectOut):
    faculty_name: str | None


class TeachingOut(BaseModel):
    subject: SubjectOut
    section: SectionOut


class MeResponse(UserOut):
    """Student: section + subjects. Faculty: teaching mappings. The other group is null."""

    section: SectionOut | None = None
    subjects: list[StudentSubjectOut] | None = None
    teaching: list[TeachingOut] | None = None
