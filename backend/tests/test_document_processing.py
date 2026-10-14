import io
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from groq import RateLimitError, AuthenticationError, APITimeoutError

from app.core.config import settings
from app.schemas.form import FormSchemaDefinition, FormFieldSchema


def create_simple_pdf_bytes(text_lines):
    """Helper to generate in-memory valid vector/digital PDF bytes with selectable text."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    for line in text_lines:
        c.drawString(100, y, line)
        y -= 30
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_acroform_pdf_bytes():
    """Helper to generate in-memory PDF with native AcroForm form fields."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 700, "Membership Application Form")
    form = c.acroForm
    form.textfield(name="member_name", tooltip="Member Name", x=100, y=650, width=200, height=20)
    form.textfield(name="member_email", tooltip="Email", x=100, y=600, width=200, height=20)
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_empty_scanned_pdf_bytes():
    """Helper to generate a valid PDF page with zero text and zero AcroForms (simulating scanned image)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_valid_test_png_bytes(width=100, height=100):
    """Helper to generate in-memory valid PNG image bytes."""
    img = Image.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_multipage_pdf_bytes(num_pages=11):
    """Helper to generate a PDF exceeding standard page limits."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    for i in range(num_pages):
        c.drawString(100, 700, f"Page number {i + 1} content text with sufficient length for digital text recognition.")
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_hybrid_pdf_bytes():
    """Helper to generate a 2-page hybrid PDF (Page 1 digital text, Page 2 scanned/blank)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    # Page 1: digital text
    c.drawString(100, 750, "Student Admission Application Form")
    c.drawString(100, 720, "Full Name: Student Name Here")
    c.drawString(100, 690, "Email Address: student@university.edu")
    c.showPage()
    # Page 2: blank canvas simulating scanned attachment
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def test_upload_empty_document_rejected(client):
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("empty.pdf", b"", "application/pdf")}
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_upload_unsupported_extension_rejected(client):
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("malicious.exe", b"MZexecutabledata", "application/octet-stream")}
    )
    assert res.status_code == 400
    assert "unsupported" in res.json()["detail"].lower()


def test_upload_oversized_file_rejected(client):
    oversized = b"0" * (16 * 1024 * 1024)
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("giant.pdf", oversized, "application/pdf")}
    )
    assert res.status_code == 413
    assert "exceeds" in res.json()["detail"].lower()


def test_upload_corrupted_pdf_rejected(client):
    corrupted_bytes = b"%PDF-1.4 completely broken binary junk that cannot be parsed by pypdf"
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("broken.pdf", corrupted_bytes, "application/pdf")}
    )
    assert res.status_code == 400
    assert "invalid" in res.json()["detail"].lower() or "corrupted" in res.json()["detail"].lower() or "failed" in res.json()["detail"].lower()


def test_upload_corrupted_image_rejected(client):
    corrupted_img = b"PNGfakeheaderbrokenjunkdata"
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("corrupt.png", corrupted_img, "image/png")}
    )
    assert res.status_code == 400
    assert "invalid" in res.json()["detail"].lower() or "corrupted" in res.json()["detail"].lower()


def test_upload_digital_pdf_with_text(client):
    pdf_bytes = create_simple_pdf_bytes([
        "Medical Patient Intake Form",
        "Full Name: Patient Legal Name",
        "Date of Birth: 1990-01-01",
        "Emergency Contact Phone: 555-0199",
        "Allergies or Pre-existing Conditions: None"
    ])
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("patient_intake.pdf", pdf_bytes, "application/pdf")}
    )
    assert res.status_code == 200
    data = res.json()
    assert "schema_data" in data
    assert data["detected_fields_count"] > 0
    assert data["filename"] == "patient_intake.pdf"
    assert data["extraction_strategy"] == "digital_text"


def test_upload_pdf_with_acroform_fields(client):
    acro_bytes = create_acroform_pdf_bytes()
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("membership_form.pdf", acro_bytes, "application/pdf")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["has_acroform"] is True
    assert data["extraction_strategy"] == "acroform"
    assert data["detected_fields_count"] >= 2
    field_names = [f["name"] for f in data["schema_data"]["fields"]]
    assert "member_name" in field_names
    assert "member_email" in field_names


def test_upload_scanned_pdf_groq_vision_mocked(client):
    scanned_bytes = create_empty_scanned_pdf_bytes()
    mock_schema = FormSchemaDefinition(
        title="Scanned Hospital Form",
        description="Extracted via OCR",
        fields=[
            FormFieldSchema(
                name="patient_name",
                label="Patient Name",
                type="text",
                required=True,
                source_page=1,
                confidence=0.95,
                is_uncertain=False
            )
        ]
    )

    with patch("app.services.pdf_service.ai_provider.is_groq_configured", return_value=True):
        with patch("app.services.pdf_service.ai_provider.extract_form_from_images", return_value=mock_schema) as mock_vision:
            res = client.post(
                "/api/forms/upload-document",
                files={"file": ("scanned_invoice.pdf", scanned_bytes, "application/pdf")}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["extraction_strategy"] == "groq_vision"
            assert data["detected_fields_count"] == 1
            assert data["schema_data"]["fields"][0]["source_page"] == 1
            mock_vision.assert_called_once()


def test_upload_image_document_groq_vision_mocked(client):
    png_bytes = create_valid_test_png_bytes(width=150, height=150)
    mock_schema = FormSchemaDefinition(
        title="Insurance Claim Receipt",
        description="Vision OCR extracted",
        fields=[
            FormFieldSchema(
                name="claimant_name",
                label="Claimant Name",
                type="text",
                required=True,
                source_page=1,
                confidence=0.92,
                is_uncertain=False
            ),
            FormFieldSchema(
                name="claim_amount",
                label="Claim Amount",
                type="number",
                required=False,
                source_page=1,
                confidence=0.88,
                is_uncertain=False
            )
        ]
    )

    with patch("app.services.pdf_service.ai_provider.is_groq_configured", return_value=True):
        with patch("app.services.pdf_service.ai_provider.extract_form_from_images", return_value=mock_schema) as mock_vision:
            res = client.post(
                "/api/forms/upload-document",
                files={"file": ("receipt.png", png_bytes, "image/png")}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["extraction_strategy"] == "groq_vision"
            assert data["detected_fields_count"] == 2
            mock_vision.assert_called_once()


def test_upload_hybrid_pdf_mixed_pages(client):
    hybrid_bytes = create_hybrid_pdf_bytes()
    vision_mock_schema = FormSchemaDefinition(
        title="Attached Scanned Signature",
        description="Vision OCR fields",
        fields=[
            FormFieldSchema(
                name="guardian_signature_note",
                label="Guardian Signature Note",
                type="text",
                required=False,
                source_page=2,
                confidence=0.85,
                is_uncertain=False
            )
        ]
    )

    with patch("app.services.pdf_service.ai_provider.is_groq_configured", return_value=True):
        with patch("app.services.pdf_service.ai_provider.extract_form_from_images", return_value=vision_mock_schema):
            res = client.post(
                "/api/forms/upload-document",
                files={"file": ("hybrid_admission.pdf", hybrid_bytes, "application/pdf")}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["extraction_strategy"] == "hybrid"
            assert data["pages_processed"] == 2
            field_names = [f["name"] for f in data["schema_data"]["fields"]]
            assert "guardian_signature_note" in field_names


def test_upload_multipage_limit_enforced(client):
    excessive_pdf = create_multipage_pdf_bytes(num_pages=12)
    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("long_document.pdf", excessive_pdf, "application/pdf")}
    )
    assert res.status_code == 400
    assert "exceeds the maximum limit" in res.json()["detail"].lower()


def test_scanned_pdf_missing_groq_key_raises_503(client):
    scanned_bytes = create_empty_scanned_pdf_bytes()
    with patch.object(settings, "AI_DEMO_MODE", False):
        with patch("app.services.pdf_service.ai_provider.is_groq_configured", return_value=False):
            res = client.post(
                "/api/forms/upload-document",
                files={"file": ("scanned_paper.pdf", scanned_bytes, "application/pdf")}
            )
            assert res.status_code == 503
            assert "groq" in res.json()["detail"].lower()


def test_groq_vision_rate_limit_handling(client):
    png_bytes = create_valid_test_png_bytes()
    with patch.object(settings, "GROQ_API_KEY", "gsk_test_mock_123"):
        with patch("app.services.ai_provider.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = RateLimitError(
                message="Rate limit reached",
                response=MagicMock(status_code=429),
                body={"error": {"message": "Rate limit reached"}}
            )
            mock_groq_cls.return_value = mock_client

            res = client.post(
                "/api/forms/upload-document",
                files={"file": ("test.png", png_bytes, "image/png")}
            )
            assert res.status_code == 429
            assert "rate limit" in res.json()["detail"].lower()


def test_uncertain_fields_flagged(client):
    png_bytes = create_valid_test_png_bytes()
    mock_schema = FormSchemaDefinition(
        title="Faded Medical Scan",
        description="Faded text OCR",
        fields=[
            FormFieldSchema(
                name="doctor_notes",
                label="Doctor Notes (Unclear)",
                type="textarea",
                required=False,
                confidence=0.45,
                is_uncertain=True,
                source_page=1
            )
        ]
    )

    with patch("app.services.pdf_service.ai_provider.is_groq_configured", return_value=True):
        with patch("app.services.pdf_service.ai_provider.extract_form_from_images", return_value=mock_schema):
            res = client.post(
                "/api/forms/upload-document",
                files={"file": ("faded.png", png_bytes, "image/png")}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["uncertain_fields_count"] == 1
            assert data["schema_data"]["fields"][0]["is_uncertain"] is True
