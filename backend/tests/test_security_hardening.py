import io
import time
import json
import pytest
from datetime import timedelta
from unittest.mock import patch

from app.core.config import Settings
from app.core.security import create_access_token, get_password_hash, clear_login_attempts
from app.models.user import User
from app.models.form import Form
from app.models.submission import Submission
from app.models.draft import Draft
from app.services.pdf_service import generate_completed_pdf


@pytest.fixture
def auth_fixtures(db_session):
    u1 = User(
        email="alice_sec@example.com",
        hashed_password=get_password_hash("StrongAlicePass123!"),
        full_name="Alice Sec",
        role="User",
        avatar="AS",
    )
    u2 = User(
        email="bob_sec@example.com",
        hashed_password=get_password_hash("StrongBobPass123!"),
        full_name="Bob Sec",
        role="User",
        avatar="BS",
    )
    db_session.add_all([u1, u2])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)

    return {
        "alice": u1,
        "bob": u2,
        "token_alice": create_access_token(u1.id),
        "token_bob": create_access_token(u2.id),
        "expired_token_alice": create_access_token(u1.id, expires_delta=timedelta(seconds=-10)),
    }


def test_production_config_fails_safely():
    # 1. Missing secret in production
    with pytest.raises(ValueError) as exc1:
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="")
    assert "Production configuration error" in str(exc1.value)

    # 2. Known insecure/default secret in production
    with pytest.raises(ValueError) as exc2:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="voxform-secure-production-jwt-secret-key-random-88492"
        )
    assert "Production configuration error" in str(exc2.value)

    # 3. Too short secret in production
    with pytest.raises(ValueError) as exc3:
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="short-secret-under-32-chars")
    assert "at least 32 characters" in str(exc3.value)

    # 4. Valid strong secret in production with live AI key
    prod_settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="a" * 32,
        GROQ_API_KEY="gsk_valid_prod_key_12345",
        AI_DEMO_MODE=False,
    )
    assert prod_settings.ENVIRONMENT == "production"
    assert prod_settings.SEED_DEMO_USER is False


def test_invalid_and_expired_jwt_handling(client, auth_fixtures):
    # 1. Expired token -> 401
    res_expired = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {auth_fixtures['expired_token_alice']}"}
    )
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json()["detail"].lower()

    # 2. Malformed token -> 401
    res_malformed = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"}
    )
    assert res_malformed.status_code == 401
    assert "invalid" in res_malformed.json()["detail"].lower()

    # 3. Bad header prefix -> 401
    res_bad_prefix = client.get(
        "/api/auth/me",
        headers={"Authorization": "Token abcdef"}
    )
    assert res_bad_prefix.status_code == 401


def test_anonymous_cannot_hijack_authenticated_session(client, auth_fixtures):
    token_alice = auth_fixtures["token_alice"]
    token_bob = auth_fixtures["token_bob"]

    # Create form
    f_res = client.post(
        "/api/forms",
        json={
            "title": "Secret Survey",
            "schema_json": {
                "title": "Secret Survey",
                "fields": [{"name": "feedback", "label": "Feedback", "type": "text", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = f_res.json()["id"]

    # Alice begins session
    turn_alice = client.post(
        f"/api/forms/{form_id}/conversation",
        json={"transcript": "My feedback is confidential", "current_values": {}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert turn_alice.status_code == 200
    session_id = turn_alice.json()["session_id"]

    # Anonymous attempts to access Alice's session -> must be rejected with 401
    turn_anon = client.post(
        f"/api/forms/{form_id}/conversation",
        json={"session_id": session_id, "transcript": "Hijacking session", "current_values": {}}
    )
    assert turn_anon.status_code == 401

    # Bob attempts to access Alice's session -> must be rejected with 403
    turn_bob = client.post(
        f"/api/forms/{form_id}/conversation",
        json={"session_id": session_id, "transcript": "Bob hijacking", "current_values": {}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert turn_bob.status_code == 403


def test_private_form_access_control(client, auth_fixtures):
    token_alice = auth_fixtures["token_alice"]
    token_bob = auth_fixtures["token_bob"]

    # Alice creates a private form (is_public=False)
    create_res = client.post(
        "/api/forms",
        json={
            "title": "Alice Private Ledger",
            "is_public": False,
            "schema_json": {
                "title": "Alice Private Ledger",
                "fields": [{"name": "account", "label": "Account", "type": "text", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert create_res.status_code == 201
    form_id = create_res.json()["id"]
    assert create_res.json()["is_public"] is False

    # Anonymous GET /forms/{id} -> 401
    anon_get = client.get(f"/api/forms/{form_id}")
    assert anon_get.status_code == 401

    # Bob GET /forms/{id} -> 403
    bob_get = client.get(f"/api/forms/{form_id}", headers={"Authorization": f"Bearer {token_bob}"})
    assert bob_get.status_code == 403

    # Alice GET /forms/{id} -> 200
    alice_get = client.get(f"/api/forms/{form_id}", headers={"Authorization": f"Bearer {token_alice}"})
    assert alice_get.status_code == 200
    assert alice_get.json()["title"] == "Alice Private Ledger"

    # In GET /forms:
    # Alice sees it
    alice_list = client.get("/api/forms", headers={"Authorization": f"Bearer {token_alice}"})
    assert any(f["id"] == form_id for f in alice_list.json())

    # Bob does NOT see it
    bob_list = client.get("/api/forms", headers={"Authorization": f"Bearer {token_bob}"})
    assert not any(f["id"] == form_id for f in bob_list.json())

    # Anonymous does NOT see it
    anon_list = client.get("/api/forms")
    assert not any(f["id"] == form_id for f in anon_list.json())


def test_multi_user_draft_no_deletion_collision(client, auth_fixtures):
    token_alice = auth_fixtures["token_alice"]
    token_bob = auth_fixtures["token_bob"]

    # Public form
    f_res = client.post(
        "/api/forms",
        json={
            "title": "Shared Hackathon Registration",
            "schema_json": {
                "title": "Shared Hackathon Registration",
                "fields": [
                    {"name": "team_name", "label": "Team Name", "type": "text", "required": True},
                    {"name": "email", "label": "Email", "type": "email", "required": True}
                ]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = f_res.json()["id"]

    # Alice saves draft
    client.post(
        f"/api/forms/{form_id}/draft",
        json={"values_json": {"team_name": "Alice Cyber Team"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )

    # Bob saves draft
    client.post(
        f"/api/forms/{form_id}/draft",
        json={"values_json": {"team_name": "Bob Builders"}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )

    # Alice submits her form
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"team_name": "Alice Cyber Team", "email": "alice@team.org"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_res.status_code == 201

    # Alice's draft should be cleared
    alice_draft = client.get(f"/api/forms/{form_id}/draft", headers={"Authorization": f"Bearer {token_alice}"})
    assert alice_draft.json() is None

    # Bob's draft must NOT have been deleted!
    bob_draft = client.get(f"/api/forms/{form_id}/draft", headers={"Authorization": f"Bearer {token_bob}"})
    assert bob_draft.json() is not None
    assert bob_draft.json()["values_json"]["team_name"] == "Bob Builders"


def test_pdf_special_characters_escaping():
    # User inputs with HTML/XML special characters that previously crashed ReportLab
    fields_schema = [
        {"name": "company", "label": "Company & Co <Inc>", "type": "text"},
        {"name": "notes", "label": "Special Notes", "type": "textarea"},
    ]
    response_data = {
        "company": "Procter & Gamble <P&G> \"Global\"",
        "notes": "Scores: Math < 80 & Physics > 90. <script>alert('xss')</script>",
    }

    pdf_path = generate_completed_pdf(
        form_title="Safety & Compliance <Audit>",
        form_description="Contains & symbols and <tags>",
        fields_schema=fields_schema,
        response_data=response_data,
        submission_id=9999,
    )
    assert pdf_path.endswith(".pdf")
    with open(pdf_path, "rb") as f:
        data = f.read()
    assert data.startswith(b"%PDF")


def test_pdf_download_query_token_authentication(client, auth_fixtures):
    token_alice = auth_fixtures["token_alice"]
    token_bob = auth_fixtures["token_bob"]

    # Alice creates a private form
    f_res = client.post(
        "/api/forms",
        json={
            "title": "Private Appraisal",
            "is_public": False,
            "schema_json": {
                "title": "Private Appraisal",
                "fields": [{"name": "score", "label": "Score", "type": "number", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = f_res.json()["id"]

    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"score": 95}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    sub_id = sub_res.json()["id"]

    # Direct browser click using ?token= query parameter -> 200 OK
    res_query = client.get(f"/api/forms/{form_id}/submissions/{sub_id}/pdf?token={token_alice}")
    assert res_query.status_code == 200
    assert res_query.content.startswith(b"%PDF")

    # Bob's query token -> 403 Forbidden
    res_bob_query = client.get(f"/api/forms/{form_id}/submissions/{sub_id}/pdf?token={token_bob}")
    assert res_bob_query.status_code == 403


def test_password_length_validation_on_register(client):
    # Password shorter than 8 chars -> 422
    short_res = client.post(
        "/api/auth/register",
        json={"email": "short_pass@example.com", "password": "short"}
    )
    assert short_res.status_code == 422

    # Valid >= 8 chars password -> 201
    good_res = client.post(
        "/api/auth/register",
        json={"email": "good_pass@example.com", "password": "StrongPassword123!"}
    )
    assert good_res.status_code == 201


def test_auth_login_rate_limiting(client):
    email = "ratelimit_target@example.com"
    clear_login_attempts(email)

    # 10 invalid attempts
    for _ in range(10):
        res = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
        assert res.status_code == 401

    # 11th attempt is rate-limited -> 429
    blocked = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    assert blocked.status_code == 429
    assert "too many" in blocked.json()["detail"].lower()
    clear_login_attempts(email)


def test_unowned_shared_template_cannot_be_modified_or_deleted(client, db_session, auth_fixtures):
    token_alice = auth_fixtures["token_alice"]

    # Create unowned shared system template (user_id is None)
    template = Form(
        title="Official Government Form Template",
        schema_json={
            "title": "Official Government Form",
            "fields": [{"name": "citizen_id", "label": "Citizen ID", "type": "text"}]
        },
        user_id=None,
        is_public=True,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    # 1. Anonymous visitor cannot update or delete
    assert client.put(f"/api/forms/{template.id}", json={"title": "Hacked"}).status_code == 401
    assert client.delete(f"/api/forms/{template.id}").status_code == 401

    # 2. Regular authenticated user cannot update or delete unowned template
    put_res = client.put(
        f"/api/forms/{template.id}",
        json={"title": "Alice Modified Template"},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert put_res.status_code == 403
    assert "shared system template" in put_res.json()["detail"].lower()

    del_res = client.delete(
        f"/api/forms/{template.id}",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert del_res.status_code == 403
    assert "shared system template" in del_res.json()["detail"].lower()


def test_submission_history_isolation_on_public_form(client, auth_fixtures):
    token_alice = auth_fixtures["token_alice"]
    token_bob = auth_fixtures["token_bob"]

    # Alice creates a public form
    form_res = client.post(
        "/api/forms",
        json={
            "title": "Community Survey",
            "is_public": True,
            "schema_json": {
                "title": "Community Survey",
                "fields": [{"name": "feedback", "label": "Feedback", "type": "text", "required": True}]
            }
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    form_id = form_res.json()["id"]

    # 1. Alice submits response A
    client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"feedback": "Alice personal feedback"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )

    # 2. Bob submits response B
    client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"feedback": "Bob confidential submission"}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )

    # 3. Anonymous visitor attempts to view submissions -> 401 Unauthorized
    anon_subs = client.get(f"/api/forms/{form_id}/submissions")
    assert anon_subs.status_code == 401

    # 4. Bob retrieves submissions -> receives ONLY Bob's submission
    bob_subs = client.get(f"/api/forms/{form_id}/submissions", headers={"Authorization": f"Bearer {token_bob}"})
    assert bob_subs.status_code == 200
    bob_list = bob_subs.json()
    assert len(bob_list) == 1
    assert bob_list[0]["response_json"]["feedback"] == "Bob confidential submission"

    # 5. Alice (form owner) retrieves submissions -> receives both submissions
    alice_subs = client.get(f"/api/forms/{form_id}/submissions", headers={"Authorization": f"Bearer {token_alice}"})
    assert alice_subs.status_code == 200
    alice_list = alice_subs.json()
    assert len(alice_list) == 2


def test_upload_magic_bytes_inspection(client):
    # Spoofed PDF (has .pdf extension but binary content is not PDF)
    fake_pdf = client.post(
        "/api/forms/upload-document",
        files={"file": ("spoofed.pdf", b"This is plain text pretending to be PDF", "application/pdf")}
    )
    assert fake_pdf.status_code == 400
    assert "invalid pdf" in fake_pdf.json()["detail"].lower()

    # Spoofed PNG (has .png extension but invalid magic header)
    fake_png = client.post(
        "/api/forms/upload-document",
        files={"file": ("spoofed.png", b"GIF89a fake image", "image/png")}
    )
    assert fake_png.status_code == 400
    assert "invalid png" in fake_png.json()["detail"].lower()


def test_production_demo_user_seeding_rejected():
    # Production with SEED_DEMO_USER=True must fail fast
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="c" * 32,
            SEED_DEMO_USER=True,
            GROQ_API_KEY="gsk_valid_key",
        )
    assert "SEED_DEMO_USER is prohibited in production" in str(exc.value)

    # Production with DEV_FALLBACK_SECRET must fail fast
    with pytest.raises(ValueError) as exc2:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="voxform-dev-ephemeral-jwt-key-2026-safe-for-local-testing-only-99",
            GROQ_API_KEY="gsk_valid_key",
        )
    assert "Production configuration error" in str(exc2.value)
