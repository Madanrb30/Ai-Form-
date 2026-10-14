import json
import pytest
from unittest.mock import MagicMock, patch
from groq import RateLimitError, AuthenticationError

from app.services.ai_provider import ai_provider, AIProviderError
from app.core.config import settings


def test_ai_provider_is_configured_flag():
    # If key is empty or default placeholder, is_groq_configured returns False
    with patch.object(settings, "GROQ_API_KEY", "your_actual_groq_api_key"):
        assert not ai_provider.is_groq_configured()

    with patch.object(settings, "GROQ_API_KEY", "gsk_valid_test_key_123"):
        assert ai_provider.is_groq_configured()


def test_ai_provider_extract_json():
    # Valid raw JSON
    valid_raw = '{"title": "Feedback Form", "fields": []}'
    res = ai_provider.extract_json(valid_raw)
    assert res["title"] == "Feedback Form"

    # Fenced JSON with comments / newlines
    fenced = """```json
    {
        "title": "Onboarding",
        "fields": [{"name": "full_name", "label": "Full Name", "type": "text", "required": true}]
    }
    ```"""
    res2 = ai_provider.extract_json(fenced)
    assert res2["title"] == "Onboarding"
    assert len(res2["fields"]) == 1

    # Malformed text raises AIProviderError (and ValueError)
    with pytest.raises(AIProviderError) as exc_info:
        ai_provider.extract_json("Definitely not JSON here.")
    assert exc_info.value.status_code == 502


def test_ai_provider_missing_key_raises_error():
    with patch.object(settings, "GROQ_API_KEY", ""):
        with pytest.raises(AIProviderError) as exc_info:
            ai_provider.generate_form_schema("Create a survey")
        assert exc_info.value.status_code == 503
        assert "GROQ_API_KEY is not configured" in exc_info.value.message


def test_ai_provider_mocked_generate_form_schema():
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "title": "Employee Feedback",
        "description": "Monthly feedback form",
        "fields": [
            {
                "name": "employee_name",
                "label": "Employee Name",
                "type": "text",
                "required": True,
                "placeholder": "Enter full name"
            },
            {
                "name": "satisfaction_rating",
                "label": "Satisfaction Rating",
                "type": "number",
                "required": True,
                "placeholder": "1-5"
            }
        ]
    })
    mock_response.choices = [mock_choice]

    with patch.object(settings, "GROQ_API_KEY", "gsk_test_key_abc123"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_groq_cls.return_value = mock_client

            schema = ai_provider.generate_form_schema("Employee feedback form")
            assert schema.title == "Employee Feedback"
            assert len(schema.fields) == 2
            assert schema.fields[0].name == "employee_name"


def test_ai_provider_rate_limit_error_handling():
    with patch.object(settings, "GROQ_API_KEY", "gsk_test_key_abc123"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = RateLimitError(
                message="Rate limit reached",
                response=MagicMock(status_code=429),
                body={"error": {"message": "Rate limit reached"}}
            )
            mock_groq_cls.return_value = mock_client

            with pytest.raises(AIProviderError) as exc_info:
                ai_provider.generate_form_schema("Employee feedback form")
            assert exc_info.value.status_code == 429
            assert exc_info.value.is_retryable is True


def test_ai_provider_invalid_key_auth_error():
    with patch.object(settings, "GROQ_API_KEY", "gsk_invalid_test_key"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = AuthenticationError(
                message="Invalid API Key",
                response=MagicMock(status_code=401),
                body={"error": {"message": "Invalid API Key"}}
            )
            mock_groq_cls.return_value = mock_client

            with pytest.raises(AIProviderError) as exc_info:
                ai_provider.generate_form_schema("Employee feedback form")
            assert exc_info.value.status_code == 401
            assert "Invalid Groq API Key" in exc_info.value.message


def test_ai_service_missing_key_raises_explicit_503():
    from app.services.ai_service import generate_form_schema
    # When AI_DEMO_MODE is False and GROQ_API_KEY is not configured, it must NOT silently generate fake forms
    with patch.object(settings, "AI_DEMO_MODE", False):
        with patch.object(settings, "GROQ_API_KEY", ""):
            with pytest.raises(AIProviderError) as exc_info:
                generate_form_schema("Create a confidential tax form")
            assert exc_info.value.status_code == 503
            assert "GROQ_API_KEY is not configured" in exc_info.value.message


def test_ai_service_demo_mode_when_enabled():
    from app.services.ai_service import generate_form_schema
    # When AI_DEMO_MODE is True, it returns demo schema with is_demo=True
    with patch.object(settings, "AI_DEMO_MODE", True):
        schema, is_demo, provider, msg = generate_form_schema("Student registration form")
        assert is_demo is True
        assert provider == "demo_mode"
        assert schema.title == "Student Registration Form"


def test_process_conversation_turn_mocked():
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "extracted_fields": {"full_name": "Charlie Chaplin"},
        "assistant_response": "Got your name Charlie Chaplin. What is your email?",
        "needs_confirmation": False,
        "confidence_notes": "Extracted with high confidence"
    })
    mock_response.choices = [mock_choice]

    with patch.object(settings, "GROQ_API_KEY", "gsk_test_key_abc123"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_groq_cls.return_value = mock_client

            res = ai_provider.process_conversation_turn(
                form_title="Intake Form",
                field_statuses="Full Name: empty, Email: empty",
                user_speech="My name is Charlie Chaplin"
            )
            assert res["extracted_fields"]["full_name"] == "Charlie Chaplin"
            assert "Charlie Chaplin" in res["assistant_response"]

