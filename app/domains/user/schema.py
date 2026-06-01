from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SignupRequest(BaseModel):
    user_name: str = Field(max_length=255)
    password: str = Field(max_length=72)


class LoginRequest(BaseModel):
    user_name: str = Field(max_length=255)
    password: str = Field(max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    user_name: str
    created_at: datetime
