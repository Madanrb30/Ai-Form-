import time
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Any
import bcrypt
import jwt
from app.core.config import settings

# In-memory thread-safe sliding-window rate limiter for authentication endpoints.
# NOTE: For horizontal multi-worker/multi-server production deployments,
# this in-memory cache should be replaced with a distributed Redis or Memcached store.
_LOGIN_ATTEMPTS = defaultdict(list)
_RATE_LIMIT_LOCK = threading.Lock()
MAX_LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def check_login_rate_limit(key: str) -> bool:
    """Returns True if under rate limit, False if exceeded (thread-safe)."""
    now = time.time()
    with _RATE_LIMIT_LOCK:
        attempts = _LOGIN_ATTEMPTS[key]
        _LOGIN_ATTEMPTS[key] = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        return len(_LOGIN_ATTEMPTS[key]) < MAX_LOGIN_ATTEMPTS


def record_login_attempt(key: str):
    """Records a failed login attempt (thread-safe)."""
    with _RATE_LIMIT_LOCK:
        _LOGIN_ATTEMPTS[key].append(time.time())


def clear_login_attempts(key: str):
    """Clears failed login attempts upon successful authentication (thread-safe)."""
    with _RATE_LIMIT_LOCK:
        _LOGIN_ATTEMPTS.pop(key, None)


def get_password_hash(password: str) -> str:
    # Cap input length at 128 characters to mitigate bcrypt CPU DoS
    safe_password = password[:128]
    pwd_bytes = safe_password.encode("utf-8")[:72]  # bcrypt 72-byte max
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        safe_password = plain_password[:128]
        return bcrypt.checkpw(
            safe_password.encode("utf-8")[:72],
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": datetime.utcnow()
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decodes and validates a JWT access token.
    Raises jwt.ExpiredSignatureError, jwt.InvalidTokenError, or jwt.PyJWTError
    if the token is invalid or expired.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
