import pytest


def test_generate_form_demo_mode(client):
    response = client.post(
        "/api/forms/generate",
        json={"prompt": "Create a student registration form containing full name, email address, department, and phone number"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_demo"] is True
    assert "schema_data" in data
    schema = data["schema_data"]
    assert "title" in schema
    assert len(schema["fields"]) >= 4
    
    # Check field names
    field_names = [f["name"] for f in schema["fields"]]
    assert "full_name" in field_names
    assert "email" in field_names or "email_address" in field_names


def test_generate_form_empty_prompt(client):
    response = client.post("/api/forms/generate", json={"prompt": "   "})
    assert response.status_code in (400, 422)


def test_anonymous_form_creation_rejected(client):
    payload = {
        "title": "Anonymous Attempt",
        "schema_json": {
            "title": "Anonymous Attempt",
            "fields": [{"name": "field1", "label": "Field 1", "type": "text"}]
        }
    }
    # Unauthenticated persistent form creation must be rejected
    res = client.post("/api/forms", json=payload)
    assert res.status_code == 401


def test_form_crud_lifecycle(client, auth_headers):
    # 1. Create Form (Authenticated)
    payload = {
        "title": "Job Application Form",
        "description": "Candidate application details",
        "schema_json": {
            "title": "Job Application",
            "description": "Candidate application details",
            "fields": [
                {
                    "name": "full_name",
                    "label": "Full Name",
                    "type": "text",
                    "required": True,
                    "placeholder": "Your full name"
                },
                {
                    "name": "email",
                    "label": "Email Address",
                    "type": "email",
                    "required": True,
                    "placeholder": "your.email@example.com"
                },
                {
                    "name": "years_exp",
                    "label": "Years of Experience",
                    "type": "number",
                    "required": False,
                    "placeholder": "5"
                }
            ]
        }
    }
    create_res = client.post("/api/forms", json=payload, headers=auth_headers)
    assert create_res.status_code == 201
    form_data = create_res.json()
    form_id = form_data["id"]
    assert form_data["title"] == "Job Application Form"
    assert len(form_data["schema_json"]["fields"]) == 3

    # 2. List Forms (Authenticated sees own created form)
    list_res = client.get("/api/forms", headers=auth_headers)
    assert list_res.status_code == 200
    forms = list_res.json()
    assert any(f["id"] == form_id for f in forms)

    # 3. Get Form by ID
    get_res = client.get(f"/api/forms/{form_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == form_id

    # 4. Update Form (Owner)
    update_res = client.put(
        f"/api/forms/{form_id}",
        json={"title": "Updated Job Application Form"},
        headers=auth_headers
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Updated Job Application Form"

    # 5. Non-existent form
    missing_res = client.get("/api/forms/99999", headers=auth_headers)
    assert missing_res.status_code == 404

    # 6. Delete Form (Owner)
    del_res = client.delete(f"/api/forms/{form_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # Confirm deleted
    assert client.get(f"/api/forms/{form_id}").status_code == 404


def test_form_submissions_and_validation(client, auth_headers):
    # Setup form (Authenticated creator)
    form_payload = {
        "title": "Contact Us",
        "description": "Customer message form",
        "schema_json": {
            "title": "Contact Us",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                {"name": "email", "label": "Email Address", "type": "email", "required": True},
                {"name": "age", "label": "Age", "type": "number", "required": False}
            ]
        }
    }
    create_form_res = client.post("/api/forms", json=form_payload, headers=auth_headers)
    assert create_form_res.status_code == 201
    form_id = create_form_res.json()["id"]

    # 1. Missing required field
    invalid_sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"email": "test@example.com"}}
    )
    assert invalid_sub_res.status_code == 400
    assert "Full Name" in str(invalid_sub_res.json())

    # 2. Invalid email format
    invalid_email_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "John Doe", "email": "not-an-email"}}
    )
    assert invalid_email_res.status_code == 400
    assert "email address" in str(invalid_email_res.json())

    # 3. Invalid number format
    invalid_num_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "John Doe", "email": "john@example.com", "age": "not_a_number"}}
    )
    assert invalid_num_res.status_code == 400

    # 4. Valid Submission (Guest can submit to public form)
    valid_sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "John Doe", "email": "john@example.com", "age": "28"}}
    )
    assert valid_sub_res.status_code == 201
    sub_data = valid_sub_res.json()
    assert sub_data["form_id"] == form_id
    assert sub_data["response_json"]["full_name"] == "John Doe"

    # 5. Anonymous visitor cannot view submission history
    anon_subs_res = client.get(f"/api/forms/{form_id}/submissions")
    assert anon_subs_res.status_code == 401

    # 6. Retrieve Submissions (Authenticated form owner)
    get_subs_res = client.get(f"/api/forms/{form_id}/submissions", headers=auth_headers)
    assert get_subs_res.status_code == 200
    subs = get_subs_res.json()
    assert len(subs) == 1
    assert subs[0]["response_json"]["email"] == "john@example.com"
