"""
PURPOSE: Authentication module for JWT token creation, verification, and FastAPI dependencies.

Handles login validation, JWT token generation/verification using python-jose with HS256,
API key authentication, and FastAPI dependency injection for route protection.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config.settings import settings
from app.schemas import LoginRequest, TokenResponse
from app.utils.logger import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ════════════════════════════════════════════════════════════════
# JWT Token Management
# ════════════════════════════════════════════════════════════════


class TokenPayload(BaseModel):
    """
    PURPOSE: JWT token payload structure for access token claims.

    Attributes:
        sub: Subject (username) of the token
        exp: Expiration timestamp
        iat: Issued at timestamp
    """

    sub: str
    exp: int
    iat: int


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    PURPOSE: Create a JWT access token with optional custom expiration time.

    CALLED BY: login endpoint, refresh token handlers

    Args:
        data: Token payload data (must include 'sub' for username)
        expires_delta: Optional custom expiration delta. Defaults to 24 hours.

    Returns:
        str: Encoded JWT token

    Raises:
        ValueError: If 'sub' is not in data dictionary
    """
    if "sub" not in data:
        raise ValueError("Token data must include 'sub' (subject/username)")

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    try:
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET,
            algorithm="HS256"
        )
        logger.info(
            "token_created",
            subject=data.get("sub"),
            expires_in_hours=24 if not expires_delta else expires_delta.total_seconds() / 3600
        )
        return encoded_jwt
    except Exception as e:
        logger.error("token_creation_failed", error=str(e))
        raise


def verify_token(token: str) -> dict:
    """
    PURPOSE: Decode and verify JWT token validity using HS256 algorithm.

    CALLED BY: get_current_user dependency, token refresh handlers

    Args:
        token: JWT token string to verify

    Returns:
        dict: Decoded token payload with claims

    Raises:
        HTTPException: If token is invalid, expired, or verification fails
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials (missing subject)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError as e:
        logger.warning("token_verification_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error("token_verification_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ════════════════════════════════════════════════════════════════
# FastAPI Dependencies
# ════════════════════════════════════════════════════════════════


async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """
    PURPOSE: FastAPI dependency to extract and verify current user from Bearer token.

    CALLED BY: All protected route handlers via Depends(get_current_user)

    Args:
        authorization: Authorization header value in format "Bearer <token>"

    Returns:
        str: Authenticated username

    Raises:
        HTTPException: If authorization header is missing, malformed, or token is invalid
    """
    if not authorization:
        logger.warning("missing_authorization_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        logger.warning("malformed_authorization_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)
    username = payload.get("sub")

    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return username


async def api_key_auth(x_api_key: Optional[str] = Header(None)) -> str:
    """
    PURPOSE: FastAPI dependency to validate API key from X-API-Key header.

    CALLED BY: API-key-authenticated routes via Depends(api_key_auth)

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        str: "api-key" if validation succeeds

    Raises:
        HTTPException: If X-API-Key header is missing or invalid
    """
    if not x_api_key:
        logger.warning("missing_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    if x_api_key != settings.API_KEY:
        logger.warning("invalid_api_key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return "api-key"


# ════════════════════════════════════════════════════════════════
# Login Endpoint
# ════════════════════════════════════════════════════════════════


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest) -> TokenResponse:
    """
    PURPOSE: Authenticate user with username/password and return JWT access token.

    CALLED BY: Frontend login form, external authentication requests

    Args:
        credentials: LoginRequest with username and password

    Returns:
        TokenResponse: JWT access token and token type

    Raises:
        HTTPException: If credentials do not match configured admin credentials
    """
    if (credentials.username == settings.ADMIN_USERNAME and
        credentials.password == settings.ADMIN_PASSWORD):

        token = create_access_token({"sub": credentials.username})
        logger.info("user_login_successful", username=credentials.username)
        return TokenResponse(access_token=token, token_type="bearer")

    logger.warning(
        "login_failed_invalid_credentials",
        username=credentials.username
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
