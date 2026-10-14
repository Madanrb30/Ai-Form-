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
    db_session.add_all([u1, u2])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)

    token1 = create_access_token(u1.id)
    token2 = create_access_token(u2.id)

    return {
        "alice": u1,
        "bob": u2,
        "token_alice": token1,
        "token_bob": token2,
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
