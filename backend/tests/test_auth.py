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
