import io
import pytest
from unittest.mock import patch, MagicMock
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pypdf import PdfWriter, PdfReader

from app.models.form import Form
from app.models.draft import Draft
from app.models.user import User
from app.core.security import get_password_hash, create_access_token


def make_pdf(lines):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    for line in lines:
        c.drawString(100, y, line)
        y -= 25
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def make_encrypted_pdf(lines, password="secretpassword"):
    plain_pdf = make_pdf(lines)
    reader = PdfReader(io.BytesIO(plain_pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


@pytest.fixture
def sample_form(db_session, auth_user):
    schema = {
        "title": "College Admission Form",
        "description": "Standard student enrollment application",
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Email Address", "type": "email", "required": True},
            {"name": "phone_number", "label": "Phone Number", "type": "text", "required": True},
            {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "required": True},
            {
                "name": "department",
                "label": "Department",
                "type": "select",
                "required": True,
                "options": [
                    "Computer Science & Engineering",
                    "Artificial Intelligence & Data Science",
                    "Mechanical Engineering"
                ]
            },
            {"name": "register_number", "label": "Register Number", "type": "text", "required": True},
            {"name": "city", "label": "City", "type": "text", "required": False},
        ]
    }
    form = Form(
        title="College Admission Form",
        description="Standard student enrollment application",
        schema_json=schema,
        user_id=auth_user.id,
        is_public=True,
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)
    return form


@pytest.fixture
def other_user(db_session):
    user = User(
        email="other_user@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Other User",
        role="USER",
        avatar="OU",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_headers(other_user):
    token = create_access_token(other_user.id)
    return {"Authorization": f"Bearer {token}"}


def test_extract_pdf_digital_text_maps_to_form(client, auth_headers, sample_form, db_session, auth_user):
    pdf_bytes = make_pdf([
        "CURRICULUM VITAE",
        "Full Name: Vikramaditya Sharma",
        "Email: vikram.sharma@example.com",
        "Phone: 9876543210",
        "Date of Birth: 1999-05-20",
        "Department: Computer Science & Engineering",
        "City: Bangalore",
    ])

    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["form_id"] == sample_form.id
    assert data["extracted_fields"]["email"] == "vikram.sharma@example.com"
    assert "9876543210" in data["extracted_fields"]["phone_number"]
    assert data["extracted_fields"]["date_of_birth"] == "1999-05-20"
    assert data["extracted_fields"]["department"] == "Computer Science & Engineering"
    assert data["extracted_fields"]["city"] == "Bangalore"

    # register_number was not in the PDF, so it should be listed in missing_required_fields
    assert "register_number" in data["missing_required_fields"]

    # Verify draft persistence in SQLite database
    draft = db_session.query(Draft).filter(
        Draft.form_id == sample_form.id,
        Draft.user_id == auth_user.id
    ).first()
    assert draft is not None
    assert draft.values_json["email"] == "vikram.sharma@example.com"


def test_extract_pdf_unauthenticated_rejected(client, sample_form):
    pdf_bytes = make_pdf(["Name: John Doe", "Email: john@example.com"])
    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 401


def test_extract_pdf_unauthorized_private_form_rejected(client, other_headers, db_session, auth_user):
    # Create private form owned by auth_user
    schema = {"title": "Private Form", "fields": [{"name": "secret", "label": "Secret", "type": "text"}]}
    private_form = Form(
        title="Private Form",
        schema_json=schema,
        user_id=auth_user.id,
        is_public=False,
    )
    db_session.add(private_form)
    db_session.commit()
    db_session.refresh(private_form)

    pdf_bytes = make_pdf(["Secret: mydata"])
    # other_user attempts to extract into private form
    res = client.post(
        f"/api/forms/{private_form.id}/extract-pdf",
        headers=other_headers,
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 403
    assert "permission" in res.json()["detail"].lower()


def test_extract_pdf_encrypted_rejected(client, auth_headers, sample_form):
    enc_pdf = make_encrypted_pdf(["Full Name: Secret User", "Email: secret@example.com"])
    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("locked.pdf", enc_pdf, "application/pdf")},
    )
    assert res.status_code == 400
    assert "encrypted" in res.json()["detail"].lower() or "password" in res.json()["detail"].lower()


def test_extract_pdf_corrupted_rejected(client, auth_headers, sample_form):
    corrupt_bytes = b"%PDF-1.4 header followed by random corrupted data with no xref or trailer"
    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("broken.pdf", corrupt_bytes, "application/pdf")},
    )
    assert res.status_code == 400
    assert "corrupted" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()


def test_extract_pdf_unsupported_extension_rejected(client, auth_headers, sample_form):
    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\nfakeimage", "image/png")},
    )
    assert res.status_code == 400
    assert "unsupported" in res.json()["detail"].lower() or "pdf" in res.json()["detail"].lower()


def test_extract_pdf_empty_file_rejected(client, auth_headers, sample_form):
    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_extract_pdf_blank_content_rejected(client, auth_headers, sample_form):
    # Valid PDF structure with a blank page containing zero text
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.showPage()
    c.save()
    blank_pdf = buf.getvalue()

    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("blank.pdf", blank_pdf, "application/pdf")},
    )
    assert res.status_code == 400
    assert "no readable text" in res.json()["detail"].lower() or "blank" in res.json()["detail"].lower()


def test_extract_pdf_ambiguous_fields_flagged_for_review(client, auth_headers, sample_form):
    pdf_bytes = make_pdf([
        "Contact Document",
        "Full Name: Priya Ramesh",
        "Primary Mobile: 9840112233",
        "Secondary Phone: 9840998877",
        "Email: priya@example.com",
    ])

    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("contact_sheet.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    data = res.json()

    # The phone number field had 2 conflicting phone numbers, so it should be flagged in needs_review
    assert "phone_number" in data["needs_review"]
    assert "multiple" in data["needs_review"]["phone_number"].lower()
    # The non-ambiguous fields should still be populated
    assert data["extracted_fields"]["email"] == "priya@example.com"


def test_extract_pdf_preserves_existing_draft_values(client, auth_headers, sample_form, db_session, auth_user):
    # Pre-populate draft with an already entered value (e.g. register_number)
    pre_draft = Draft(
        form_id=sample_form.id,
        user_id=auth_user.id,
        values_json={"register_number": "REG-2026-999"},
        status="in_progress"
    )
    db_session.add(pre_draft)
    db_session.commit()

    pdf_bytes = make_pdf([
        "Profile",
        "Full Name: Ananya Roy",
        "Email: ananya.roy@example.com",
    ])

    res = client.post(
        f"/api/forms/{sample_form.id}/extract-pdf",
        headers=auth_headers,
        files={"file": ("profile.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    data = res.json()

    # Merged values must contain both previous user input and new extracted fields
    assert data["merged_values"]["register_number"] == "REG-2026-999"
    assert data["merged_values"]["email"] == "ananya.roy@example.com"


def test_export_completed_pdf_independent_of_submission(client, auth_headers, sample_form, db_session):
    values = {
        "full_name": "Arun Kumar",
        "email": "arun.kumar@example.com",
        "phone_number": "9123456780",
        "date_of_birth": "1998-12-01",
        "department": "Mechanical Engineering",
        "register_number": "MECH-44",
        "city": "Chennai",
    }

    res = client.post(
        f"/api/forms/{sample_form.id}/export-pdf",
        headers=auth_headers,
        json={"values": values},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-")
    assert "completed.pdf" in res.headers.get("content-disposition", "")
