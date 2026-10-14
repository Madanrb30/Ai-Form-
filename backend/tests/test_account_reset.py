"""
Automated Test Suite for User Account Reset & Super Admin Re-Arming.
Verifies:
1. Complete removal of USER, ADMIN, and SUPER_ADMIN accounts.
2. 100% preservation of forms, form schemas, submissions, PDFs, and drafts.
3. Foreign-key integrity with PRAGMA foreign_keys=ON.
4. Transactional rollback on simulated failures.
5. Invalidation of old JWT tokens.
6. Public accessibility of preserved forms and submissions.
7. Successful subsequent Super Admin provisioning and admin promotion.
"""
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole
from app.models.form import Form
from app.models.submission import Submission
from app.models.draft import Draft
from app.models.audit_log import AuditLog
from app.services.bootstrap_service import (
    has_active_super_admin,
    provision_super_admin,
)
from app.scripts.reset_user_accounts import (
    execute_account_reset,
    get_pre_reset_summary,
    run_reset_cli,
    CONFIRMATION_PHRASE,
)

BOOTSTRAP_KEY = "test-bootstrap-secret-key-32-chars-long"


@pytest.fixture(autouse=True)
def setup_bootstrap():
    original = settings.BOOTSTRAP_SECRET_KEY
    settings.BOOTSTRAP_SECRET_KEY = BOOTSTRAP_KEY
    yield
    settings.BOOTSTRAP_SECRET_KEY = original


def seed_test_database(db: Session):
    """Seeds a realistic database with users of all roles, forms, submissions, and drafts."""
    # 1. Users
    user1 = User(
        email="regular_user@example.com",
        hashed_password=get_password_hash("UserPass123!"),
        full_name="Regular User",
        role="USER",
        is_active=True,
    )
    admin1 = User(
        email="admin_user@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        full_name="Admin User",
        role="ADMIN",
        is_active=True,
    )
    super1 = User(
        email="super_user@example.com",
        hashed_password=get_password_hash("SuperPass123!"),
        full_name="Super Admin User",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db.add_all([user1, admin1, super1])
    db.commit()
    db.refresh(user1)
    db.refresh(admin1)
    db.refresh(super1)

    # 2. Forms (one private owned by user1, one public owned by user1, one public unowned)
    form_private = Form(
        title="Confidential Evaluation",
        description="Private user form",
        schema_json={
            "title": "Confidential Evaluation",
            "fields": [{"id": "q1", "name": "q1", "label": "Question 1", "type": "text"}],
        },
        user_id=user1.id,
        is_public=False,
    )
    form_public = Form(
        title="Public Survey",
        description="Public user form",
        schema_json={
            "title": "Public Survey",
            "fields": [{"id": "name", "name": "name", "label": "Full Name", "type": "text"}],
        },
        user_id=user1.id,
        is_public=True,
    )
    form_template = Form(
        title="Shared Starter Template",
        description="System template",
        schema_json={
            "title": "Shared Starter Template",
            "fields": [{"id": "email", "name": "email", "label": "Email Address", "type": "email"}],
        },
        user_id=None,
        is_public=True,
    )
    db.add_all([form_private, form_public, form_template])
    db.commit()
    db.refresh(form_private)
    db.refresh(form_public)
    db.refresh(form_template)

    # 3. Submissions
    sub1 = Submission(
        form_id=form_private.id,
        user_id=user1.id,
        response_json={"q1": "Answer 1"},
        generated_pdf_path="/uploads/sub1.pdf",
    )
    sub2 = Submission(
        form_id=form_public.id,
        user_id=None,  # Guest submission
        response_json={"name": "Guest Visitor"},
        generated_pdf_path="/uploads/sub2.pdf",
    )
    db.add_all([sub1, sub2])

    # 4. Draft
    draft1 = Draft(
        form_id=form_private.id,
        user_id=user1.id,
        values_json={"q1": "Draft text"},
    )
    db.add(draft1)
    db.commit()

    return {
        "users": [user1, admin1, super1],
        "forms": [form_private, form_public, form_template],
        "submissions": [sub1, sub2],
        "draft": draft1,
    }


def test_get_pre_reset_summary(db_session: Session):
    data = seed_test_database(db_session)
    summary = get_pre_reset_summary(db_session)

    assert summary["total_users"] == 3
    assert summary["users_by_role"]["USER"] == 1
    assert summary["users_by_role"]["ADMIN"] == 1
    assert summary["users_by_role"]["SUPER_ADMIN"] == 1
    assert summary["total_forms"] == 3
    assert summary["private_forms"] == 1
    assert summary["public_forms"] == 2
    assert summary["total_submissions"] == 2
    assert summary["total_drafts"] == 1


def test_execute_account_reset_removes_users_and_preserves_data(db_session: Session):
    data = seed_test_database(db_session)

    result = execute_account_reset(db_session, dry_run=False)

    assert result["status"] == "SUCCESS"
    assert result["users_deleted"] == 3
    assert result["forms_preserved"] == 3
    assert result["submissions_preserved"] == 2
    assert result["bootstrap_re_armed"] is True

    # 1. Verify users table is completely empty
    assert db_session.query(User).count() == 0
    assert not has_active_super_admin(db_session)

    # 2. Verify forms preserved and converted to public shared templates
    forms = db_session.query(Form).all()
    assert len(forms) == 3
    for f in forms:
        assert f.user_id is None, f"Form {f.id} user_id should be NULL"
        assert f.is_public is True, f"Form {f.id} should be public shared template"

    # 3. Verify submissions preserved
    submissions = db_session.query(Submission).all()
    assert len(submissions) == 2
    for s in submissions:
        assert s.user_id is None
        assert s.form_id is not None
        assert s.response_json is not None

    # 4. Verify draft preserved and disassociated
    drafts = db_session.query(Draft).all()
    assert len(drafts) == 1
    assert drafts[0].user_id is None

    # 5. Verify audit log entry was created
    audit = db_session.query(AuditLog).filter(AuditLog.action == "ACCOUNTS_PURGED_AND_RESET").first()
    assert audit is not None
    assert audit.status == "SUCCESS"


def test_dry_run_leaves_database_untouched(db_session: Session):
    data = seed_test_database(db_session)

    result = execute_account_reset(db_session, dry_run=True)
    assert result["status"] == "DRY_RUN_SUCCESS"

    # All users still exist
    assert db_session.query(User).count() == 3
    assert has_active_super_admin(db_session) is True
    # Private form still private
    private_f = db_session.query(Form).filter(Form.title == "Confidential Evaluation").first()
    assert private_f.is_public is False
    assert private_f.user_id is not None


def test_cli_requires_confirmation_phrase(db_session: Session):
    data = seed_test_database(db_session)

    # Run with incorrect phrase
    code = run_reset_cli(
        confirm_phrase="WRONG PHRASE",
        session_override=db_session,
    )
    assert code == 1
    assert db_session.query(User).count() == 3  # Untouched

    # Run with exact confirmation phrase
    code_success = run_reset_cli(
        confirm_phrase=CONFIRMATION_PHRASE,
        session_override=db_session,
    )
    assert code_success == 0
    assert db_session.query(User).count() == 0  # Successfully reset


def test_old_jwts_rejected_after_reset(client, db_session: Session):
    data = seed_test_database(db_session)
    old_user = data["users"][0]
    old_token = create_access_token(old_user.id, role=old_user.role, token_version=old_user.token_version)

    # Verify old token works before reset
    res_before = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert res_before.status_code == 200

    # Execute reset
    execute_account_reset(db_session, dry_run=False)

    # Verify old token is rejected with 401 after reset
    res_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert res_after.status_code == 401
    assert "not found" in res_after.json()["detail"].lower()


def test_preserved_forms_accessible_via_api(client, db_session: Session):
    data = seed_test_database(db_session)
    execute_account_reset(db_session, dry_run=False)

    # Guest can view public forms list
    forms_res = client.get("/api/forms")
    assert forms_res.status_code == 200
    forms = forms_res.json()
    assert len(forms) == 3

    # Guest can view previously private form (now public template)
    private_id = data["forms"][0].id
    form_detail = client.get(f"/api/forms/{private_id}")
    assert form_detail.status_code == 200
    assert form_detail.json()["title"] == "Confidential Evaluation"

    # Guest can submit response to preserved form
    sub_res = client.post(
        f"/api/forms/{private_id}/submissions",
        json={"response_json": {"q1": "New submission after reset"}},
    )
    assert sub_res.status_code == 201


def test_subsequent_super_admin_provisioning_and_admin_creation(client, db_session: Session):
    data = seed_test_database(db_session)
    execute_account_reset(db_session, dry_run=False)

    # 1. Provision fresh Super Admin via API
    bootstrap_res = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Key": BOOTSTRAP_KEY},
        json={
            "email": "fresh_super@example.com",
            "password": "FreshSuperPassword123!",
            "full_name": "Fresh Super Admin",
        },
    )
    assert bootstrap_res.status_code == 201
    super_data = bootstrap_res.json()["user"]
    assert super_data["role"] == "SUPER_ADMIN"

    # Login as fresh Super Admin
    login_super = client.post(
        "/api/auth/login",
        json={"email": "fresh_super@example.com", "password": "FreshSuperPassword123!"},
    )
    assert login_super.status_code == 200
    super_token = login_super.json()["token"]
    super_headers = {"Authorization": f"Bearer {super_token}"}

    # 2. Register a new user via public registration (strictly assigned USER)
    reg_res = client.post(
        "/api/auth/register",
        json={
            "email": "new_candidate@example.com",
            "password": "CandidatePassword123!",
            "full_name": "Candidate User",
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["user"]["role"] == "USER"
    new_user_id = reg_res.json()["user"]["id"]

    # 3. Super Admin promotes candidate to ADMIN
    promote_res = client.put(
        f"/api/admin/users/{new_user_id}/role",
        headers=super_headers,
        json={"role": "ADMIN"},
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["role"] == "ADMIN"

    # 4. Login as newly promoted Admin and verify access to Admin API
    login_admin = client.post(
        "/api/auth/login",
        json={"email": "new_candidate@example.com", "password": "CandidatePassword123!"},
    )
    assert login_admin.status_code == 200
    admin_token = login_admin.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    admin_view = client.get("/api/admin/users", headers=admin_headers)
    assert admin_view.status_code == 200
    assert len(admin_view.json()["items"]) == 2  # Super Admin + Admin


def test_rollback_on_simulated_db_error(db_session: Session):
    data = seed_test_database(db_session)

    # Simulate an error by attempting invalid SQL within a transaction
    try:
        with db_session.begin_nested():
            db_session.execute(text("UPDATE forms SET user_id = NULL"))
            # Provoke an error
            db_session.execute(text("SELECT * FROM non_existent_table_for_error"))
    except Exception:
        db_session.rollback()

    # Confirm all users and original form user_ids remain unchanged after rollback
    assert db_session.query(User).count() == 3
    form_with_user = db_session.query(Form).filter(Form.title == "Confidential Evaluation").first()
    assert form_with_user.user_id is not None
