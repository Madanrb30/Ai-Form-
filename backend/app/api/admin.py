import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.schemas.admin import (
    UserAdminResponse,
    UserListResponse,
    UserStatusUpdateRequest,
    UserRoleUpdateRequest,
    AuditLogResponse,
    AuditLogListResponse,
)
from app.api.deps import get_current_admin, get_current_super_admin
from app.services.audit_service import record_audit_log
from app.core.logging import logger

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/users", response_model=UserListResponse)
def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    role: Optional[str] = Query(None, description="Filter by role (USER, ADMIN, SUPER_ADMIN)"),
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
        query = query.filter(User.role == role_clean)

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


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Retrieve paginated audit logs.
    Accessible to ADMIN and SUPER_ADMIN roles.
    Audit records cannot be modified or deleted via API.
    """
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action.strip().upper())

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
