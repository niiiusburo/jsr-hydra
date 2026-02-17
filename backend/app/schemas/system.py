"""
System-level Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of system health, versioning,
event logging, and authentication.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class HealthCheck(BaseModel):
    """
    System health check response.

    Attributes:
        status: Overall system status (healthy/degraded/unhealthy)
        services: Dictionary mapping service names to their statuses
        version: Current system version
        uptime_seconds: System uptime in seconds
    """

    model_config = ConfigDict(from_attributes=True)

    status: str
    services: dict[str, str]
    version: str
    uptime_seconds: float

    @field_validator('uptime_seconds')
    @classmethod
    def validate_uptime(cls, v: float) -> float:
        """Validate uptime is non-negative."""
        if v < 0:
            raise ValueError('uptime_seconds must be non-negative')
        return v


class VersionInfo(BaseModel):
    """
    System version information.

    Attributes:
        version: Semantic version string
        codename: Release codename
        updated_at: Last update timestamp
    """

    model_config = ConfigDict(from_attributes=True)

    version: str
    codename: str
    updated_at: str


class EventLogResponse(BaseModel):
    """
    System event log entry.

    Attributes:
        id: Unique event identifier
        event_type: Type of event
        severity: Event severity level (info/warning/error/critical)
        source_module: Optional module that generated the event
        payload: Event data dictionary
        created_at: Event timestamp
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    severity: str
    source_module: Optional[str] = None
    payload: dict
    created_at: datetime

    @field_validator('severity')
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """Validate severity is a known level."""
        valid_levels = {'info', 'warning', 'error', 'critical'}
        if v.lower() not in valid_levels:
            raise ValueError(
                f'severity must be one of {valid_levels}, got {v}'
            )
        return v.lower()


class LoginRequest(BaseModel):
    """
    User login request schema.

    Attributes:
        username: Username
        password: Password
    """

    model_config = ConfigDict(from_attributes=True)

    username: str
    password: str

    @field_validator('username', 'password')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Validate fields are not empty."""
        if not v or not v.strip():
            raise ValueError('field cannot be empty')
        return v.strip()


class TokenResponse(BaseModel):
    """
    JWT token response schema.

    Attributes:
        access_token: JWT access token
        token_type: Token type (default: 'bearer')
    """

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"

    @field_validator('access_token')
    @classmethod
    def validate_token_not_empty(cls, v: str) -> str:
        """Validate token is not empty."""
        if not v or not v.strip():
            raise ValueError('access_token cannot be empty')
        return v.strip()
