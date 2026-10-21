import io
import os
import json
import pytest
from pypdf import PdfWriter, PdfReader
from pypdf.generic import (
    ByteStringObject,
    TextStringObject,
    NameObject,
    DictionaryObject,
    ArrayObject,
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from app.schemas.form import (
    FormFieldSchema,
    FormSchemaDefinition,
    DocumentExtractResponse,
    sanitize_json_value,
)
from app.services.pdf_service import process_document_hybrid, analyze_pdf_pages


def create_pdf_with_digital_signature():
    """Generates a valid PDF with selectable text and a mock digital signature dictionary."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "Tax Invoice")
    c.drawString(100, 720, "Customer Name: John Doe")
    c.drawString(100, 690, "Billing Address: 123 Main Street")
    c.drawString(100, 660, "Invoice Amount: $450.00")
    c.save()
    buffer.seek(0)

    # Read with pypdf and inject a digital signature field into AcroForm
    reader = PdfReader(buffer)
    writer = PdfWriter()
    writer.append(reader)

    # Create a signature dictionary with raw non-UTF-8 bytes (exact pattern of PKCS#7 /Contents)
    sig_dict = DictionaryObject()
    sig_dict[NameObject("/Type")] = NameObject("/Sig")
    sig_dict[NameObject("/Filter")] = NameObject("/Adobe.PPKLite")
    sig_dict[NameObject("/SubFilter")] = NameObject("/adbe.pkcs7.detached")
    sig_dict[NameObject("/Name")] = TextStringObject("DS Test Company 01")
    sig_dict[NameObject("/Reason")] = TextStringObject("Tax Invoice Verification")
    # Non-UTF8 byte sequence: index 0 is '0', index 1 is \x80
    sig_dict[NameObject("/Contents")] = ByteStringObject(b"0\x80\x06\t*\x86H\x86\xf7\r\x01\x07\x02\xa0\x80")
    sig_dict[NameObject("/ByteRange")] = ArrayObject([0, 100, 200, 300])

    # Add signature field to catalog
    sig_field = DictionaryObject()
    sig_field[NameObject("/FT")] = NameObject("/Sig")
    sig_field[NameObject("/T")] = TextStringObject("Signature1")
    sig_field[NameObject("/V")] = sig_dict

    out_buf = io.BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return out_buf.getvalue(), sig_dict


def create_acroform_with_utf16_and_bytes():
    """Generates an AcroForm PDF where field values contain UTF-16 ByteStringObjects."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "Registration Application")
    form = c.acroForm
    form.textfield(name="applicant_name", tooltip="Name", x=100, y=700, width=200, height=20)
    form.textfield(name="notes", tooltip="Notes", x=100, y=650, width=200, height=20)
    c.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    writer.append(reader)

    # Update field values with UTF-16 BE ByteStringObject
    utf16_val = ByteStringObject("\ufeffJane Doe".encode("utf-16-be"))
    binary_val = ByteStringObject(b"raw\x80bytes\xffvalue")
    writer.update_page_form_field_values(
        writer.pages[0],
        {"applicant_name": utf16_val, "notes": binary_val}
    )

    out_buf = io.BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return out_buf.getvalue()


def test_sanitize_json_value_handles_non_utf8_bytes():
    """Verify that sanitize_json_value safely converts all problematic binary values."""
    # 1. Non-UTF8 bytes with invalid sequence at index 1
    bad_bytes = b"a\x80b"
    sanitized = sanitize_json_value(bad_bytes)
    assert isinstance(sanitized, str)
    # Must be JSON serializable
    json.dumps({"val": sanitized})

    # 2. UTF-16 with BOM
    utf16_bytes = ByteStringObject("\ufeffTest Value".encode("utf-16-be"))
    sanitized_utf16 = sanitize_json_value(utf16_bytes)
    assert sanitized_utf16 == "Test Value"
    json.dumps({"val": sanitized_utf16})

    # 3. PKCS#7 Digital signature dictionary
    sig_dict = DictionaryObject()
    sig_dict[NameObject("/Type")] = NameObject("/Sig")
    sig_dict[NameObject("/Name")] = TextStringObject("DS Test Signer")
    sig_dict[NameObject("/Contents")] = ByteStringObject(b"0\x80\x06\t*binary")
    sanitized_sig = sanitize_json_value(sig_dict)
    assert sanitized_sig == "DS Test Signer"
    json.dumps({"val": sanitized_sig})

    # 4. Nested structures
    nested = {
        "str_field": "hello",
        "bytes_field": ByteStringObject(b"a\xffb"),
        "list_field": [1, 2, ByteStringObject(b"\xfe\xff\x00A\x00B")],
        "none_field": None,
    }
    sanitized_nested = sanitize_json_value(nested)
    assert isinstance(sanitized_nested, dict)
    json_result = json.dumps(sanitized_nested)
    assert "hello" in json_result


def test_form_field_schema_model_dump_json_safety():
    """Verify FormFieldSchema rejects non-UTF8 bytes and always serializes cleanly."""
    field = FormFieldSchema(
        name="test_field",
        label="Test Field",
        type="text",
        extracted_value=ByteStringObject(b"0\x80\x06\t*binary"),
        default_value=ByteStringObject(b"\xfe\xff\x00D\x00e\x00f\x00a\x00u\x00l\x00t"),
    )

    # Must serialize without PydanticSerializationError
    json_str = field.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["name"] == "test_field"
    assert parsed["default_value"] == "Default"


def test_document_extract_response_serialization():
    """Verify DocumentExtractResponse containing signature containers serializes to JSON."""
    sig_dict = DictionaryObject()
    sig_dict[NameObject("/Type")] = NameObject("/Sig")
    sig_dict[NameObject("/Name")] = TextStringObject("Signer Name")
    sig_dict[NameObject("/Contents")] = ByteStringObject(b"0\x80binary")

    field = FormFieldSchema(
        name="signature_field",
        label="Signature Field",
        type="text",
        extracted_value=sig_dict,
    )
    schema = FormSchemaDefinition(
        title="Test Form",
        description="Testing serialization",
        fields=[field],
    )
    resp = DocumentExtractResponse(
        schema_data=schema,
        filename="test.pdf",
        file_path="test_path.pdf",
        detected_fields_count=1,
        has_acroform=False,
        message="Extracted successfully",
        extraction_strategy="digital_text",
        pages_processed=1,
        uncertain_fields_count=0,
    )

    json_str = resp.model_dump_json()
    assert isinstance(json_str, str)
    data = json.loads(json_str)
    assert data["schema_data"]["fields"][0]["extracted_value"] == "Signer Name"


def test_upload_document_endpoint_with_digital_signature_pdf(client):
    """Test POST /api/forms/upload-document with a PDF containing /Sig fields does not return HTTP 500."""
    pdf_bytes, _ = create_pdf_with_digital_signature()

    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("invoice_signed.pdf", pdf_bytes, "application/pdf")},
    )

    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
    data = res.json()
    assert "schema_data" in data
    assert data["filename"] == "invoice_signed.pdf"
    assert data["detected_fields_count"] > 0
    # Must contain no raw un-encoded bytes
    json.dumps(data)


def test_upload_document_endpoint_with_acroform_utf16(client):
    """Test POST /api/forms/upload-document with AcroForm containing UTF-16 values."""
    pdf_bytes = create_acroform_with_utf16_and_bytes()

    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("acro_utf16.pdf", pdf_bytes, "application/pdf")},
    )

    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
    data = res.json()
    assert "schema_data" in data
    assert data["has_acroform"] is True
    assert data["extraction_strategy"] == "acroform"
    json.dumps(data)


def test_upload_document_existing_flipkart_invoice_if_present(client):
    """Test the exact file that originally caused HTTP 500 if present in uploads/."""
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    target_filename = "8ba39537e4cd_OD338423589809271100.pdf"
    target_path = os.path.join(upload_dir, target_filename)

    if not os.path.exists(target_path):
        pytest.skip(f"Test invoice {target_filename} not present in uploads directory")

    with open(target_path, "rb") as f:
        file_bytes = f.read()

    res = client.post(
        "/api/forms/upload-document",
        files={"file": ("OD338423589809271100.pdf", file_bytes, "application/pdf")},
    )

    assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"
    data = res.json()
    assert "schema_data" in data
    assert data["detected_fields_count"] > 0
    # Confirm valid JSON roundtrip without serialization failure
    json_roundtrip = json.dumps(data)
    assert len(json_roundtrip) > 100


def test_guest_draft_cleaned_up_on_submission(client, db_session):
    """Verify that a guest's in-progress draft is deleted when the guest submits the form with session_id."""
    from app.models.form import Form
    from app.models.draft import Draft

    # Create public form
    form = Form(
        title="Guest Draft Test Form",
        description="Testing guest draft deletion",
        is_public=True,
        schema_json={
            "title": "Guest Draft Test Form",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text", "required": True}
            ]
        }
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    # Guest saves a draft
    session_id = "test-guest-session-456"
    save_draft_res = client.post(
        f"/api/forms/{form.id}/draft",
        json={"session_id": session_id, "values_json": {"full_name": "Incomplete Name"}}
    )
    assert save_draft_res.status_code == 200

    # Verify draft exists in database
    existing_draft = db_session.query(Draft).filter(
        Draft.form_id == form.id,
        Draft.session_id == session_id
    ).first()
    assert existing_draft is not None
    assert existing_draft.values_json["full_name"] == "Incomplete Name"

    # Guest submits the form with session_id
    sub_res = client.post(
        f"/api/forms/{form.id}/submissions",
        json={
            "response_json": {"full_name": "Final Valid Name"},
            "session_id": session_id
        }
    )
    assert sub_res.status_code == 201

    # Verify draft is completely removed
    db_session.expire_all()
    remaining_draft = db_session.query(Draft).filter(
        Draft.form_id == form.id,
        Draft.session_id == session_id
    ).first()
    assert remaining_draft is None, "Guest draft was not cleaned up after submission"


def test_preview_pdf_cleaned_up_after_export(client, db_session):
    """Verify export-pdf schedules background cleanup of the temporary preview PDF."""
    from app.models.form import Form
    import glob

    form = Form(
        title="Preview Cleanup Form",
        description="Testing background cleanup",
        is_public=True,
        schema_json={
            "title": "Preview Cleanup Form",
            "fields": [
                {"name": "feedback", "label": "Feedback", "type": "textarea", "required": False}
            ]
        }
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    res = client.post(
        f"/api/forms/{form.id}/export-pdf",
        json={"values": {"feedback": "Everything looks great!"}}
    )
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")

    # In TestClient, BackgroundTasks execute automatically before returning
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    previews = glob.glob(os.path.join(upload_dir, "submission_PREVIEW-*.pdf"))
    assert len(previews) == 0, f"Found lingering preview files on disk: {previews}"
