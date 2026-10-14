import pytest
from app.services.ai_service import extract_json_from_ai_text, generate_demo_form_schema
from app.core.config import settings


def test_ai_malformed_json_extraction():
    # Markdown fenced json
    fenced = '```json\n{"title": "Test Form", "fields": [{"name": "f1", "label": "Field 1", "type": "text"}]}\n```'
    extracted = extract_json_from_ai_text(fenced)
    assert extracted["title"] == "Test Form"

    # Raw json surrounded by conversational text
    messy = 'Here is your schema: {"title": "Conversational Form", "fields": []} Hope you like it!'
    extracted2 = extract_json_from_ai_text(messy)
    assert extracted2["title"] == "Conversational Form"

    # Completely invalid text
    with pytest.raises(ValueError):
        extract_json_from_ai_text("Sorry, I cannot create this form.")


def test_sql_injection_resilience(client):
    # Harmless SQL injection payload
    injection_title = "Form'); DROP TABLE forms;--"
    payload = {
        "title": injection_title,
        "description": "SQL injection test",
        "schema_json": {
            "title": injection_title,
            "fields": [
                {"name": "test_field", "label": "Test Field", "type": "text", "required": False}
            ]
        }
    }
    res = client.post("/api/forms", json=payload)
    assert res.status_code == 201
    form_id = res.json()["id"]

    # Verify database table still exists and data was treated as literal string
    get_res = client.get(f"/api/forms/{form_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == injection_title

    # Other forms can still be listed
    list_res = client.get("/api/forms")
    assert list_res.status_code == 200


def test_no_secret_leak_in_health_or_api(client):
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    data = health_res.json()
    assert "GEMINI_API_KEY" not in data
    assert "api_key" not in data
    if settings.GEMINI_API_KEY:
        assert settings.GEMINI_API_KEY not in str(data)


def test_invalid_and_boundary_requests(client):
    # 1. Non-existent form
    assert client.get("/api/forms/999999").status_code == 404
    assert client.put("/api/forms/999999", json={"title": "new"}).status_code == 404
    assert client.delete("/api/forms/999999").status_code == 404
    assert client.post("/api/forms/999999/submissions", json={"response_json": {}}).status_code == 404
    assert client.get("/api/forms/999999/submissions").status_code == 404
    assert client.post("/api/forms/999999/voice-map", json={"transcript": "hello"}).status_code == 404

    # 2. Invalid schema (empty fields list)
    bad_schema = {
        "title": "Bad Form",
        "schema_json": {
            "title": "Bad Form",
            "fields": []
        }
    }
    assert client.post("/api/forms", json=bad_schema).status_code == 422


def test_demo_mode_archetypes():
    student_schema = generate_demo_form_schema("create student registration form with register number")
    assert "Student" in student_schema.title
    assert any(f.name == "register_number" for f in student_schema.fields)

    feedback_schema = generate_demo_form_schema("customer feedback survey with rating and comments")
    assert any(f.type == "textarea" for f in feedback_schema.fields)

    job_schema = generate_demo_form_schema("job application form for software engineer")
    assert any("experience" in f.name for f in job_schema.fields)
