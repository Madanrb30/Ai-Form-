import pytest
import jwt
from datetime import timedelta
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.user import User


@pytest.fixture
def audit_test_users(db_session):
    u_user = User(
        email="audit_user@example.com",
        hashed_password=get_password_hash("AuditPass123!"),
        full_name="Audit Standard User",
        role="USER",
        avatar="AU",
        is_active=True,
        token_version=1,
    )
    u_admin = User(
        email="audit_admin@example.com",
        hashed_password=get_password_hash("AuditPass123!"),
        full_name="Audit Admin User",
        role="ADMIN",
        avatar="AA",
        is_active=True,
        token_version=1,
    )
    u_admin2 = User(
        email="audit_admin2@example.com",
        hashed_password=get_password_hash("AuditPass123!"),
        full_name="Audit Admin User 2",
        role="ADMIN",
        avatar="A2",
        is_active=True,
        token_version=1,
    )
    u_super = User(
        email="audit_super@example.com",
        hashed_password=get_password_hash("AuditPass123!"),
        full_name="Audit Super Admin",
        role="SUPER_ADMIN",
        avatar="AS",
        is_active=True,
        token_version=1,
    )
    db_session.add_all([u_user, u_admin, u_admin2, u_super])
    db_session.commit()
    for u in (u_user, u_admin, u_admin2, u_super):
        db_session.refresh(u)

    return {
        "user": u_user,
        "admin": u_admin,
        "admin2": u_admin2,
        "super_admin": u_super,
        "token_user": create_access_token(u_user.id, role=u_user.role, token_version=u_user.token_version),
        "token_admin": create_access_token(u_admin.id, role=u_admin.role, token_version=u_admin.token_version),
        "token_admin2": create_access_token(u_admin2.id, role=u_admin2.role, token_version=u_admin2.token_version),
        "token_super": create_access_token(u_super.id, role=u_super.role, token_version=u_super.token_version),
    }


def test_jwt_tampering_and_algorithm_none_rejected(client, audit_test_users):
    """1. Algorithm 'none' attack and invalid signature tampering must be rejected with 401."""
    # Attempt algorithm: none
    forged_none_token = jwt.encode(
        {"sub": str(audit_test_users["super_admin"].id), "role": "SUPER_ADMIN", "token_version": 1},
        key="",
        algorithm="none"
    )
    res_none = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {forged_none_token}"})
    assert res_none.status_code == 401

    # Attempt wrong secret key signature
    forged_secret_token = jwt.encode(
        {"sub": str(audit_test_users["super_admin"].id), "role": "SUPER_ADMIN", "token_version": 1},
        key="wrong-untrusted-secret-key-attacker",
        algorithm="HS256"
    )
    res_secret = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {forged_secret_token}"})
    assert res_secret.status_code == 401


def test_expired_jwt_rejected_on_all_admin_endpoints(client, audit_test_users):
    """2. Expired JWTs must be rejected across all administrative endpoints."""
    expired_token = create_access_token(
        audit_test_users["super_admin"].id,
        role="SUPER_ADMIN",
        token_version=audit_test_users["super_admin"].token_version,
        expires_delta=timedelta(seconds=-10)
    )

    headers = {"Authorization": f"Bearer {expired_token}"}
    assert client.get("/api/admin/stats", headers=headers).status_code == 401
    assert client.get("/api/admin/users", headers=headers).status_code == 401
    assert client.get("/api/admin/audit-logs", headers=headers).status_code == 401
    assert client.get("/api/admin/system-health", headers=headers).status_code == 401


def test_audit_logs_strictly_immutable(client, audit_test_users):
    """3. Audit logs cannot be modified or deleted via API (HTTP 405 Method Not Allowed)."""
    headers = {"Authorization": f"Bearer {audit_test_users['token_super']}"}

    # DELETE /api/admin/audit-logs -> 405
    res_delete = client.delete("/api/admin/audit-logs", headers=headers)
    assert res_delete.status_code == 405

    # PUT /api/admin/audit-logs -> 405
    res_put = client.put("/api/admin/audit-logs", json={}, headers=headers)
    assert res_put.status_code == 405

    # POST /api/admin/audit-logs -> 405
    res_post = client.post("/api/admin/audit-logs", json={}, headers=headers)
    assert res_post.status_code == 405


def test_suspended_admin_cannot_access_any_privileged_endpoint(client, audit_test_users, db_session):
    """4. Suspended admin tokens must be immediately revoked and blocked."""
    admin = audit_test_users["admin"]
    token_admin = audit_test_users["token_admin"]
    token_super = audit_test_users["token_super"]

    # Suspend the admin
    suspend_res = client.put(
        f"/api/admin/users/{admin.id}/status",
        json={"is_active": False, "reason": "Security investigation"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert suspend_res.status_code == 200

    # Suspended admin attempts to access stats -> 401/403
    res_stats = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_stats.status_code in (401, 403)

    # Reactivate to restore
    reactivate_res = client.put(
        f"/api/admin/users/{admin.id}/status",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert reactivate_res.status_code == 200


def test_admin_cannot_suspend_another_admin(client, audit_test_users):
    """5. An ADMIN cannot suspend another ADMIN (requires SUPER_ADMIN)."""
    token_admin = audit_test_users["token_admin"]
    admin2_id = audit_test_users["admin2"].id

    res = client.put(
        f"/api/admin/users/{admin2_id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res.status_code == 403
    assert "cannot modify the status of other administrators" in res.json()["detail"].lower()


def test_super_admin_cannot_demote_or_suspend_last_super_admin(client, audit_test_users):
    """6. The final active SUPER_ADMIN cannot demote or suspend themselves."""
    super_admin_id = audit_test_users["super_admin"].id
    token_super = audit_test_users["token_super"]

    # Attempt self-demotion
    demote_res = client.put(
        f"/api/admin/users/{super_admin_id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert demote_res.status_code == 400
    assert "cannot demote the final active super administrator" in demote_res.json()["detail"].lower()

    # Attempt self-suspension
    suspend_res = client.put(
        f"/api/admin/users/{super_admin_id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_super}"}
    )
    assert suspend_res.status_code == 400
