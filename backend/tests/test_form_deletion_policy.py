import pytest
from unittest.mock import patch
from app.models.user import User
from app.models.form import Form
from app.models.submission import Submission
from app.models.draft import Draft
from app.models.audit_log import AuditLog
from app.core.security import get_password_hash, create_access_token


@pytest.fixture
def rbac_users(db_session):
    super_admin = User(
        email="superadmin@example.com",
        hashed_password=get_password_hash("SuperAdmin123!"),
        full_name="Super Administrator",
        role="SUPER_ADMIN",
    )
    admin_user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("AdminUser123!"),
        full_name="Regular Admin",
        role="ADMIN",
    )
    regular_user = User(
        email="user1@example.com",
        hashed_password=get_password_hash("User123456!"),
        full_name="Alice User",
        role="USER",
    )
    other_user = User(
        email="user2@example.com",
        hashed_password=get_password_hash("User123456!"),
        full_name="Bob User",
        role="USER",
    )
    db_session.add_all([super_admin, admin_user, regular_user, other_user])
    db_session.commit()
    for u in [super_admin, admin_user, regular_user, other_user]:
        db_session.refresh(u)

    return {
        "super_admin": super_admin,
        "super_admin_headers": {"Authorization": f"Bearer {create_access_token(super_admin.id)}"},
        "admin": admin_user,
        "admin_headers": {"Authorization": f"Bearer {create_access_token(admin_user.id)}"},
        "alice": regular_user,
        "alice_headers": {"Authorization": f"Bearer {create_access_token(regular_user.id)}"},
        "bob": other_user,
        "bob_headers": {"Authorization": f"Bearer {create_access_token(other_user.id)}"},
    }


def test_super_admin_can_delete_any_form_and_shared_templates(client, db_session, rbac_users):
    """SUPER_ADMIN can delete forms owned by others and shared templates."""
    # 1. Form owned by Alice
    alice_form = Form(
        title="Alice's Private Form",
        schema_json={"title": "Alice's Form", "fields": [{"name": "q1", "type": "text"}]},
        user_id=rbac_users["alice"].id,
        is_public=False,
    )
    # 2. Shared system template (user_id is None)
    template_form = Form(
        title="Public Shared Template",
        schema_json={"title": "Template", "fields": [{"name": "q1", "type": "text"}]},
        user_id=None,
        is_public=True,
    )
    db_session.add_all([alice_form, template_form])
    db_session.commit()
    db_session.refresh(alice_form)
    db_session.refresh(template_form)

    # Super Admin deletes Alice's form
    res = client.delete(f"/api/forms/{alice_form.id}", headers=rbac_users["super_admin_headers"])
    assert res.status_code == 204
    assert db_session.query(Form).filter(Form.id == alice_form.id).first() is None

    # Verify audit log was recorded
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "FORM_DELETED",
        AuditLog.target_id == str(alice_form.id)
    ).first()
    assert audit is not None
    assert audit.actor_id == rbac_users["super_admin"].id
    assert "Alice's Private Form" in audit.details

    # Super Admin deletes shared template
    res2 = client.delete(f"/api/forms/{template_form.id}", headers=rbac_users["super_admin_headers"])
    assert res2.status_code == 204
    assert db_session.query(Form).filter(Form.id == template_form.id).first() is None


def test_user_deletion_permissions(client, db_session, rbac_users):
    """USER can only delete their own form; cannot delete other users' forms or shared templates."""
    alice_form = Form(
        title="Alice's Form",
        schema_json={"title": "Alice's Form", "fields": []},
        user_id=rbac_users["alice"].id,
        is_public=False,
    )
    template_form = Form(
        title="System Template",
        schema_json={"title": "Template", "fields": []},
        user_id=None,
        is_public=True,
    )
    db_session.add_all([alice_form, template_form])
    db_session.commit()

    # Bob attempts to delete Alice's form -> 403 Forbidden
    res_bob = client.delete(f"/api/forms/{alice_form.id}", headers=rbac_users["bob_headers"])
    assert res_bob.status_code == 403
    assert "permission" in res_bob.json()["detail"].lower()

    # Alice attempts to delete shared system template -> 403 Forbidden
    res_template = client.delete(f"/api/forms/{template_form.id}", headers=rbac_users["alice_headers"])
    assert res_template.status_code == 403
    assert "shared system template" in res_template.json()["detail"].lower()

    # Anonymous user -> 401 Unauthorized
    res_anon = client.delete(f"/api/forms/{alice_form.id}")
    assert res_anon.status_code == 401

    # Alice deletes her own form -> 204 No Content
    res_own = client.delete(f"/api/forms/{alice_form.id}", headers=rbac_users["alice_headers"])
    assert res_own.status_code == 204
    assert db_session.query(Form).filter(Form.id == alice_form.id).first() is None


def test_admin_cannot_delete_other_users_forms_or_templates(client, db_session, rbac_users):
    """Standard ADMIN cannot delete other users' forms or shared templates."""
    bob_form = Form(
        title="Bob's Form",
        schema_json={"title": "Bob's Form", "fields": []},
        user_id=rbac_users["bob"].id,
        is_public=False,
    )
    template_form = Form(
        title="System Template",
        schema_json={"title": "Template", "fields": []},
        user_id=None,
        is_public=True,
    )
    db_session.add_all([bob_form, template_form])
    db_session.commit()

    # Admin attempts to delete Bob's form -> 403 Forbidden
    res = client.delete(f"/api/forms/{bob_form.id}", headers=rbac_users["admin_headers"])
    assert res.status_code == 403
    assert "permission" in res.json()["detail"].lower()

    # Admin attempts to delete shared template -> 403 Forbidden
    res_t = client.delete(f"/api/forms/{template_form.id}", headers=rbac_users["admin_headers"])
    assert res_t.status_code == 403
    assert "shared system template" in res_t.json()["detail"].lower()


def test_delete_nonexistent_form(client, rbac_users):
    """Attempting to delete a nonexistent form returns 404."""
    res = client.delete("/api/forms/9999999", headers=rbac_users["super_admin_headers"])
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_deletion_with_associated_submissions_and_drafts(client, db_session, rbac_users):
    """Forms with submissions require explicit confirmation before deletion."""
    form = Form(
        title="Feedback Form with Submissions",
        schema_json={"title": "Feedback", "fields": [{"name": "rating", "type": "number"}]},
        user_id=rbac_users["alice"].id,
        is_public=True,
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    # Add a draft
    draft = Draft(
        form_id=form.id,
        user_id=rbac_users["bob"].id,
        values_json={"rating": 5},
    )
    # Add a submission
    sub = Submission(
        form_id=form.id,
        user_id=rbac_users["bob"].id,
        response_json={"rating": 5},
    )
    db_session.add_all([draft, sub])
    db_session.commit()

    # Deleting without confirmation flag -> 409 Conflict
    res_unconfirmed = client.delete(
        f"/api/forms/{form.id}",
        headers=rbac_users["super_admin_headers"]
    )
    assert res_unconfirmed.status_code == 409
    assert "confirmation is required" in res_unconfirmed.json()["detail"].lower()

    # Ensure form, submission, and draft were NOT deleted
    assert db_session.query(Form).filter(Form.id == form.id).first() is not None
    assert db_session.query(Submission).filter(Submission.form_id == form.id).count() == 1
    assert db_session.query(Draft).filter(Draft.form_id == form.id).count() == 1

    # Deleting WITH confirmation flag -> 204 No Content
    res_confirmed = client.delete(
        f"/api/forms/{form.id}?confirm_delete_submissions=true",
        headers=rbac_users["super_admin_headers"]
    )
    assert res_confirmed.status_code == 204

    # Ensure form, submissions, and drafts are cleanly removed
    assert db_session.query(Form).filter(Form.id == form.id).first() is None
    assert db_session.query(Submission).filter(Submission.form_id == form.id).count() == 0
    assert db_session.query(Draft).filter(Draft.form_id == form.id).count() == 0


def test_database_rollback_on_deletion_failure(client, db_session, rbac_users):
    """When database error occurs during deletion, changes are rolled back and 500 returned."""
    form = Form(
        title="Form for Rollback Test",
        schema_json={"title": "Test", "fields": []},
        user_id=rbac_users["super_admin"].id,
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    # Mock db.commit to raise an exception
    with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("Simulated SQLite write error")):
        res = client.delete(f"/api/forms/{form.id}", headers=rbac_users["super_admin_headers"])
        assert res.status_code == 500
        assert "database error" in res.json()["detail"].lower()

    # Verify form still exists due to rollback
    db_session.expire_all()
    assert db_session.query(Form).filter(Form.id == form.id).first() is not None
