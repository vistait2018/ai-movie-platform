from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    email: EmailStr = Field(examples=["viewer@example.com"])
    display_name: str = Field(min_length=1, max_length=80, examples=["Movie Viewer"])
    password: SecretStr = Field(
        json_schema_extra={"minLength": 15, "maxLength": 128, "writeOnly": True},
        description="15–128 characters; Unicode and spaces are supported. Never returned.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def trim_email(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()

    @field_validator("display_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Display name must contain visible text without control characters")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 15 <= len(password) <= 128 or not password.strip():
            raise ValueError("Password must contain 15–128 characters and cannot be blank")
        return value


class RegistrationResponse(BaseModel):
    message: str = "Registration request received. Account activation requires email verification."


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr = Field(json_schema_extra={"writeOnly": True, "maxLength": 128})

    @field_validator("email", mode="before")
    @classmethod
    def canonical_email(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid password length")
        return value


class LoginResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: str = "bearer"
    expires_in: int


class CurrentUser(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    status: str
    roles: list[str]
