from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Reauthentication(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    password: SecretStr = Field(min_length=1, max_length=1024)


class MFAProof(Reauthentication):
    code: SecretStr = Field(min_length=6, max_length=128)


class EnrollmentIssued(BaseModel):
    # Returned exactly once; repr and logs must not disclose credentials.
    secret: str = Field(repr=False)
    provisioning_uri: str = Field(repr=False)


class RecoveryIssued(BaseModel):
    recovery_codes: list[str] = Field(repr=False)
