import io
import pytest
from unittest.mock import MagicMock, patch
from groq import RateLimitError, AuthenticationError, APITimeoutError, APIConnectionError, APIError

from app.core.config import settings
from app.services.ai_provider import ai_provider, AIProviderError
from app.models.form import Form
from app.models.user import User
from app.core.security import get_password_hash


def test_ai_provider_missing_key_for_transcription():
    with patch.object(settings, "GROQ_API_KEY", ""):
        with pytest.raises(AIProviderError) as exc_info:
            ai_provider.transcribe_audio(b"dummy audio", "audio.webm")
        assert exc_info.value.status_code == 503
        assert "GROQ_API_KEY is not configured" in exc_info.value.message


def test_ai_provider_transcribe_audio_success():
    mock_transcription = MagicMock()
    mock_transcription.text = "Hello, my name is Alex Doe."
    mock_transcription.duration = 2.45
    mock_transcription.language = "en"

    with patch.object(settings, "GROQ_API_KEY", "gsk_test_key_abc123"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.return_value = mock_transcription
            mock_groq_cls.return_value = mock_client

            result = ai_provider.transcribe_audio(
                audio_bytes=b"RIFF....dummy_wav_data",
                filename="test_audio.wav",
                content_type="audio/wav",
                language="en",
                prompt="Form filling"
            )

            assert result["text"] == "Hello, my name is Alex Doe."
            assert result["model"] == settings.GROQ_TRANSCRIPTION_MODEL
            assert result["duration"] == 2.45
            assert result["language"] == "en"

            mock_client.audio.transcriptions.create.assert_called_once()
            call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs["model"] == "whisper-large-v3-turbo"
            assert call_kwargs["language"] == "en"
            assert call_kwargs["prompt"] == "Form filling"
            assert call_kwargs["response_format"] == "verbose_json"


def test_ai_provider_transcribe_audio_errors():
    with patch.object(settings, "GROQ_API_KEY", "gsk_test_key_abc123"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_groq_cls.return_value = mock_client

            # 1. 401 Authentication Error
            mock_client.audio.transcriptions.create.side_effect = AuthenticationError(
                message="Invalid API Key",
                response=MagicMock(status_code=401),
                body={"error": {"message": "Invalid API Key"}}
            )
            with pytest.raises(AIProviderError) as exc_401:
                ai_provider.transcribe_audio(b"audio", "test.webm")
            assert exc_401.value.status_code == 401

            # 2. 429 Rate Limit Error
            mock_client.audio.transcriptions.create.side_effect = RateLimitError(
                message="Rate limit reached",
                response=MagicMock(status_code=429),
                body={"error": {"message": "Rate limit reached"}}
            )
            with pytest.raises(AIProviderError) as exc_429:
                ai_provider.transcribe_audio(b"audio", "test.webm")
            assert exc_429.value.status_code == 429

            # 3. 504 Connection/Timeout Error
            mock_client.audio.transcriptions.create.side_effect = APIConnectionError(
                request=MagicMock()
            )
            with pytest.raises(AIProviderError) as exc_504:
                ai_provider.transcribe_audio(b"audio", "test.webm")
            assert exc_504.value.status_code == 504

            # 4. 502 Generic API Error
            mock_client.audio.transcriptions.create.side_effect = APIError(
                message="Bad Gateway",
                request=MagicMock(),
                body={"error": {"message": "Bad Gateway"}}
            )
            with pytest.raises(AIProviderError) as exc_502:
                ai_provider.transcribe_audio(b"audio", "test.webm")
            assert exc_502.value.status_code == 502


def test_endpoint_transcribe_audio_empty_file(client):
    empty_file = io.BytesIO(b"")
    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("recording.webm", empty_file, "audio/webm")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_endpoint_transcribe_audio_unsupported_format(client):
    fake_exe = io.BytesIO(b"MZ\x90\x00...")
    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("malicious.exe", fake_exe, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]


def test_endpoint_transcribe_audio_oversized_file(client):
    with patch.object(settings, "MAX_AUDIO_SIZE_BYTES", 50):
        oversized = io.BytesIO(b"A" * 100)
        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("recording.webm", oversized, "audio/webm")},
        )
        assert response.status_code == 413
        assert "exceeds maximum size limit" in response.json()["detail"]


def test_endpoint_transcribe_audio_success(client):
    audio_content = io.BytesIO(b"RIFF_FAKE_AUDIO_DATA")

    with patch("app.api.voice.ai_provider.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {
            "text": "My email is test@domain.com",
            "model": "whisper-large-v3-turbo",
            "duration": 1.8,
            "language": "en"
        }

        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("voice_note.webm", audio_content, "audio/webm")},
            data={"language": "en", "prompt": "Please transcribe email accurately"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "My email is test@domain.com"
        assert data["model"] == "whisper-large-v3-turbo"
        assert data["duration"] == 1.8
        assert data["language"] == "en"
        mock_transcribe.assert_called_once()


def test_transcription_feeds_conversation_pipeline(client, db_session):
    # Setup test user and test form
    test_user = User(
        email="voiceuser@example.com",
        full_name="Voice User",
        hashed_password=get_password_hash("password123"),
    )
    db_session.add(test_user)
    db_session.commit()

    form_schema = {
        "title": "Contact Details",
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Email Address", "type": "email", "required": True},
        ]
    }
    test_form = Form(
        title="Contact Form",
        schema_json=form_schema,
        user_id=test_user.id,
    )
    db_session.add(test_form)
    db_session.commit()

    # Step 1: Transcribe audio through /api/voice/transcribe
    audio_content = io.BytesIO(b"FAKE_AUDIO_BYTES")
    with patch("app.api.voice.ai_provider.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {
            "text": "My full name is Jane Smith and my email is jane@example.com",
            "model": "whisper-large-v3-turbo",
            "duration": 3.2,
            "language": "en"
        }

        transcribe_res = client.post(
            "/api/voice/transcribe",
            files={"file": ("recording.webm", audio_content, "audio/webm")},
        )
        assert transcribe_res.status_code == 200
        transcribed_text = transcribe_res.json()["text"]

    # Step 2: Feed the transcribed text directly into the conversational filling endpoint
    with patch("app.services.conversation_service.ai_provider.process_conversation_turn") as mock_turn:
        mock_turn.return_value = {
            "assistant_response": "Thanks Jane! I've filled in your name and email.",
            "updated_values": {
                "full_name": "Jane Smith",
                "email": "jane@example.com"
            },
            "newly_filled": ["full_name", "email"],
            "confirmed_fields": ["full_name", "email"],
            "missing_fields": [],
            "is_completed": True
        }

        conv_res = client.post(
            f"/api/forms/{test_form.id}/conversation",
            json={
                "transcript": transcribed_text,
                "current_values": {}
            }
        )

        assert conv_res.status_code == 200
        conv_data = conv_res.json()
        assert conv_data["updated_values"]["full_name"] == "Jane Smith"
        assert conv_data["updated_values"]["email"] == "jane@example.com"
        assert conv_data["is_completed"] is True
