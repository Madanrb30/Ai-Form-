import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.models.form import Form
from app.models.submission import Submission
from app.schemas.admin import (
    AdminStatsResponse,
    SystemHealthResponse,
    UserAdminResponse,
    UserListResponse,
    UserStatusUpdateRequest,
    UserRoleUpdateRequest,
    AuditLogResponse,
    AuditLogListResponse,
    SuperAdminBootstrapRequest,
    SuperAdminBootstrapResponse,
)
from app.api.deps import get_current_admin, get_current_super_admin
from app.services.audit_service import record_audit_log
from app.services.bootstrap_service import (
    provision_super_admin,
    BootstrapDisabledError,
    InvalidBootstrapSecretError,
    SuperAdminAlreadyExistsError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from app.core.config import settings
from app.core.logging import logger

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Retrieve real aggregate user and administrative activity statistics.
    Accessible to ADMIN and SUPER_ADMIN roles.
    Never exposes sensitive individual user records or passwords.
    """
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    suspended_users = db.query(User).filter(User.is_active == False).count()
    total_audit_logs = db.query(AuditLog).count()
    total_forms = db.query(Form).count()
    total_submissions = db.query(Submission).count()

    users_by_role = {
        "USER": db.query(User).filter(User.role == "USER").count(),
        "ADMIN": db.query(User).filter(User.role == "ADMIN").count(),
        "SUPER_ADMIN": db.query(User).filter(User.role == "SUPER_ADMIN").count(),
    }

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        suspended_users=suspended_users,
        total_audit_logs=total_audit_logs,
        users_by_role=users_by_role,
        total_forms=total_forms,
        total_submissions=total_submissions,
    )


@router.get("/users", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    role: Optional[str] = Query(None, description="Filter by role (USER, ADMIN, SUPER_ADMIN)"),
    status: Optional[str] = Query(None, description="Filter by status: 'active', 'suspended', or 'all'"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    List registered users with bounded pagination and search filters.
    Accessible to ADMIN and SUPER_ADMIN roles.
    Never exposes password hashes or tokens.
    """
    query = db.query(User)

    if role:
        role_clean = role.strip().upper()
        if role_clean != "ALL":
            query = query.filter(User.role == role_clean)

    if status:
        status_clean = status.strip().lower()
        if status_clean == "active":
            query = query.filter(User.is_active == True)
        elif status_clean == "suspended":
            query = query.filter(User.is_active == False)

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            (User.email.ilike(search_pattern)) | (User.full_name.ilike(search_pattern))
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / limit))
    offset = (page - 1) * limit

    items = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    return UserListResponse(
        items=[UserAdminResponse.model_validate(u) for u in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=UserAdminResponse)
def get_user_details(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Retrieve permitted details of a specific user.
    Accessible to ADMIN and SUPER_ADMIN roles.
    """
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} was not found."
        )

    return UserAdminResponse.model_validate(target_user)


@router.put("/users/{user_id}/status", response_model=UserAdminResponse)
def update_user_status(
    user_id: int,
    req: UserStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Suspend or reactivate a user account.
    - Admins cannot modify their own active status.
    - Regular ADMINs cannot suspend other ADMINs or SUPER_ADMINs.
    - Cannot suspend the final active SUPER_ADMIN.
    - Immediately invalidates existing sessions by incrementing token_version.
    - Records an audit log entry.
    """
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} was not found."
        )

    # Prevent modifying self
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot modify their own active status."
        )

    # Role hierarchy: ADMIN cannot suspend ADMIN or SUPER_ADMIN
    if current_user.role == "ADMIN" and target_user.role in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot modify the status of other administrators or super administrators."
        )

    # Protect the last active SUPER_ADMIN
    if target_user.role == "SUPER_ADMIN" and not req.is_active:
        active_super_admins = db.query(User).filter(
            User.role == "SUPER_ADMIN",
            User.is_active == True
        ).count()
        if active_super_admins <= 1:
            record_audit_log(
                db=db,
                action="USER_SUSPENSION_REJECTED",
                actor_id=current_user.id,
                actor_email=current_user.email,
                target_type="User",
                target_id=str(target_user.id),
                details={"reason": "Cannot suspend final active Super Administrator"},
                ip_address=request.client.host if request.client else None,
                status="FAILURE",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot suspend the final active Super Administrator."
            )

    old_status = target_user.is_active
    target_user.is_active = req.is_active

    # Invalidate existing active tokens
    target_user.token_version += 1
    db.commit()
    db.refresh(target_user)

    action_name = "USER_REACTIVATED" if req.is_active else "USER_SUSPENDED"
    record_audit_log(
        db=db,
        action=action_name,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="User",
        target_id=str(target_user.id),
        details={"old_status": old_status, "new_status": req.is_active, "reason": req.reason},
        ip_address=request.client.host if request.client else None,
        status="SUCCESS",
    )

    logger.info(f"{action_name}: User {target_user.id} ({target_user.email}) by Admin {current_user.id}")
    return UserAdminResponse.model_validate(target_user)


@router.put("/users/{user_id}/role", response_model=UserAdminResponse)
def update_user_role(
    user_id: int,
    req: UserRoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    """
    Change a user's authorization role.
    - Restricted exclusively to SUPER_ADMIN.
    - Prevents demoting or removing the final active SUPER_ADMIN.
    - Immediately invalidates existing tokens by incrementing token_version.
    - Records an immutable audit log entry.
    """
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} was not found."
        )

    # Protect the last active SUPER_ADMIN
    if target_user.role == "SUPER_ADMIN" and req.role != UserRole.SUPER_ADMIN:
        active_super_admins = db.query(User).filter(
            User.role == "SUPER_ADMIN",
            User.is_active == True
        ).count()
        if active_super_admins <= 1:
            record_audit_log(
                db=db,
                action="ROLE_CHANGE_REJECTED",
                actor_id=current_user.id,
                actor_email=current_user.email,
                target_type="User",
                target_id=str(target_user.id),
                details={"attempted_role": req.role.value, "reason": "Cannot demote final active Super Administrator"},
                ip_address=request.client.host if request.client else None,
                status="FAILURE",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the final active Super Administrator."
            )

    old_role = target_user.role
    target_user.role = req.role.value

    # Invalidate existing active tokens so old role claims are revoked
    target_user.token_version += 1
    db.commit()
    db.refresh(target_user)

    record_audit_log(
        db=db,
        action="ROLE_CHANGED",
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="User",
        target_id=str(target_user.id),
        details={"old_role": old_role, "new_role": req.role.value},
        ip_address=request.client.host if request.client else None,
        status="SUCCESS",
    )

    logger.info(f"ROLE_CHANGED: User {target_user.id} role changed from {old_role} to {req.role.value} by SuperAdmin {current_user.id}")
    return UserAdminResponse.model_validate(target_user)


@router.get("/system-health", response_model=SystemHealthResponse)
def get_system_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    """
    Approved operational system information for Super Administrators.
    Exposes no secrets, environment variables, or API keys.
    """
    from sqlalchemy import text
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    from app.services.ai_provider import ai_provider
    is_ai_active = ai_provider.is_groq_configured()
    ai_mode = "groq" if is_ai_active else "demo"

    return SystemHealthResponse(
        status="ok",
        project_name=settings.PROJECT_NAME,
        version="1.0.0",
        environment=settings.ENVIRONMENT,
        database_status=db_status,
        database_type="SQLite",
        ai_mode=ai_mode,
        ai_provider=settings.AI_PROVIDER,
        ai_model=settings.GROQ_MODEL if is_ai_active else "offline_demo_generator",
        transcription_model=settings.GROQ_TRANSCRIPTION_MODEL if is_ai_active else "offline_demo",
        max_audio_size_mb=int(settings.MAX_AUDIO_SIZE_BYTES / (1024 * 1024)),
        jwt_algorithm=settings.JWT_ALGORITHM,
        token_expiry_hours=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES / 60),
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, FAILURE)"),
    actor: Optional[str] = Query(None, description="Filter by actor email or ID"),
    target: Optional[str] = Query(None, description="Filter by target ID or type"),
    search: Optional[str] = Query(None, description="Search across action, details, actor_email"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Retrieve paginated audit logs.
    Accessible to ADMIN and SUPER_ADMIN roles.
    Audit records cannot be modified or deleted via API.
    """
    query = db.query(AuditLog)

    if action and action.strip().upper() != "ALL":
        query = query.filter(AuditLog.action == action.strip().upper())

    if status and status.strip().upper() != "ALL":
        query = query.filter(AuditLog.status == status.strip().upper())

    if actor and actor.strip():
        actor_term = f"%{actor.strip().lower()}%"
        query = query.filter(AuditLog.actor_email.ilike(actor_term))

    if target and target.strip():
        target_term = f"%{target.strip().lower()}%"
        query = query.filter(
            (AuditLog.target_id.ilike(target_term)) | (AuditLog.target_type.ilike(target_term))
        )

    if search and search.strip():
        search_pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            (AuditLog.action.ilike(search_pattern))
            | (AuditLog.actor_email.ilike(search_pattern))
            | (AuditLog.details.ilike(search_pattern))
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / limit))
    offset = (page - 1) * limit

    items = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.post("/bootstrap", response_model=SuperAdminBootstrapResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_initial_super_admin(
    req: SuperAdminBootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_bootstrap_key: Optional[str] = Header(None, alias="X-Bootstrap-Key"),
):
    """
    One-time administrative bootstrap endpoint for the initial Super Administrator.
    - Requires server-side BOOTSTRAP_SECRET_KEY via X-Bootstrap-Key header or bootstrap_key body field.
    - Disallowed if any active Super Administrator already exists.
    - Prohibits silent promotion or credential overwriting of existing accounts.
    - Transactionally provisions the account and logs an immutable audit event.
    """
    bootstrap_key = x_bootstrap_key or req.bootstrap_key
    client_ip = request.client.host if request.client else None

    try:
        new_super_admin = provision_super_admin(
            db=db,
            email=req.email,
            password=req.password,
            full_name=req.full_name,
            bootstrap_key=bootstrap_key,
            client_ip=client_ip,
            method="api",
        )
    except BootstrapDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except InvalidBootstrapSecretError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except SuperAdminAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except UserAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except (WeakPasswordError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return SuperAdminBootstrapResponse(
        message="Initial Super Administrator provisioned successfully. "
                "Please unset or remove BOOTSTRAP_SECRET_KEY from server environment.",
        user=UserAdminResponse.model_validate(new_super_admin),
    )
