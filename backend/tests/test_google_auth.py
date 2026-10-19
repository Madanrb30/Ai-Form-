import pytest
from unittest.mock import patch
from app.models.user import User
from app.core.security import get_password_hash


def test_google_auth_new_user_creates_default_user_role(client, db_session):
    """Google sign-in for a new email creates an account with default USER role."""
    mock_id_info = {
        "iss": "https://accounts.google.com",
        "sub": "google-user-id-12345",
        "email": "google_newbie@example.com",
        "email_verified": True,
        "name": "Google Newbie",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        res = client.post("/api/auth/google", json={"credential": "valid.mock.google.id.token.credential"})
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert data["user"]["email"] == "google_newbie@example.com"
        assert data["user"]["role"] == "USER"

    # Verify persisted in database with role USER
    user = db_session.query(User).filter(User.email == "google_newbie@example.com").first()
    assert user is not None
    assert user.role == "USER"


def test_google_auth_existing_admin_preserves_role(client, db_session):
    """Google sign-in for an existing ADMIN or SUPER_ADMIN preserves their assigned role."""
    admin_user = User(
        email="existing_admin@example.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="Existing Administrator",
        role="ADMIN",
        avatar="EA",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    mock_id_info = {
        "iss": "accounts.google.com",
        "sub": "google-admin-id-999",
        "email": "existing_admin@example.com",
        "email_verified": True,
        "name": "Existing Administrator",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        res = client.post("/api/auth/google", json={"credential": "valid.mock.google.id.token.credential"})
        assert res.status_code == 200
        data = res.json()
        assert data["user"]["email"] == "existing_admin@example.com"
        # Role must remain ADMIN!
        assert data["user"]["role"] == "ADMIN"


def test_google_auth_suspended_account_rejected(client, db_session):
    """Suspended accounts cannot log in through Google OAuth."""
    suspended_user = User(
        email="suspended_oauth@example.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="Suspended Person",
        role="USER",
        avatar="SP",
        is_active=False,
    )
    db_session.add(suspended_user)
    db_session.commit()

    mock_id_info = {
        "iss": "https://accounts.google.com",
        "sub": "google-suspended-id-000",
        "email": "suspended_oauth@example.com",
        "email_verified": True,
        "name": "Suspended Person",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        res = client.post("/api/auth/google", json={"credential": "valid.mock.google.id.token.credential"})
        assert res.status_code == 403
        assert "suspended" in res.json()["detail"].lower()


def test_google_auth_unverified_email_rejected(client):
    """Google accounts with unverified email addresses must be rejected."""
    mock_id_info = {
        "iss": "https://accounts.google.com",
        "sub": "google-unverified-id",
        "email": "unverified@example.com",
        "email_verified": False,
        "name": "Unverified User",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        res = client.post("/api/auth/google", json={"credential": "valid.mock.google.id.token.credential"})
        assert res.status_code == 400
        assert "not verified" in res.json()["detail"].lower()


def test_google_auth_invalid_issuer_rejected(client):
    """Tokens with an unauthorized issuer are rejected."""
    mock_id_info = {
        "iss": "https://evil-issuer.example.com",
        "sub": "hacker-sub",
        "email": "hacker@example.com",
        "email_verified": True,
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        res = client.post("/api/auth/google", json={"credential": "valid.mock.google.id.token.credential"})
        assert res.status_code == 401
        assert "issuer" in res.json()["detail"].lower()


def test_google_auth_invalid_token_rejected(client):
    """Invalid or expired Google tokens raise 401 Unauthorized."""
    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token expired")):
        res = client.post("/api/auth/google", json={"credential": "expired.invalid.token.credential"})
        assert res.status_code == 401
        assert "invalid or expired" in res.json()["detail"].lower()
