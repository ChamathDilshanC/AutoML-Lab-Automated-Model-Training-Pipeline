from typing import Literal

from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds


class GoogleTokenRequest(BaseModel):
    access_token: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: str | None = None
