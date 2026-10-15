import pytest
from app.models.form import Form
from app.models.user import User
from app.models.submission import Submission
from app.models.draft import Draft
from app.core.security import get_password_hash, create_access_token


@pytest.fixture
def users_and_tokens(db_session):
    # User 1: Alice
    u1 = User(
        email="alice@company.org",
        hashed_password=get_password_hash("AlicePassword123!"),
        full_name="Alice Smith",
        role="Manager",
        avatar="AS"
    )
    # User 2: Bob
    u2 = User(
        email="bob@company.org",
        hashed_password=get_password_hash("BobPassword123!"),
        full_name="Bob Jones",
        role="Engineer",
        avatar="BJ"
    )
    # User 3: Admin
    u_admin = User(
        email="admin@company.org",
        hashed_password=get_password_hash("AdminPassword123!"),
        full_name="Admin Boss",
        role="ADMIN",
        avatar="AD"
    )
    db_session.add_all([u1, u2, u_admin])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)
    db_session.refresh(u_admin)

    token1 = create_access_token(u1.id)
    token2 = create_access_token(u2.id)
    token_admin = create_access_token(u_admin.id)

    return {
        "alice": u1,
        "bob": u2,
        "admin": u_admin,
        "token_alice": token1,
        "token_bob": token2,
        "token_admin": token_admin,
    }


def test_cross_user_form_modification_and_deletion(client, users_and_tokens):
    alice = users_and_tokens["alice"]
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]

    # Alice creates a private form
    payload = {
        "title": "Alice's Private Appraisal Form",
        "description": "Confidential managerial review",
        "schema_json": {
            "title": "Alice's Private Appraisal Form",
            "fields": [
                {"name": "rating", "label": "Rating", "type": "number", "required": True}
            ]
        }
    }
    create_res = client.post(
        "/api/forms",
        json=payload,
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert create_res.status_code == 201
    form_id = create_res.json()["id"]

    # Bob attempts to UPDATE Alice's form -> 403 Forbidden
    update_res_bob = client.put(
        f"/api/forms/{form_id}",
        json={"title": "Hacked Title by Bob"},
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert update_res_bob.status_code == 403
    assert "permission" in update_res_bob.json()["detail"].lower()

    # Anonymous user attempts to UPDATE Alice's form -> 401 Unauthorized
    update_res_anon = client.put(
        f"/api/forms/{form_id}",
        json={"title": "Hacked Title by Anonymous"}
    )
    assert update_res_anon.status_code == 401

    # Bob attempts to DELETE Alice's form -> 403 Forbidden
    del_res_bob = client.delete(
        f"/api/forms/{form_id}",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert del_res_bob.status_code == 403

    # Anonymous user attempts to DELETE Alice's form -> 401 Unauthorized
    del_res_anon = client.delete(f"/api/forms/{form_id}")
    assert del_res_anon.status_code == 401

    # Alice CAN update her own form -> 200 OK
    update_res_alice = client.put(
        f"/api/forms/{form_id}",
        json={"title": "Alice's Updated Review Form"},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert update_res_alice.status_code == 200
    assert update_res_alice.json()["title"] == "Alice's Updated Review Form"


def test_cross_user_draft_isolation(client, users_and_tokens):
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]

    # Create a base form
    create_res = client.post(
        "/api/forms",
        json={
            "title": "Quarterly Goals",
            "schema_json": {
                "title": "Quarterly Goals",
                "fields": [{"name": "goal", "label": "Goal", "type": "text", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = create_res.json()["id"]

    # Alice saves a private draft
    alice_draft = {"goal": "Deliver Q3 Project with 100% test coverage"}
    save_res = client.post(
        f"/api/forms/{form_id}/draft",
        json={"values_json": alice_draft},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert save_res.status_code == 200

    # Bob fetches draft -> must NOT see Alice's draft
    bob_draft_res = client.get(
        f"/api/forms/{form_id}/draft",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_draft_res.status_code == 200
    assert bob_draft_res.json() is None

    # Anonymous user fetches draft -> must NOT see Alice's draft
    anon_draft_res = client.get(f"/api/forms/{form_id}/draft")
    assert anon_draft_res.status_code == 200
    assert anon_draft_res.json() is None

    # Bob deletes draft -> Alice's draft must NOT be deleted
    del_bob = client.delete(
        f"/api/forms/{form_id}/draft",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert del_bob.status_code == 204

    # Alice fetches draft -> her draft is still there
    alice_check = client.get(
        f"/api/forms/{form_id}/draft",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert alice_check.status_code == 200
    assert alice_check.json()["values_json"]["goal"] == "Deliver Q3 Project with 100% test coverage"


def test_cross_user_conversation_session_protection(client, users_and_tokens):
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]

    create_res = client.post(
        "/api/forms",
        json={
            "title": "Confidential Interview",
            "schema_json": {
                "title": "Confidential Interview",
                "fields": [{"name": "salary", "label": "Expected Salary", "type": "text", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = create_res.json()["id"]

    # Alice starts a session
    turn1 = client.post(
        f"/api/forms/{form_id}/conversation",
        json={"transcript": "My expected salary is 150000", "current_values": {}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert turn1.status_code == 200
    alice_session_id = turn1.json()["session_id"]

    # Bob tries to hijack Alice's conversation session
    turn_bob = client.post(
        f"/api/forms/{form_id}/conversation",
        json={"session_id": alice_session_id, "transcript": "Change salary to 50000", "current_values": {}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert turn_bob.status_code == 403
    assert "permission" in turn_bob.json()["detail"].lower()


def test_cross_user_submission_and_pdf_authorization(client, users_and_tokens):
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]

    # Alice creates private form
    form_res = client.post(
        "/api/forms",
        json={
            "title": "Executive Payroll Form",
            "schema_json": {
                "title": "Executive Payroll Form",
                "fields": [{"name": "bonus", "label": "Annual Bonus", "type": "number", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = form_res.json()["id"]

    # Alice submits a record
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"bonus": 75000}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    # Anonymous user attempts to read Alice's form submissions -> 401 Unauthorized
    anon_subs = client.get(f"/api/forms/{form_id}/submissions")
    assert anon_subs.status_code == 401

    # Bob reads Alice's form submissions -> Bob has not submitted any responses, so list is empty
    bob_subs = client.get(
        f"/api/forms/{form_id}/submissions",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_subs.status_code == 200
    assert len(bob_subs.json()) == 0

    # Bob attempts to download Alice's submission PDF -> 403 Forbidden
    bob_pdf = client.get(
        f"/api/forms/{form_id}/submissions/{sub_id}/pdf",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_pdf.status_code == 403

    # Anonymous attempts to download Alice's submission PDF -> 401 Unauthorized / 403 Forbidden
    anon_pdf = client.get(f"/api/forms/{form_id}/submissions/{sub_id}/pdf")
    assert anon_pdf.status_code in (401, 403)


    # Alice (form owner) downloads PDF -> 200 OK
    alice_pdf = client.get(
        f"/api/forms/{form_id}/submissions/{sub_id}/pdf",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert alice_pdf.status_code == 200
    assert alice_pdf.content.startswith(b"%PDF")


def test_private_form_visibility_and_template_sharing(client, users_and_tokens):
    """
    Test 1: Private forms are NOT visible to other regular users in list_forms or get_form.
    Test 2: Shared public templates ARE visible to all users.
    Test 3: Admin users CAN view private forms for administrative oversight.
    """
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]
    token_admin = users_and_tokens["token_admin"]

    # 1. Alice creates a private form (is_public=False)
    alice_form_res = client.post(
        "/api/forms",
        json={
            "title": "Alice's Secret Project Form",
            "is_public": False,
            "schema_json": {
                "title": "Secret Project",
                "fields": [{"name": "code_name", "label": "Codename", "type": "text"}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert alice_form_res.status_code == 201
    alice_private_id = alice_form_res.json()["id"]

    # 2. Alice creates a public shared template (is_public=True)
    shared_form_res = client.post(
        "/api/forms",
        json={
            "title": "Company-wide Feedback Template",
            "is_public": True,
            "schema_json": {
                "title": "Company Feedback",
                "fields": [{"name": "rating", "label": "Rating", "type": "number"}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert shared_form_res.status_code == 201
    shared_template_id = shared_form_res.json()["id"]

    # 3. Bob lists forms -> must see shared template, but NOT Alice's private form
    bob_list_res = client.get(
        "/api/forms",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_list_res.status_code == 200
    bob_form_ids = [f["id"] for f in bob_list_res.json()]
    assert shared_template_id in bob_form_ids
    assert alice_private_id not in bob_form_ids

    # 4. Bob tries to access Alice's private form directly by ID -> 403 Forbidden
    bob_direct_res = client.get(
        f"/api/forms/{alice_private_id}",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_direct_res.status_code == 403
    assert "access this private form" in bob_direct_res.json()["detail"].lower()

    # 5. Bob accesses shared template directly by ID -> 200 OK
    bob_shared_res = client.get(
        f"/api/forms/{shared_template_id}",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_shared_res.status_code == 200

    # 6. Admin lists forms -> Admin sees shared template, but NOT Alice's private form
    admin_list_res = client.get(
        "/api/forms",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert admin_list_res.status_code == 200
    admin_form_ids = [f["id"] for f in admin_list_res.json()]
    assert alice_private_id not in admin_form_ids
    assert shared_template_id in admin_form_ids

    # 7. Admin also cannot access Alice's private form directly -> 403 Forbidden
    admin_direct = client.get(
        f"/api/forms/{alice_private_id}",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert admin_direct.status_code == 403


def test_submission_isolation_on_shared_form(client, users_and_tokens):
    """
    On a shared form, regular users only see their own submissions.
    Admins can view all submissions for administrative oversight.
    """
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]
    token_admin = users_and_tokens["token_admin"]

    # Shared form created by admin or system
    form_res = client.post(
        "/api/forms",
        json={
            "title": "All-Hands Registration",
            "is_public": True,
            "schema_json": {
                "title": "Registration",
                "fields": [{"name": "diet", "label": "Dietary Preference", "type": "text"}]
            }
        },
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    form_id = form_res.json()["id"]

    # Alice submits response
    sub_alice_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"diet": "Vegetarian"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_alice_res.status_code == 201
    sub_alice_id = sub_alice_res.json()["id"]

    # Bob submits response
    sub_bob_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"diet": "Vegan"}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert sub_bob_res.status_code == 201
    sub_bob_id = sub_bob_res.json()["id"]

    # Alice lists submissions -> gets only her 1 submission
    alice_list = client.get(
        f"/api/forms/{form_id}/submissions",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert alice_list.status_code == 200
    alice_sub_ids = [s["id"] for s in alice_list.json()]
    assert alice_sub_ids == [sub_alice_id]

    # Bob lists submissions -> gets only his 1 submission
    bob_list = client.get(
        f"/api/forms/{form_id}/submissions",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_list.status_code == 200
    bob_sub_ids = [s["id"] for s in bob_list.json()]
    assert bob_sub_ids == [sub_bob_id]

    # Bob attempts to download Alice's submission PDF -> 403 Forbidden
    cross_pdf_res = client.get(
        f"/api/forms/{form_id}/submissions/{sub_alice_id}/pdf",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert cross_pdf_res.status_code == 403

    # Admin lists submissions -> gets both submissions
    admin_list = client.get(
        f"/api/forms/{form_id}/submissions",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert admin_list.status_code == 200
    admin_sub_ids = [s["id"] for s in admin_list.json()]
    assert sub_alice_id in admin_sub_ids
    assert sub_bob_id in admin_sub_ids


def test_user_dashboard_stats_isolation(client, users_and_tokens):
    """
    Ensure GET /api/forms/user/stats returns strictly isolated statistics for each user.
    """
    token_alice = users_and_tokens["token_alice"]
    token_bob = users_and_tokens["token_bob"]

    # Alice creates form 1 and submits a response
    f1_res = client.post(
        "/api/forms",
        json={
            "title": "Alice's First Form",
            "is_public": False,
            "schema_json": {
                "title": "First Form",
                "fields": [{"name": "item", "label": "Item", "type": "text"}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form1_id = f1_res.json()["id"]

    client.post(
        f"/api/forms/{form1_id}/submissions",
        json={"response_json": {"item": "Laptop"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )

    # Alice creates form 2 and saves an active draft (submissions auto-clear form 1's draft)
    f2_res = client.post(
        "/api/forms",
        json={
            "title": "Alice's In-Progress Draft Form",
            "is_public": False,
            "schema_json": {
                "title": "Draft Form",
                "fields": [{"name": "item", "label": "Item", "type": "text"}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form2_id = f2_res.json()["id"]

    client.post(
        f"/api/forms/{form2_id}/draft",
        json={"values_json": {"item": "Notebook"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )

    # Alice checks stats
    alice_stats = client.get(
        "/api/forms/user/stats",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert alice_stats.status_code == 200
    alice_data = alice_stats.json()
    assert alice_data["my_forms_count"] == 2
    assert alice_data["my_submissions_count"] == 1
    assert alice_data["my_drafts_count"] == 1

    # Bob checks stats -> Bob has no forms, drafts, or submissions
    bob_stats = client.get(
        "/api/forms/user/stats",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_stats.status_code == 200
    bob_data = bob_stats.json()
    assert bob_data["my_forms_count"] == 0
    assert bob_data["my_submissions_count"] == 0
    assert bob_data["my_drafts_count"] == 0


def test_guest_and_user_draft_isolation(client, users_and_tokens):
    """
    Ensure guest drafts and authenticated user drafts remain completely isolated.
    A guest cannot access an authenticated user's draft, and vice-versa.
    """
    token_alice = users_and_tokens["token_alice"]

    form_res = client.post(
        "/api/forms",
        json={
            "title": "Public Feedback",
            "is_public": True,
            "schema_json": {
                "title": "Public Feedback",
                "fields": [{"name": "feedback", "label": "Feedback", "type": "text"}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = form_res.json()["id"]

    # Alice saves an authenticated draft
    client.post(
        f"/api/forms/{form_id}/draft",
        json={"values_json": {"feedback": "Alice's authenticated feedback"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )

    # Guest saves a guest draft with a session_id
    guest_save = client.post(
        f"/api/forms/{form_id}/draft",
        json={"session_id": "session_guest_xyz123", "values_json": {"feedback": "Guest comments"}}
    )
    assert guest_save.status_code == 200

    # Guest queries Alice's draft (without session_id or with guest session_id) -> Alice's draft is NEVER returned
    guest_get1 = client.get(f"/api/forms/{form_id}/draft")
    assert guest_get1.status_code == 200
    if guest_get1.json():
        assert guest_get1.json()["values_json"].get("feedback") != "Alice's authenticated feedback"

    guest_get2 = client.get(f"/api/forms/{form_id}/draft?session_id=session_guest_xyz123")
    assert guest_get2.status_code == 200
    assert guest_get2.json()["values_json"]["feedback"] == "Guest comments"

    # Alice queries draft -> receives Alice's draft, NOT guest's draft
    alice_get = client.get(
        f"/api/forms/{form_id}/draft",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert alice_get.status_code == 200
    assert alice_get.json()["values_json"]["feedback"] == "Alice's authenticated feedback"
