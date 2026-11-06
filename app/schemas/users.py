from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import RegistrationRequest


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def visible_name(cls, value: str) -> str:
        return RegistrationRequest.normalize_name(value)


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "active", "suspended", "deactivated"]
