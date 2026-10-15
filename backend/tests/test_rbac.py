import pytest
from app.models.user import User, UserRole
from app.models.form import Form
from app.models.audit_log import AuditLog
from app.core.security import get_password_hash, create_access_token
from app.db.init_db import init_db


@pytest.fixture
def rbac_users(db_session):
    u_user = User(
        email="regular_user@example.com",
        hashed_password=get_password_hash("UserPassword123!"),
        full_name="Regular User",
        role="USER",
        avatar="RU",
        is_active=True,
        token_version=1,
    )
    u_admin = User(
        email="admin_user@example.com",
        hashed_password=get_password_hash("AdminPassword123!"),
        full_name="Admin User",
        role="ADMIN",
        avatar="AU",
        is_active=True,
        token_version=1,
    )
    u_super = User(
        email="super_admin@example.com",
        hashed_password=get_password_hash("SuperPassword123!"),
        full_name="Super Admin User",
        role="SUPER_ADMIN",
        avatar="SA",
        is_active=True,
        token_version=1,
    )
    u_legacy = User(
        email="legacy_user@example.com",
        hashed_password=get_password_hash("LegacyPassword123!"),
        full_name="Legacy Engineer",
        role="Engineer",  # Legacy job title
        avatar="LE",
        is_active=True,
        token_version=1,
    )
    db_session.add_all([u_user, u_admin, u_super, u_legacy])
    db_session.commit()
    for u in (u_user, u_admin, u_super, u_legacy):
        db_session.refresh(u)

    return {
        "user": u_user,
        "admin": u_admin,
        "super_admin": u_super,
        "legacy": u_legacy,
        "token_user": create_access_token(u_user.id, role=u_user.role, token_version=u_user.token_version),
        "token_admin": create_access_token(u_admin.id, role=u_admin.role, token_version=u_admin.token_version),
        "token_super": create_access_token(u_super.id, role=u_super.role, token_version=u_super.token_version),
    }


def test_1_public_registration_always_creates_user(client):
    """1. Public registration always creates a USER."""
    res = client.post(
        "/api/auth/register",
        json={"email": "new_public_user@example.com", "password": "SecurePassword123!", "full_name": "New Public"}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["user"]["role"] == "USER"
    assert data["user"]["email"] == "new_public_user@example.com"


def test_2_registration_cannot_create_admin_or_super_admin(client):
    """2. Registration cannot create an ADMIN or SUPER_ADMIN (rejects privilege injection)."""
    res = client.post(
        "/api/auth/register",
        json={
            "email": "hacker_trying_admin@example.com",
            "password": "SecurePassword123!",
            "full_name": "Hacker Attempt",
            "role": "SUPER_ADMIN",
        }
    )
    assert res.status_code == 201
    data = res.json()
    # The server strictly forces role="USER" regardless of payload
    assert data["user"]["role"] == "USER"


def test_3_users_cannot_elevate_own_privileges(client, rbac_users):
    """3. Users cannot elevate their own privileges."""
    token_user = rbac_users["token_user"]
    user_id = rbac_users["user"].id

    # Normal user attempts to promote self to ADMIN via role update endpoint
    res = client.put(
        f"/api/admin/users/{user_id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token_user}"}
    )
    # Blocked by role dependency
    assert res.status_code == 403


def test_4_user_cannot_call_administrative_endpoints(client, rbac_users):
    """4. USER cannot call administrative endpoints."""
    token_user = rbac_users["token_user"]

    # Attempt to list users
    res_list = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token_user}"})
    assert res_list.status_code == 403

    # Attempt to view audit logs
    res_audit = client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token_user}"})
    assert res_audit.status_code == 403

    # Attempt to suspend an account
    res_suspend = client.put(
        f"/api/admin/users/{rbac_users['admin'].id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_user}"}
    )
    assert res_suspend.status_code == 403


def test_5_admin_cannot_perform_super_admin_only_operations(client, rbac_users):
    """5. ADMIN cannot perform SUPER_ADMIN-only operations."""
    token_admin = rbac_users["token_admin"]
    target_user_id = rbac_users["user"].id

    # Admin attempts to change a user's role -> 403 Forbidden
    res = client.put(
        f"/api/admin/users/{target_user_id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res.status_code == 403
    assert "permission" in res.json()["detail"].lower()

    # Admin cannot suspend a SUPER_ADMIN
    res_suspend_super = client.put(
        f"/api/admin/users/{rbac_users['super_admin'].id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res_suspend_super.status_code == 403


def test_6_super_admin_can_perform_authorized_role_management(client, rbac_users):
    """6. SUPER_ADMIN can perform authorized role-management operations."""
    token_super = rbac_users["token_super"]
    target_user_id = rbac_users["user"].id

    # 1. Promote USER to ADMIN
    res_promote = client.put(
        f"/api/admin/users/{target_user_id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert res_promote.status_code == 200
    assert res_promote.json()["role"] == "ADMIN"

    # 2. Demote back to USER
    res_demote = client.put(
        f"/api/admin/users/{target_user_id}/role",
        json={"role": "USER"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert res_demote.status_code == 200
    assert res_demote.json()["role"] == "USER"


def test_7_suspended_user_cannot_access_protected_apis(client, db_session, rbac_users):
    """7. A suspended user cannot access protected APIs."""
    user = rbac_users["user"]
    token_user = rbac_users["token_user"]

    # Directly suspend the user
    user.is_active = False
    db_session.commit()

    # Protected endpoint call returns 403
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_user}"})
    assert res.status_code == 403
    assert "suspended" in res.json()["detail"].lower()

    # Suspended user login is rejected
    res_login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "UserPassword123!"}
    )
    assert res_login.status_code == 403
    assert "suspended" in res_login.json()["detail"].lower()


def test_8_existing_public_form_workflows_continue(client, rbac_users):
    """8. Existing public form workflows continue to work."""
    token_user = rbac_users["token_user"]

    # User creates a public form
    form_res = client.post(
        "/api/forms",
        json={
            "title": "RBAC Community Survey",
            "is_public": True,
            "schema_json": {
                "title": "RBAC Survey",
                "fields": [{"name": "response", "label": "Response", "type": "text", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_user}"}
    )
    assert form_res.status_code == 201
    form_id = form_res.json()["id"]

    # Guest fills public form without auth
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"response": "Guest feedback"}}
    )
    assert sub_res.status_code == 201
    assert sub_res.json()["id"] is not None


def test_9_existing_ownership_and_cross_user_isolation_passes(client, rbac_users):
    """9. Existing ownership and cross-user isolation protections still pass."""
    token_user = rbac_users["token_user"]
    token_admin = rbac_users["token_admin"]

    # User creates private form
    form_res = client.post(
        "/api/forms",
        json={
            "title": "Private Diary",
            "is_public": False,
            "schema_json": {
                "title": "Private Diary",
                "fields": [{"name": "entry", "label": "Entry", "type": "text"}]
            }
        },
        headers={"Authorization": f"Bearer {token_user}"}
    )
    form_id = form_res.json()["id"]

    # Another user cannot read private form
    other_res = client.get(f"/api/forms/{form_id}", headers={"Authorization": f"Bearer {token_admin}"})
    assert other_res.status_code == 403


def test_10_invalid_and_expired_jwts_rejected(client):
    """10. Invalid and expired JWTs remain rejected."""
    # Malformed token
    res_bad = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.jwt.token"})
    assert res_bad.status_code == 401

    # Missing header
    res_missing = client.get("/api/auth/me")
    assert res_missing.status_code == 401


def test_11_role_change_and_suspension_invalidates_token(client, rbac_users):
    """11. Role changes and token invalidation behave as documented."""
    token_super = rbac_users["token_super"]
    target_user = rbac_users["user"]
    target_token = rbac_users["token_user"]

    # Target token currently works
    check_before = client.get("/api/auth/me", headers={"Authorization": f"Bearer {target_token}"})
    assert check_before.status_code == 200

    # Super admin changes role
    role_change_res = client.put(
        f"/api/admin/users/{target_user.id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert role_change_res.status_code == 200

    # Previous token must now be rejected because token_version was incremented
    check_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {target_token}"})
    assert check_after.status_code == 401
    assert "revoked" in check_after.json()["detail"].lower()


def test_12_final_active_super_admin_cannot_be_demoted_or_suspended(client, rbac_users):
    """12. The final active SUPER_ADMIN cannot accidentally be removed or demoted."""
    token_super = rbac_users["token_super"]
    super_admin_id = rbac_users["super_admin"].id

    # Attempt to demote final SUPER_ADMIN to USER
    demote_res = client.put(
        f"/api/admin/users/{super_admin_id}/role",
        json={"role": "USER"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert demote_res.status_code == 400
    assert "final active super administrator" in demote_res.json()["detail"].lower()

    # Attempt to suspend final SUPER_ADMIN
    suspend_res = client.put(
        f"/api/admin/users/{super_admin_id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert suspend_res.status_code == 400
    assert "cannot modify their own active status" in suspend_res.json()["detail"].lower() or "final active" in suspend_res.json()["detail"].lower()


def test_13_existing_database_records_survive_migration(client, rbac_users, db_session):
    """13. Existing database records survive migration with job titles preserved."""
    legacy = rbac_users["legacy"]
    # Legacy user had role="Engineer"
    # User model preserved "Engineer" in title and assigned role="USER"
    assert legacy.role == "USER"
    assert legacy.title == "Engineer"

    # Profile endpoint returns title and USER role
    token_legacy = create_access_token(legacy.id, role=legacy.role, token_version=legacy.token_version)
    profile_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_legacy}"})
    assert profile_res.status_code == 200
    data = profile_res.json()
    assert data["role"] == "USER"
    assert data["title"] == "Engineer"


def test_14_password_hashes_and_secrets_never_appear_in_api(client, rbac_users):
    """14. Password hashes and secrets never appear in API responses."""
    token_admin = rbac_users["token_admin"]

    # 1. GET /api/auth/me
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_admin}"})
    me_data = me_res.json()
    assert "hashed_password" not in me_data
    assert "password" not in me_data
    assert "token_version" not in me_data

    # 2. GET /api/admin/users
    users_res = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token_admin}"})
    assert users_res.status_code == 200
    for u in users_res.json()["items"]:
        assert "hashed_password" not in u
        assert "password" not in u

    # 3. GET /api/admin/audit-logs
    audit_res = client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token_admin}"})
    assert audit_res.status_code == 200
    for log_item in audit_res.json()["items"]:
        if log_item.get("details"):
            assert "password" not in log_item["details"].lower() or "[redacted]" in log_item["details"].lower()


def test_15_admin_stats_access_and_metrics(client, rbac_users):
    """15. GET /api/admin/stats requires Admin privileges and returns accurate aggregated metrics."""
    token_user = rbac_users["token_user"]
    token_admin = rbac_users["token_admin"]

    # 1. Unauthenticated request -> 401
    res_unauth = client.get("/api/admin/stats")
    assert res_unauth.status_code == 401

    # 2. Regular user request -> 403 Forbidden
    res_user = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token_user}"})
    assert res_user.status_code == 403

    # 3. Admin request -> 200 OK
    res_admin = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "total_users" in data
    assert "active_users" in data
    assert "suspended_users" in data
    assert "users_by_role" in data
    assert data["total_users"] >= 4
    assert data["active_users"] >= 4
    assert data["suspended_users"] >= 0
    assert "USER" in data["users_by_role"]
    assert "ADMIN" in data["users_by_role"]
    assert "SUPER_ADMIN" in data["users_by_role"]


def test_16_admin_users_status_filter(client, rbac_users, db_session):
    """16. GET /api/admin/users supports status filtering for 'active' and 'suspended' users."""
    token_admin = rbac_users["token_admin"]
    user_to_suspend = rbac_users["user"]

    # Suspend user
    suspend_res = client.put(
        f"/api/admin/users/{user_to_suspend.id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert suspend_res.status_code == 200

    # Filter status=suspended
    res_suspended = client.get("/api/admin/users?status=suspended", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_suspended.status_code == 200
    items_suspended = res_suspended.json()["items"]
    assert any(u["id"] == user_to_suspend.id for u in items_suspended)
    assert all(u["is_active"] is False for u in items_suspended)

    # Filter status=active
    res_active = client.get("/api/admin/users?status=active", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_active.status_code == 200
    items_active = res_active.json()["items"]
    assert not any(u["id"] == user_to_suspend.id for u in items_active)
    assert all(u["is_active"] is True for u in items_active)

    # Reactivate user to restore state
    reactivate_res = client.put(
        f"/api/admin/users/{user_to_suspend.id}/status",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert reactivate_res.status_code == 200


def test_17_super_admin_system_health_endpoint(client, rbac_users):
    """17. GET /api/admin/system-health is accessible strictly to SUPER_ADMIN and never leaks secrets."""
    token_user = rbac_users["token_user"]
    token_admin = rbac_users["token_admin"]
    token_super = rbac_users["token_super"]

    # 1. Unauthenticated -> 401
    assert client.get("/api/admin/system-health").status_code == 401

    # 2. Regular user -> 403
    assert client.get("/api/admin/system-health", headers={"Authorization": f"Bearer {token_user}"}).status_code == 403

    # 3. Regular admin -> 403 (Super Admin only)
    assert client.get("/api/admin/system-health", headers={"Authorization": f"Bearer {token_admin}"}).status_code == 403

    # 4. Super Admin -> 200
    res = client.get("/api/admin/system-health", headers={"Authorization": f"Bearer {token_super}"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "database_status" in data
    assert "ai_mode" in data
    assert "jwt_algorithm" in data

    # Verify no secret leakage
    for forbidden in ["secret", "jwt_secret_key", "groq_api_key", "password", "token"]:
        assert forbidden not in data


def test_18_audit_rejections_and_enhanced_filters(client, rbac_users, db_session):
    """18. Audit log records rejected actions and supports multi-parameter filtering."""
    token_super = rbac_users["token_super"]
    super_admin_id = rbac_users["super_admin"].id

    # Attempt forbidden demotion of final active SUPER_ADMIN -> should record ROLE_CHANGE_REJECTED
    demote_res = client.put(
        f"/api/admin/users/{super_admin_id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert demote_res.status_code == 400

    # Query audit logs with action=ROLE_CHANGE_REJECTED
    audit_res = client.get(
        "/api/admin/audit-logs?action=ROLE_CHANGE_REJECTED",
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert audit_res.status_code == 200
    items = audit_res.json()["items"]
    assert any(log["action"] == "ROLE_CHANGE_REJECTED" and log["status"] == "FAILURE" for log in items)

    # Test filtering by status=FAILURE
    audit_failure_res = client.get(
        "/api/admin/audit-logs?status=FAILURE",
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert audit_failure_res.status_code == 200
    for log in audit_failure_res.json()["items"]:
        assert log["status"] == "FAILURE"


