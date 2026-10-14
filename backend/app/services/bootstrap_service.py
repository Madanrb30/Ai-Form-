"""
Administrative Bootstrap Service
Provides safe, one-time provisioning of the initial SUPER_ADMIN account.
Enforces server-side secret verification, concurrency locking, and audit logging.
Prohibits repeat provisioning, silent user promotion, and unauthenticated access.
"""
import hmac
import re
import threading
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import logger
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.services.audit_service import record_audit_log

# Thread-level mutual exclusion lock for in-process concurrency safety
_bootstrap_lock = threading.Lock()


class BootstrapError(Exception):
    """Base exception for administrative bootstrap failures."""
    pass


class BootstrapDisabledError(BootstrapError):
    """Raised when bootstrap is not enabled or BOOTSTRAP_SECRET_KEY is unset."""
    pass


class InvalidBootstrapSecretError(BootstrapError):
    """Raised when the provided bootstrap secret key is invalid or missing."""
    pass


class SuperAdminAlreadyExistsError(BootstrapError):
    """Raised when an active Super Administrator already exists in the system."""
    pass


class UserAlreadyExistsError(BootstrapError):
    """Raised when the requested email belongs to an existing user."""
    pass


class WeakPasswordError(BootstrapError):
    """Raised when the requested administrator password is too short or weak."""
    pass


def has_active_super_admin(db: Session) -> bool:
    """
    Checks whether at least one active Super Administrator exists.
    Used to permanently lock the bootstrap mechanism once initialized.
    """
    active_count = db.query(User).filter(
        User.role == UserRole.SUPER_ADMIN.value,
        User.is_active == True
    ).count()
    return active_count > 0


def verify_bootstrap_secret(provided_key: Optional[str]) -> bool:
    """
    Verifies that BOOTSTRAP_SECRET_KEY is configured on the server
    and matches the provided key using constant-time comparison.
    """
    configured_secret = (settings.BOOTSTRAP_SECRET_KEY or "").strip()
    if not configured_secret:
        return False

    if not provided_key:
        return False

    return hmac.compare_digest(configured_secret, provided_key.strip())


def provision_super_admin(
    db: Session,
    email: str,
    password: str,
    full_name: Optional[str] = "Super Administrator",
    bootstrap_key: Optional[str] = None,
    client_ip: Optional[str] = None,
    method: str = "manual",
) -> User:
    """
    Transactionally provisions the initial SUPER_ADMIN account.
    
    Guarantees:
    1. Server secret validation (X-Bootstrap-Key or BOOTSTRAP_SECRET_KEY).
    2. Concurrency lock preventing race conditions.
    3. Re-checks for existing active SUPER_ADMIN before committing.
    4. Prohibits silent promotion or credential overwriting of existing users.
    5. Hashes password using application's Bcrypt implementation.
    6. Emits an immutable audit log entry.
    """
    configured_secret = (settings.BOOTSTRAP_SECRET_KEY or "").strip()
    if not configured_secret:
        raise BootstrapDisabledError(
            "Administrative bootstrap is disabled. BOOTSTRAP_SECRET_KEY is not configured on the server."
        )

    if not verify_bootstrap_secret(bootstrap_key):
        # Record failed authorization attempt
        record_audit_log(
            db=db,
            action="BOOTSTRAP_UNAUTHORIZED_ATTEMPT",
            actor_email=email,
            target_type="Role",
            target_id="SUPER_ADMIN",
            details={"reason": "Invalid or missing bootstrap secret key", "method": method},
            ip_address=client_ip,
            status="DENIED",
        )
        raise InvalidBootstrapSecretError("Invalid or missing administrative bootstrap secret key.")

    # Password validation
    if not password or len(password) < 8:
        raise WeakPasswordError("Administrator password must be at least 8 characters long.")
    if len(password) > 128:
        raise WeakPasswordError("Administrator password must not exceed 128 characters.")

    email_clean = (email or "").strip().lower()
    if not email_clean or "@" not in email_clean:
        raise ValueError("A valid email address is required for the Super Administrator.")

    # Concurrency-safe execution block
    with _bootstrap_lock:
        # SQLite immediate transaction lock if possible
        try:
            db.execute(text("BEGIN IMMEDIATE"))
        except Exception:
            pass  # Session may already have an active transaction

        # 1. Check if an active Super Admin already exists
        if has_active_super_admin(db):
            record_audit_log(
                db=db,
                action="BOOTSTRAP_REJECTED_ALREADY_EXISTS",
                actor_email=email_clean,
                target_type="Role",
                target_id="SUPER_ADMIN",
                details={"reason": "Active Super Administrator already exists", "method": method},
                ip_address=client_ip,
                status="FAILURE",
            )
            raise SuperAdminAlreadyExistsError(
                "A Super Administrator already exists. One-time administrative bootstrap is permanently disabled."
            )

        # 2. Check if a user with this email already exists (prevent silent promotion or password reset)
        existing_user = db.query(User).filter(User.email == email_clean).first()
        if existing_user:
            record_audit_log(
                db=db,
                action="BOOTSTRAP_REJECTED_EXISTING_USER",
                actor_email=email_clean,
                target_type="User",
                target_id=str(existing_user.id),
                details={"reason": "Email already registered; silent promotion prohibited", "method": method},
                ip_address=client_ip,
                status="FAILURE",
            )
            raise UserAlreadyExistsError(
                f"A user with email '{email_clean}' already exists. "
                "Administrative bootstrap cannot promote or reset existing accounts."
            )

        # 3. Create the Super Administrator
        name = (full_name or "Super Administrator").strip()
        words = name.split()
        initials = (words[0][0] + words[1][0]).upper() if len(words) > 1 else name[:2].upper()

        new_super_admin = User(
            email=email_clean,
            hashed_password=get_password_hash(password),
            full_name=name,
            role=UserRole.SUPER_ADMIN.value,
            title="System Owner",
            avatar=initials or "SA",
            is_active=True,
            token_version=1,
        )

        db.add(new_super_admin)
        db.commit()
        db.refresh(new_super_admin)

        # 4. Audit log
        record_audit_log(
            db=db,
            action="SUPER_ADMIN_BOOTSTRAPPED",
            actor_id=new_super_admin.id,
            actor_email=new_super_admin.email,
            target_type="User",
            target_id=str(new_super_admin.id),
            details={
                "provisioning_method": method,
                "role": UserRole.SUPER_ADMIN.value,
                "email": new_super_admin.email,
            },
            ip_address=client_ip,
            status="SUCCESS",
        )

        logger.info(
            f"SUPER_ADMIN_BOOTSTRAPPED: Initial Super Admin '{new_super_admin.email}' (ID {new_super_admin.id}) "
            f"successfully provisioned via {method}."
        )

        return new_super_admin
