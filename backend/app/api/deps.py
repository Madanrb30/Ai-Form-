from typing import Optional
from fastapi import Depends, HTTPException, status, Header, Query
from sqlalchemy.orm import Session
import jwt

from app.db.session import get_db
from app.models.user import User
from app.core.security import decode_access_token


def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Extracts current authenticated user from Bearer JWT token in Authorization header
    or fallback 'token' query parameter (used for browser downloads).
    
    If no authorization credentials are provided, returns None for guest workflows.
    If credentials ARE provided but invalid, expired, or malformed, raises HTTP 401
    to prevent silent degradation to anonymous access.
    """
    raw_token = None

    if authorization:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected 'Bearer <token>'."
            )
        raw_token = parts[1]
    elif token:
        raw_token = token.strip()

    if not raw_token:
        return None

    try:
        payload = decode_access_token(raw_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token could not be verified."
        )

    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authentication token."
        )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier encoded in token."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with this token was not found."
        )

    # Check account suspension
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact an administrator."
        )

    # Check token version revocation (e.g. after suspension or role change)
    token_version = payload.get("token_version")
    if token_version is not None and token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked. Please log in again."
        )

    return user


def get_current_user_required(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Enforces authentication; raises 401 if token is missing or invalid."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials are required to access this resource."
        )
    return user


def require_roles(*allowed_roles: str):
    """
    Reusable authorization dependency factory.
    Verifies that the authenticated user possesses one of the allowed roles.
    Raises 401 if unauthenticated, 403 if authenticated but lacking permitted role.
    Records audit attempt on unauthorized access.
    """
    def role_checker(
        current_user: User = Depends(get_current_user_required),
        db: Session = Depends(get_db)
    ) -> User:
        if current_user.role not in allowed_roles:
            try:
                from app.services.audit_service import record_audit_log
                record_audit_log(
                    db=db,
                    action="UNAUTHORIZED_ROLE_ACCESS_DENIED",
                    actor_id=current_user.id,
                    actor_email=current_user.email,
                    target_type="Role",
                    target_id=str(allowed_roles),
                    details={"user_role": current_user.role, "required_roles": list(allowed_roles)},
                    status="DENIED"
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource."
            )
        return current_user
    return role_checker


get_current_admin = require_roles("ADMIN", "SUPER_ADMIN")
get_current_super_admin = require_roles("SUPER_ADMIN")

