"""
Automated Test Suite for Super Admin Provisioning & Administrative Bootstrap.
Verifies:
1. Successful initial provisioning via service and API.
2. Rejection of repeat bootstrap attempts once a Super Admin exists.
3. Rejection of invalid, missing, or empty bootstrap secret keys.
4. Prevention of silent user promotion or password reset for existing users.
5. Rejection of weak passwords (< 8 characters).
6. Concurrent bootstrap attempts ensuring only one account is created.
7. Verification of audit logging and Bcrypt password hashing.
8. CLI bootstrap command functionality.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.services.bootstrap_service import (
    has_active_super_admin,
    provision_super_admin,
    BootstrapDisabledError,
    InvalidBootstrapSecretError,
    SuperAdminAlreadyExistsError,
    UserAlreadyExistsError,
    WeakPasswordError,
)
from app.scripts.bootstrap_super_admin import run_cli_bootstrap

BOOTSTRAP_TEST_SECRET = "super-secret-bootstrap-key-for-automated-testing-32chars"


@pytest.fixture(autouse=True)
def setup_bootstrap_key():
    """Ensure BOOTSTRAP_SECRET_KEY is configured for bootstrap tests."""
    original = settings.BOOTSTRAP_SECRET_KEY
    settings.BOOTSTRAP_SECRET_KEY = BOOTSTRAP_TEST_SECRET
    yield
    settings.BOOTSTRAP_SECRET_KEY = original


def test_has_active_super_admin_returns_false_when_none(db_session: Session):
    assert not has_active_super_admin(db_session)


def test_has_active_super_admin_returns_true_when_active_exists(db_session: Session):
    admin = User(
        email="super@example.com",
        hashed_password="somehashvalue",
        full_name="Super Admin",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    assert has_active_super_admin(db_session)


def test_has_active_super_admin_returns_false_if_suspended(db_session: Session):
    suspended = User(
        email="suspended_super@example.com",
        hashed_password="somehashvalue",
        full_name="Suspended Super Admin",
        role="SUPER_ADMIN",
        is_active=False,
    )
    db_session.add(suspended)
    db_session.commit()
    assert not has_active_super_admin(db_session)


def test_successful_initial_super_admin_provisioning_via_service(db_session: Session):
    admin = provision_super_admin(
        db=db_session,
        email="owner@example.com",
        password="StrongMasterPassword123!",
        full_name="System Owner",
        bootstrap_key=BOOTSTRAP_TEST_SECRET,
        method="service_test",
    )
    assert admin.id is not None
    assert admin.email == "owner@example.com"
    assert admin.role == UserRole.SUPER_ADMIN.value
    assert admin.is_active is True
    assert admin.token_version == 1
    assert verify_password("StrongMasterPassword123!", admin.hashed_password)

    # Verify audit log
    log = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "SUPER_ADMIN_BOOTSTRAPPED")
        .first()
    )
    assert log is not None
    assert log.actor_id == admin.id
    assert log.status == "SUCCESS"


def test_successful_initial_super_admin_provisioning_via_api(client, db_session: Session):
    res = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
        json={
            "email": "api_super@example.com",
            "password": "SuperSecurePassword123!",
            "full_name": "API Super Administrator",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "Initial Super Administrator provisioned successfully" in data["message"]
    user_info = data["user"]
    assert user_info["email"] == "api_super@example.com"
    assert user_info["role"] == "SUPER_ADMIN"
    assert "hashed_password" not in user_info

    # Confirm user exists in DB
    db_user = db_session.query(User).filter(User.email == "api_super@example.com").first()
    assert db_user is not None
    assert db_user.role == "SUPER_ADMIN"
    assert verify_password("SuperSecurePassword123!", db_user.hashed_password)


def test_bootstrap_via_body_key(client, db_session: Session):
    res = client.post(
        "/api/admin/bootstrap",
        json={
            "email": "body_key_super@example.com",
            "password": "SuperSecurePassword123!",
            "full_name": "Body Key Admin",
            "bootstrap_key": BOOTSTRAP_TEST_SECRET,
        },
    )
    assert res.status_code == 201
    assert res.json()["user"]["role"] == "SUPER_ADMIN"


def test_repeat_bootstrap_attempt_rejected(client, db_session: Session):
    # First attempt: succeeds
    res1 = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
        json={
            "email": "super1@example.com",
            "password": "Password123!",
            "full_name": "First Super Admin",
        },
    )
    assert res1.status_code == 201

    # Second attempt: rejected with 409 Conflict
    res2 = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
        json={
            "email": "super2@example.com",
            "password": "Password123!",
            "full_name": "Second Super Admin",
        },
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]

    # Verify only 1 Super Admin in database
    super_admins = db_session.query(User).filter(User.role == "SUPER_ADMIN").all()
    assert len(super_admins) == 1
    assert super_admins[0].email == "super1@example.com"


def test_bootstrap_missing_or_invalid_secret_rejected(client, db_session: Session):
    # 1. Missing secret key
    res_no_key = client.post(
        "/api/admin/bootstrap",
        json={
            "email": "unauth@example.com",
            "password": "Password123!",
        },
    )
    assert res_no_key.status_code == 401
    assert "Invalid or missing" in res_no_key.json()["detail"]

    # 2. Wrong secret key
    res_wrong_key = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": "completely-incorrect-bootstrap-key"},
        json={
            "email": "unauth@example.com",
            "password": "Password123!",
        },
    )
    assert res_wrong_key.status_code == 401
    assert "Invalid or missing" in res_wrong_key.json()["detail"]

    # Verify no super admin created
    assert not has_active_super_admin(db_session)


def test_bootstrap_disabled_when_secret_unset(client, db_session: Session):
    settings.BOOTSTRAP_SECRET_KEY = ""  # Unset
    res = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
        json={
            "email": "disabled@example.com",
            "password": "Password123!",
        },
    )
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"]


def test_bootstrap_with_existing_user_rejected(client, db_session: Session, auth_user: User):
    # auth_user exists with email test_owner@example.com and role User
    res = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
        json={
            "email": auth_user.email,
            "password": "NewAdminPassword123!",
            "full_name": "Hacked Promotion",
        },
    )
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]

    # Ensure existing user was NOT promoted or password reset
    db_session.refresh(auth_user)
    assert auth_user.role == "USER"
    assert verify_password("password123", auth_user.hashed_password)
    assert not verify_password("NewAdminPassword123!", auth_user.hashed_password)


def test_bootstrap_weak_password_rejected(client, db_session: Session):
    res = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
        json={
            "email": "weak@example.com",
            "password": "short",
        },
    )
    assert res.status_code == 422 or res.status_code == 400


def test_concurrent_bootstrap_attempts_only_one_succeeds(client, db_session: Session):
    """
    Simulate multiple concurrent initialization requests.
    Only one must succeed; all others must be rejected with 409 Conflict.
    """
    def attempt_bootstrap(index: int):
        return client.post(
            "/api/admin/bootstrap",
            headers={"X-Bootstrap-Key": BOOTSTRAP_TEST_SECRET},
            json={
                "email": f"concurrent_{index}@example.com",
                "password": f"ConcurrentPass{index}!",
                "full_name": f"Concurrent Admin {index}",
            },
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_bootstrap, i) for i in range(5)]
        responses = [f.result() for f in futures]

    status_codes = [r.status_code for r in responses]
    successes = [r for r in responses if r.status_code == 201]
    conflicts = [r for r in responses if r.status_code == 409]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {status_codes}"
    assert len(conflicts) == 4, f"Expected 4 conflicts, got {len(conflicts)}: {status_codes}"

    # Confirm only 1 Super Admin in DB
    super_admins = db_session.query(User).filter(User.role == "SUPER_ADMIN").all()
    assert len(super_admins) == 1


def test_cli_bootstrap_success(db_session: Session):
    code = run_cli_bootstrap(
        email="cli_super@example.com",
        password="CliPassword123!",
        full_name="CLI Administrator",
        bootstrap_key=BOOTSTRAP_TEST_SECRET,
        db_session=db_session,
    )
    assert code == 0
    created = db_session.query(User).filter(User.email == "cli_super@example.com").first()
    assert created is not None
    assert created.role == "SUPER_ADMIN"


def test_cli_bootstrap_repeat_fails(db_session: Session):
    # Run first time: succeeds
    code1 = run_cli_bootstrap(
        email="cli1@example.com",
        password="CliPassword123!",
        full_name="CLI Admin 1",
        bootstrap_key=BOOTSTRAP_TEST_SECRET,
        db_session=db_session,
    )
    assert code1 == 0

    # Run second time: fails with code 1
    code2 = run_cli_bootstrap(
        email="cli2@example.com",
        password="CliPassword123!",
        full_name="CLI Admin 2",
        bootstrap_key=BOOTSTRAP_TEST_SECRET,
        db_session=db_session,
    )
    assert code2 == 1


def test_cli_bootstrap_missing_key_fails(db_session: Session):
    code = run_cli_bootstrap(
        email="cli_nokey@example.com",
        password="CliPassword123!",
        full_name="CLI No Key",
        bootstrap_key="invalid-key-attempt",
        db_session=db_session,
    )
    assert code == 1
    assert not has_active_super_admin(db_session)
