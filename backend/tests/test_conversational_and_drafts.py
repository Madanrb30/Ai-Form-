import pytest
from app.models.form import Form
from app.models.submission import Submission


@pytest.fixture
def sample_form(db_session):
    form = Form(
        title="Job Application",
        description="Standard application form",
        schema_json={
            "title": "Job Application",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                {"name": "email", "label": "Email Address", "type": "email", "required": True},
                {"name": "years_experience", "label": "Years of Experience", "type": "number", "required": False},
                {"name": "cover_letter", "label": "Cover Letter", "type": "textarea", "required": False}
            ]
        }
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)
    return form


def test_conversational_turn_missing_field_detection(client, sample_form):
    # User provides only full name
    payload = {
        "transcript": "My full name is Alice Johnson",
        "current_values": {}
    }
    res = client.post(f"/api/forms/{sample_form.id}/conversation", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "session_id" in data
    assert "updated_values" in data
    assert data["updated_values"].get("full_name") == "Alice Johnson"

    # Should detect that 'Email Address' is still missing
    assert "missing_fields" in data
    assert any("email" in f.lower() for f in data["missing_fields"])
    assert not any("full name" in f.lower() for f in data["missing_fields"])
    assert not data["is_completed"]

    # Assistant response prompts for missing field
    assert len(data["assistant_response"]) > 0


def test_conversational_turn_correction_and_completion(client, sample_form):
    # Step 1: User fills full name and email
    res1 = client.post(f"/api/forms/{sample_form.id}/conversation", json={
        "transcript": "My name is Bob Smith and email is bob@example.com",
        "current_values": {}
    })
    assert res1.status_code == 200
    data1 = res1.json()
    session_id = data1["session_id"]
    assert data1["updated_values"].get("full_name") == "Bob Smith"
    assert data1["updated_values"].get("email") == "bob@example.com"
    assert data1["is_completed"] is True  # both required fields are present

    # Step 2: User corrects name
    res2 = client.post(f"/api/forms/{sample_form.id}/conversation", json={
        "session_id": session_id,
        "transcript": "Actually, change my name to Robert Smith",
        "current_values": data1["updated_values"]
    })
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["updated_values"].get("full_name") == "Robert Smith"
    # email is preserved
    assert data2["updated_values"].get("email") == "bob@example.com"


def test_form_draft_lifecycle(client, sample_form):
    # 1. Draft should initially not exist (200 with null body)
    get_res = client.get(f"/api/forms/{sample_form.id}/draft")
    assert get_res.status_code == 200
    assert get_res.json() is None

    # 2. Save a draft
    draft_data = {
        "full_name": "Carol Danvers",
        "email": "carol@marvel.com",
        "years_experience": 10
    }
    save_res = client.post(f"/api/forms/{sample_form.id}/draft", json={"values_json": draft_data})
    assert save_res.status_code == 200
    saved = save_res.json()
    assert saved["values_json"]["full_name"] == "Carol Danvers"
    assert "updated_at" in saved

    # 3. Retrieve the saved draft
    get_res2 = client.get(f"/api/forms/{sample_form.id}/draft")
    assert get_res2.status_code == 200
    assert get_res2.json()["values_json"]["email"] == "carol@marvel.com"

    # 4. Overwrite draft with updated values
    draft_data["years_experience"] = 12
    client.post(f"/api/forms/{sample_form.id}/draft", json={"values_json": draft_data})
    get_res3 = client.get(f"/api/forms/{sample_form.id}/draft")
    assert get_res3.json()["values_json"]["years_experience"] == 12

    # 5. Delete draft
    del_res = client.delete(f"/api/forms/{sample_form.id}/draft")
    assert del_res.status_code == 204
    # verify it's gone
    assert client.get(f"/api/forms/{sample_form.id}/draft").json() is None


def test_pdf_submission_export(client, sample_form):
    # Create submission
    sub_payload = {
        "response_json": {
            "full_name": "Diana Prince",
            "email": "diana@themyscira.gov",
            "years_experience": 500,
            "cover_letter": "Diplomat and protector."
        }
    }
    sub_res = client.post(f"/api/forms/{sample_form.id}/submissions", json=sub_payload)
    assert sub_res.status_code == 201
    submission_id = sub_res.json()["id"]

    # Request PDF export
    pdf_res = client.get(f"/api/forms/{sample_form.id}/submissions/{submission_id}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in pdf_res.headers.get("content-disposition", "")

    # Check PDF magic bytes (%PDF)
    assert pdf_res.content.startswith(b"%PDF")


def test_conversational_turn_dropdown_and_identifier(client, db_session):
    form = Form(
        title="College Admissions",
        schema_json={
            "title": "College Admissions",
            "fields": [
                {"name": "register_number", "label": "Register Number", "type": "text", "is_identifier": True, "required": True},
                {"name": "department", "label": "Department", "type": "select", "options": ["AI&DS", "CSE", "ECE", "Mechanical"], "required": True},
                {"name": "postal_code", "label": "Postal Code", "type": "text", "is_identifier": True, "required": True},
            ]
        }
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    # Turn 1: User speaks spaced alphanumeric register number
    res1 = client.post(f"/api/forms/{form.id}/conversation", json={
        "transcript": "My register number is A 1 2 3 4 5",
        "current_values": {}
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["updated_values"]["register_number"] == "A12345"
    assert "A12345" in str(data1["updated_values"]["register_number"])
    session_id = data1["session_id"]

    # Turn 2: User provides department with phrase "I belong to AI and Data Science"
    res2 = client.post(f"/api/forms/{form.id}/conversation", json={
        "session_id": session_id,
        "transcript": "I belong to AI and Data Science",
        "current_values": data1["updated_values"]
    })
    assert res2.status_code == 200
    data2 = res2.json()
    # Confirmed previous register_number is preserved
    assert data2["updated_values"]["register_number"] == "A12345"
    # Dropdown is mapped to exact option "AI&DS"
    assert data2["updated_values"]["department"] == "AI&DS"

    # Turn 3: User tries invalid department option
    res3 = client.post(f"/api/forms/{form.id}/conversation", json={
        "session_id": session_id,
        "transcript": "Actually change my department to Biotechnology",
        "current_values": data2["updated_values"]
    })
    assert res3.status_code == 200
    data3 = res3.json()
    # Biotechnology is not stored in updated_values
    assert data3["updated_values"]["department"] != "Biotechnology"
    # Flagged in needs_review with available options
    assert "department" in data3["needs_review"]
    assert "AI&DS" in data3["assistant_response"] or "AI&DS" in data3["needs_review"]["department"]

    # Turn 4: User corrects to valid option "CSE" and supplies postal code with spoken spaces
    res4 = client.post(f"/api/forms/{form.id}/conversation", json={
        "session_id": session_id,
        "transcript": "Change department to CSE and postal code 6 3 6 0 0 1",
        "current_values": data2["updated_values"]
    })
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["updated_values"]["register_number"] == "A12345"
    assert data4["updated_values"]["department"] == "CSE"
    assert data4["updated_values"]["postal_code"] == "636001"
    assert data4["is_completed"] is True

