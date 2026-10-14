import pytest


def test_auth_registration_and_login_flow(client):
    # 1. Register a new user
    register_payload = {
        "email": "sarah.connor@cyberdyne.net",
        "password": "StrongPassword123!",
        "full_name": "Sarah Connor"
    }
    reg_res = client.post("/api/auth/register", json=register_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "token" in reg_data
    assert reg_data["user"]["email"] == "sarah.connor@cyberdyne.net"
    assert reg_data["user"]["full_name"] == "Sarah Connor"
    token = reg_data["token"]

    # 2. Access /me with JWT token
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "sarah.connor@cyberdyne.net"

    # 3. Duplicate registration should be rejected
    dup_res = client.post("/api/auth/register", json=register_payload)
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.json()["detail"].lower()

    # 4. Successful login with correct credentials
    login_res = client.post("/api/auth/login", json={
        "email": "sarah.connor@cyberdyne.net",
        "password": "StrongPassword123!"
    })
    assert login_res.status_code == 200
    assert "token" in login_res.json()

    # 5. Failed login with incorrect password
    bad_login = client.post("/api/auth/login", json={
        "email": "sarah.connor@cyberdyne.net",
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401


def test_auth_protected_me_endpoint_requires_token(client):
    # No auth header
    res1 = client.get("/api/auth/me")
    assert res1.status_code == 401

    # Invalid token format
    res2 = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert res2.status_code == 401


def test_login_followed_by_authenticated_get_forms(client):
    # 1. Register a dedicated test user
    email = "form.viewer@example.com"
    pwd = "ViewerPassword123!"
    client.post("/api/auth/register", json={
        "email": email,
        "password": pwd,
        "full_name": "Form Viewer"
    })

    # 2. Login to receive authentic JWT access token
    login_res = client.post("/api/auth/login", json={
        "email": email,
        "password": pwd
    })
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    assert token and isinstance(token, str)

    # 3. Authenticated request to GET /api/forms succeeds with 200 OK
    forms_res = client.get("/api/forms", headers={"Authorization": f"Bearer {token}"})
    assert forms_res.status_code == 200
    assert isinstance(forms_res.json(), list)


def test_get_forms_token_scenarios(client):
    from datetime import timedelta
    from app.core.security import create_access_token

    # 1. Missing token (guest access to public forms) returns 200 OK
    guest_res = client.get("/api/forms")
    assert guest_res.status_code == 200
    assert isinstance(guest_res.json(), list)

    # 2. Invalid / malformed token returns 401
    invalid_res = client.get("/api/forms", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert invalid_res.status_code == 401
    assert invalid_res.json()["detail"] == "Invalid authentication token."

    # 3. Mock placeholder token (e.g. sess_...) returns 401
    mock_res = client.get("/api/forms", headers={"Authorization": "Bearer sess_demo_token_8849"})
    assert mock_res.status_code == 401
    assert mock_res.json()["detail"] == "Invalid authentication token."

    # 4. Expired token returns 401 with specific expiration detail
    expired_token = create_access_token(
        subject=99999,
        role="USER",
        token_version=1,
        expires_delta=timedelta(seconds=-10)
    )
    expired_res = client.get("/api/forms", headers={"Authorization": f"Bearer {expired_token}"})
    assert expired_res.status_code == 401
    assert expired_res.json()["detail"] == "Authentication token has expired. Please log in again."

    # 5. Invalid authorization header format returns 401
    malformed_header_res = client.get("/api/forms", headers={"Authorization": "TokenWithoutBearerPrefix"})
    assert malformed_header_res.status_code == 401
    assert "Expected 'Bearer <token>'" in malformed_header_res.json()["detail"]

