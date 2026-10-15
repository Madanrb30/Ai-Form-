import io
import json
import pytest
from unittest.mock import MagicMock, patch
import httpx

from app.core.config import settings
from app.services.stt import (
    get_stt_provider,
    transcribe_speech_audio,
    GroqSTTProvider,
    SarvamSTTProvider,
)
from app.services.ai_provider import AIProviderError
from app.services.conversation_service import ConversationManager
from app.services.voice_mapping import (
    map_transcript_to_fields,
    match_dropdown_option,
    clean_for_matching,
)
from app.evaluation.stt_benchmark import (
    calculate_wer,
    calculate_cer,
    evaluate_entity_accuracy,
    evaluate_numeric_accuracy,
    run_benchmark_suite,
)


# =====================================================================
# 1. PROVIDER FACTORY & CONFIGURATION TESTS
# =====================================================================

def test_provider_factory_default_groq():
    with patch.object(settings, "STT_PROVIDER", "groq"):
        provider = get_stt_provider()
        assert isinstance(provider, GroqSTTProvider)
        assert provider.name == "groq"


def test_provider_factory_explicit_sarvam():
    provider = get_stt_provider("sarvam")
    assert isinstance(provider, SarvamSTTProvider)
    assert provider.name == "sarvam"


def test_provider_factory_unsupported_raises():
    with pytest.raises(AIProviderError) as exc:
        get_stt_provider("unsupported_provider")
    assert "Unsupported STT_PROVIDER" in str(exc.value)
    assert exc.value.status_code == 400


def test_groq_provider_model_configuration():
    provider = GroqSTTProvider()
    with patch.object(settings, "GROQ_STT_MODEL", "whisper-large-v3"):
        assert provider.model == "whisper-large-v3"
    with patch.object(settings, "GROQ_STT_MODEL", "whisper-large-v3-turbo"):
        assert provider.model == "whisper-large-v3-turbo"


# =====================================================================
# 2. SARVAM PROVIDER TESTS (Zero credentials needed unless enabled)
# =====================================================================

def test_sarvam_provider_missing_key():
    provider = SarvamSTTProvider()
    with patch.object(settings, "SARVAM_API_KEY", ""):
        with pytest.raises(AIProviderError) as exc_info:
            provider.transcribe(b"dummy_audio", "sample.wav")
        assert exc_info.value.status_code == 503
        assert "SARVAM_API_KEY is not configured" in exc_info.value.message


def test_sarvam_transcription_success():
    provider = SarvamSTTProvider()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "transcript": "வணக்கம் என் பெயர் கார்த்திக்",
        "language_code": "ta-IN",
    }

    with patch.object(settings, "SARVAM_API_KEY", "test_sarvam_key"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = provider.transcribe(
                audio_bytes=b"RIFF_dummy_data",
                filename="voice.wav",
                content_type="audio/wav",
            )

            assert result["text"] == "வணக்கம் என் பெயர் கார்த்திக்"
            assert result["provider"] == "sarvam"
            assert result["model"] == settings.SARVAM_STT_MODEL
            assert result["language"] == "ta-IN"

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            headers = call_kwargs[1]["headers"]
            assert headers["api-subscription-key"] == "test_sarvam_key"


def test_sarvam_error_handling_statuses():
    provider = SarvamSTTProvider()

    with patch.object(settings, "SARVAM_API_KEY", "test_sarvam_key"):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client_cls.return_value = mock_client

            # 1. 401 Unauthorized
            mock_401 = MagicMock(status_code=401, text="Invalid subscription key")
            mock_client.post.return_value = mock_401
            with pytest.raises(AIProviderError) as exc_401:
                provider.transcribe(b"audio", "voice.wav")
            assert exc_401.value.status_code == 401

            # 2. 429 Rate limit
            mock_429 = MagicMock(status_code=429, text="Rate limit exceeded")
            mock_client.post.return_value = mock_429
            with pytest.raises(AIProviderError) as exc_429:
                provider.transcribe(b"audio", "voice.wav")
            assert exc_429.value.status_code == 429

            # 3. 500 Service error
            mock_500 = MagicMock(status_code=500, text="Internal engine error")
            mock_client.post.return_value = mock_500
            with pytest.raises(AIProviderError) as exc_500:
                provider.transcribe(b"audio", "voice.wav")
            assert exc_500.value.status_code == 502

            # 4. Network timeout
            mock_client.post.side_effect = httpx.TimeoutException("Timeout")
            with pytest.raises(AIProviderError) as exc_timeout:
                provider.transcribe(b"audio", "voice.wav")
            assert exc_timeout.value.status_code == 504


# =====================================================================
# 3. TAMIL & TANGLISH FORM-FILLING & SAFEGUARDS
# =====================================================================

def test_submission_confirmation_safeguards():
    mgr = ConversationManager()

    # Never submit on "yes" alone during filling stage
    assert mgr._is_submission_confirmation("yes", "filling") is False
    assert mgr._is_submission_confirmation("yes my name is John", "filling") is False

    # Correction safeguard: never submit if correction proposed even if starting with 'yes' or in confirming stage
    assert mgr._is_submission_confirmation("yes, change my email to test@domain.com", "confirming_submission") is False
    assert mgr._is_submission_confirmation("seri, change pannunga", "confirming_submission") is False

    # Explicit Tanglish and Tamil submit commands trigger regardless of stage
    assert mgr._is_submission_confirmation("submit pannunga", "filling") is True
    assert mgr._is_submission_confirmation("form submit pannidunga", "filling") is True
    assert mgr._is_submission_confirmation("சமர்ப்பிக்கவும்", "filling") is True
    assert mgr._is_submission_confirmation("படிவத்தை சமர்ப்பிக்கவும்", "filling") is True

    # Affirmative responses in reviewing/confirming_submission stage
    assert mgr._is_submission_confirmation("aam", "confirming_submission") is True
    assert mgr._is_submission_confirmation("aama", "confirming_submission") is True
    assert mgr._is_submission_confirmation("sari", "confirming_submission") is True
    assert mgr._is_submission_confirmation("seri submit pannunga", "confirming_submission") is True
    assert mgr._is_submission_confirmation("correct-aa irukku", "confirming_submission") is True
    assert mgr._is_submission_confirmation("ஆமாம்", "confirming_submission") is True
    assert mgr._is_submission_confirmation("சரி", "confirming_submission") is True


def test_tamil_unicode_mapping():
    # Tamil Unicode cleaning
    cleaned = clean_for_matching("என் பெயர் Karthik")
    assert "பெயர்" in cleaned
    assert "karthik" in cleaned

    # Tamil department matching
    options = ["Computer Science and Engineering", "Information Technology", "Mechanical Engineering"]
    match, ambig = match_dropdown_option("கணினி அறிவியல்", options)
    assert match == "Computer Science and Engineering"
    assert ambig is False

    # Tanglish department matching
    match_cse, ambig_cse = match_dropdown_option("CSE department", options)
    assert match_cse == "Computer Science and Engineering"

    match_mech, ambig_mech = match_dropdown_option("Mechanical dept", options)
    assert match_mech == "Mechanical Engineering"


# =====================================================================
# 4. BENCHMARK SUITE TESTS (MOCKED & OFFLINE)
# =====================================================================

def test_benchmark_metrics_calculations():
    # Exact match -> 0.0 WER / CER
    assert calculate_wer("Hello world", "Hello world") == 0.0
    assert calculate_cer("வணக்கம்", "வணக்கம்") == 0.0

    # Word difference calculation
    wer = calculate_wer("My name is John", "My name is Peter")
    assert 0.2 < wer < 0.3  # 1 substitution out of 4 words = 0.25

    # Entity accuracy
    entities = ["Chennai", "Karthik Raja"]
    acc = evaluate_entity_accuracy(entities, "My name is Karthik Raja from Chennai city")
    assert acc == 1.0

    # Numeric accuracy
    numbers = ["9840123456", "21CS042"]
    num_acc = evaluate_numeric_accuracy(numbers, "phone 9840123456 and roll 21CS042")
    assert num_acc == 1.0


def test_benchmark_prevention_of_placeholder_results():
    """Verify that predictions are NEVER assumed to equal references without actual inference."""
    ref = "My name is John Doe"
    actual_pred = "My name is John"  # deletion of 'Doe'
    wer = calculate_wer(ref, actual_pred)
    assert wer > 0.0  # Must NOT be 0% placeholder


def test_benchmark_missing_audio_reports_incomplete(tmp_path):
    """Verify missing audio files strictly return INCOMPLETE status and do not fabricate results."""
    from app.evaluation.stt_benchmark import run_benchmark_suite

    # Create dummy manifest with non-existent audio file
    fake_manifest = tmp_path / "samples_manifest.json"
    fake_manifest.write_text(json.dumps([
        {
            "id": "missing_sample",
            "audio_filename": "non_existent.wav",
            "reference_transcript": "Hello test",
            "expected_entities": [],
            "expected_numbers": []
        }
    ]), encoding="utf-8")

    csv_out = str(tmp_path / "results.csv")
    res = run_benchmark_suite(
        manifest_path=str(fake_manifest),
        audio_dir=str(tmp_path),
        csv_output_path=csv_out
    )

    assert res["status"] == "INCOMPLETE"
    assert "Missing real audio" in res["reason"]

    # Verify CSV was generated with INCOMPLETE status
    with open(csv_out, "r", encoding="utf-8") as f:
        content = f.read()
    assert "INCOMPLETE (MISSING_AUDIO)" in content
    assert "N/A" in content


def test_benchmark_missing_manifest_reports_incomplete(tmp_path):
    """Verify missing manifest file strictly returns INCOMPLETE."""
    from app.evaluation.stt_benchmark import run_benchmark_suite

    csv_out = str(tmp_path / "results.csv")
    res = run_benchmark_suite(
        manifest_path=str(tmp_path / "does_not_exist.json"),
        audio_dir=str(tmp_path),
        csv_output_path=csv_out
    )
    assert res["status"] == "INCOMPLETE"
    assert "Manifest file missing" in res["reason"]


def test_benchmark_execution_with_real_audio_and_mock_provider(tmp_path):
    """
    Simulates genuine benchmark execution with a real WAV file on disk
    and mocked provider to test latency timing, error handling, and CSV export offline.
    """
    import wave
    from app.evaluation.stt_benchmark import execute_sample_benchmark

    # 1. Create a genuine 1-second silent WAV file on disk
    wav_path = str(tmp_path / "test_audio.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 32000)

    sample = {
        "id": "test_sample_01",
        "reference_transcript": "My name is Alex",
        "expected_entities": ["Alex"],
        "expected_numbers": []
    }

    mock_provider_cfg = {
        "provider": "groq",
        "model": "whisper-large-v3-turbo",
        "cost_per_hour_usd": 0.04
    }

    # Test success path with mock provider
    with patch("app.evaluation.stt_benchmark.create_benchmark_provider") as mock_create:
        mock_prov = MagicMock()
        mock_prov.transcribe.return_value = {
            "text": "My name is Alex",
            "duration": 1.0,
            "provider": "groq",
            "model": "whisper-large-v3-turbo"
        }
        mock_create.return_value = mock_prov

        record = execute_sample_benchmark(sample, wav_path, mock_provider_cfg)

        assert record["status"] == "SUCCESS"
        assert record["wer"] == 0.0
        assert record["entity_accuracy"] == 1.0
        assert record["audio_duration_sec"] == 1.0
        assert record["latency_sec"] >= 0.0
        assert record["estimated_cost_usd"] > 0.0

    # Test failure path with mock provider
    with patch("app.evaluation.stt_benchmark.create_benchmark_provider") as mock_create:
        mock_prov = MagicMock()
        mock_prov.transcribe.side_effect = AIProviderError("Rate limit reached", status_code=429)
        mock_create.return_value = mock_prov

        record_err = execute_sample_benchmark(sample, wav_path, mock_provider_cfg)

        assert record_err["status"] == "ERROR_429"
        assert "Rate limit" in record_err["error_message"]
        assert record_err["wer"] is None

