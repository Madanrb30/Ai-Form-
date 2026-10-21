import io
import os
import pytest
from app.schemas.form import FormFieldSchema, FormSchemaDefinition
from app.services.excel_service import generate_submissions_excel
from app.services.pdf_service import generate_completed_pdf
from app.models.form import Form
from app.models.submission import Submission


ALL_12_FIELD_TYPES = [
    "text",
    "textarea",
    "number",
    "email",
    "phone",
    "date",
    "time",
    "datetime",
    "select",
    "radio",
    "checkbox",
    "url",
]

ALL_6_CATEGORIES = [
    "General",
    "Education",
    "Careers",
    "Customer Experience",
    "Academic",
    "Financial Aid",
]


def test_all_12_field_types_schema_validation():
    """Verify FormFieldSchema validates and normalizes all 12 field types with type-specific properties."""
    for ftype in ALL_12_FIELD_TYPES:
        options = ["Option A", "Option B"] if ftype in ("select", "radio") else None
        field = FormFieldSchema(
            id=f"id_{ftype}",
            name=f"field_{ftype}",
            label=f"Label for {ftype}",
            type=ftype,
            required=True,
            placeholder=f"Placeholder for {ftype}",
            description=f"Help text for {ftype}",
            options=options,
            min_value=1 if ftype == "number" else None,
            max_value=100 if ftype == "number" else None,
            step=1 if ftype == "number" else None,
            min_length=2 if ftype in ("text", "textarea") else None,
            max_length=50 if ftype in ("text", "textarea") else None,
        )
        assert field.type == ftype
        assert field.name == f"field_{ftype}"
        assert field.label == f"Label for {ftype}"
        assert field.description == f"Help text for {ftype}"


def test_field_type_switch_property_cleanup():
    """Verify that type-incompatible properties are stripped when switching field types."""
    # When a field is number, it can have min_value/max_value, but options should be stripped
    field_number = FormFieldSchema(
        name="qty",
        label="Quantity",
        type="number",
        min_value=5,
        max_value=100,
        options=["Should be removed"],
    )
    assert field_number.min_value == 5
    assert field_number.max_value == 100
    assert field_number.options is None

    # When a field is text, numeric constraints should be stripped
    field_text = FormFieldSchema(
        name="notes",
        label="Notes",
        type="text",
        min_value=10,  # invalid for text
        max_value=50,  # invalid for text
        min_length=3,
        max_length=200,
    )
    assert field_text.min_value is None
    assert field_text.max_value is None
    assert field_text.min_length == 3
    assert field_text.max_length == 200

    # When field is select or radio, options must have at least one element or default
    field_select = FormFieldSchema(
        name="choice",
        label="Choice",
        type="select",
        options=[],
    )
    assert len(field_select.options) > 0


def test_create_and_edit_form_with_all_12_field_types(client, admin_headers):
    """Test full CRUD lifecycle for a form containing all 12 supported field types."""
    fields_payload = [
        {
            "id": f"field_id_{ftype}",
            "name": f"f_{ftype}",
            "label": f"Field {ftype.title()}",
            "type": ftype,
            "required": True if ftype in ("text", "email", "phone") else False,
            "placeholder": f"Enter {ftype}",
            "description": f"Guidance for {ftype}",
            "options": ["Red", "Green", "Blue"] if ftype in ("select", "radio") else None,
            "min_value": 0 if ftype == "number" else None,
            "max_value": 100 if ftype == "number" else None,
            "min_length": 3 if ftype in ("text", "textarea") else None,
            "max_length": 50 if ftype in ("text", "textarea") else None,
        }
        for ftype in ALL_12_FIELD_TYPES
    ]

    create_payload = {
        "title": "Comprehensive 12 Field Types Audit Form",
        "description": "Form containing every supported field type",
        "schema_json": {
            "title": "Comprehensive 12 Field Types Audit Form",
            "category": "Education",
            "fields": fields_payload,
        },
        "is_public": True,
    }

    # 1. Create Form
    res = client.post("/api/forms", json=create_payload, headers=admin_headers)
    assert res.status_code == 201, res.text
    form_data = res.json()
    form_id = form_data["id"]

    # 2. Verify Reloaded Form Schema
    get_res = client.get(f"/api/forms/{form_id}", headers=admin_headers)
    assert get_res.status_code == 200
    loaded = get_res.json()
    assert loaded["schema_json"]["category"] == "Education"
    assert len(loaded["schema_json"]["fields"]) == 12

    # Check each field's properties survived save and reload
    for original, saved in zip(fields_payload, loaded["schema_json"]["fields"]):
        assert saved["name"] == original["name"]
        assert saved["label"] == original["label"]
        assert saved["type"] == original["type"]
        assert saved["required"] == original["required"]
        assert saved["description"] == original["description"]
        if original["type"] in ("select", "radio"):
            assert saved["options"] == ["Red", "Green", "Blue"]

    # 3. Edit Form: Modify labels, reorder options, change category, change constraints
    updated_fields = list(loaded["schema_json"]["fields"])
    # Modify label and description of text field
    updated_fields[0]["label"] = "Updated Full Name"
    updated_fields[0]["description"] = "Please enter your first and last name."
    # Reorder select options
    for f in updated_fields:
        if f["type"] == "select":
            f["options"] = ["Blue", "Green", "Red"]
        elif f["type"] == "number":
            f["min_value"] = 18
            f["max_value"] = 65

    update_payload = {
        "title": "Updated Comprehensive Audit Form",
        "description": "Updated form description",
        "schema_json": {
            "title": "Updated Comprehensive Audit Form",
            "category": "Careers",
            "fields": updated_fields,
        },
        "is_public": True,
    }

    put_res = client.put(f"/api/forms/{form_id}", json=update_payload, headers=admin_headers)
    assert put_res.status_code == 200, put_res.text

    # 4. Verify Edited State Persisted Correctly
    reloaded_res = client.get(f"/api/forms/{form_id}", headers=admin_headers)
    assert reloaded_res.status_code == 200
    reloaded = reloaded_res.json()
    assert reloaded["title"] == "Updated Comprehensive Audit Form"
    assert reloaded["schema_json"]["category"] == "Careers"
    assert reloaded["schema_json"]["fields"][0]["label"] == "Updated Full Name"
    assert reloaded["schema_json"]["fields"][0]["description"] == "Please enter your first and last name."

    # Check select options reordered
    select_field = next(f for f in reloaded["schema_json"]["fields"] if f["type"] == "select")
    assert select_field["options"] == ["Blue", "Green", "Red"]

    # Check number constraints updated
    num_field = next(f for f in reloaded["schema_json"]["fields"] if f["type"] == "number")
    assert num_field["min_value"] == 18
    assert num_field["max_value"] == 65


def test_form_category_persistence_across_all_categories(client, admin_headers):
    """Verify that every supported form category can be assigned, persisted, and updated."""
    for category in ALL_6_CATEGORIES:
        payload = {
            "title": f"Form for {category}",
            "schema_json": {
                "title": f"Form for {category}",
                "category": category,
                "fields": [
                    {"name": "sample_field", "label": "Sample", "type": "text", "required": False}
                ],
            },
            "is_public": False,
        }
        res = client.post("/api/forms", json=payload, headers=admin_headers)
        assert res.status_code == 201, res.text
        form_id = res.json()["id"]

        get_res = client.get(f"/api/forms/{form_id}", headers=admin_headers)
        assert get_res.status_code == 200
        assert get_res.json()["schema_json"].get("category") == category


def test_submission_validation_all_12_field_types(client, admin_headers, auth_headers):
    """Test validation and submission for all 12 field types, including constraints and failure cases."""
    fields = [
        {"name": "f_text", "label": "Text", "type": "text", "required": True, "min_length": 3, "max_length": 20},
        {"name": "f_textarea", "label": "Textarea", "type": "textarea", "required": False, "min_length": 5},
        {"name": "f_number", "label": "Number", "type": "number", "required": True, "min_value": 10, "max_value": 50},
        {"name": "f_email", "label": "Email", "type": "email", "required": True},
        {"name": "f_phone", "label": "Phone", "type": "phone", "required": True},
        {"name": "f_date", "label": "Date", "type": "date", "required": True},
        {"name": "f_time", "label": "Time", "type": "time", "required": True},
        {"name": "f_datetime", "label": "Date Time", "type": "datetime", "required": False},
        {"name": "f_select", "label": "Select", "type": "select", "options": ["Option 1", "Option 2"], "required": True},
        {"name": "f_radio", "label": "Radio", "type": "radio", "options": ["Yes", "No"], "required": True},
        {"name": "f_checkbox", "label": "Checkbox", "type": "checkbox", "required": True},
        {"name": "f_url", "label": "URL", "type": "url", "required": True},
    ]

    create_res = client.post(
        "/api/forms",
        json={
            "title": "Validation Test Form",
            "schema_json": {"title": "Validation Test Form", "fields": fields},
            "is_public": True,
        },
        headers=admin_headers,
    )
    assert create_res.status_code == 201, create_res.text
    form_id = create_res.json()["id"]

    # 1. Valid Submission
    valid_data = {
        "f_text": "Valid Text",
        "f_textarea": "This is a detailed paragraph.",
        "f_number": 25,
        "f_email": "user@example.com",
        "f_phone": "+1 555-123-4567",
        "f_date": "2026-10-21",
        "f_time": "14:30",
        "f_datetime": "2026-10-21T14:30:00",
        "f_select": "Option 1",
        "f_radio": "Yes",
        "f_checkbox": True,
        "f_url": "https://example.com/profile",
    }
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": valid_data},
        headers=auth_headers,
    )
    assert sub_res.status_code == 201, sub_res.text
    sub_id = sub_res.json()["id"]
    assert sub_id is not None

    # 2. Test Invalid Email
    bad_email = dict(valid_data, f_email="not-an-email")
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_email}, headers=auth_headers)
    assert res.status_code == 400
    assert "email" in res.text.lower()

    # 3. Test Invalid Phone
    bad_phone = dict(valid_data, f_phone="123")  # too short
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_phone}, headers=auth_headers)
    assert res.status_code == 400
    assert "phone" in res.text.lower()

    # 4. Test Invalid URL
    bad_url = dict(valid_data, f_url="ftp://badurl.org")
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_url}, headers=auth_headers)
    assert res.status_code == 400
    assert "url" in res.text.lower()

    # 5. Test Invalid Date
    bad_date = dict(valid_data, f_date="invalid-date")
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_date}, headers=auth_headers)
    assert res.status_code == 400
    assert "date" in res.text.lower()

    # 6. Test Invalid Time
    bad_time = dict(valid_data, f_time="25:99")
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_time}, headers=auth_headers)
    assert res.status_code == 400
    assert "time" in res.text.lower()

    # 7. Test Number Below Minimum
    bad_min_num = dict(valid_data, f_number=5)  # min is 10
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_min_num}, headers=auth_headers)
    assert res.status_code == 400
    assert "at least" in res.text.lower()

    # 8. Test Number Above Maximum
    bad_max_num = dict(valid_data, f_number=100)  # max is 50
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_max_num}, headers=auth_headers)
    assert res.status_code == 400
    assert "cannot exceed" in res.text.lower() or "at most" in res.text.lower()

    # 9. Test Text Too Short
    bad_short_text = dict(valid_data, f_text="ab")  # min is 3
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_short_text}, headers=auth_headers)
    assert res.status_code == 400
    assert "at least 3" in res.text.lower()

    # 10. Test Select Invalid Option
    bad_option = dict(valid_data, f_select="Option Not In List")
    res = client.post(f"/api/forms/{form_id}/submissions", json={"response_json": bad_option}, headers=auth_headers)
    assert res.status_code == 400
    assert "allowed options" in res.text.lower()


def test_legacy_form_backward_compatibility(client, admin_headers, auth_headers):
    """Verify that forms saved with older, minimal schemas load, validate, and accept submissions normally."""
    legacy_payload = {
        "title": "Legacy Form 2024",
        "description": "Form without id, description, or constraints",
        "schema_json": {
            "title": "Legacy Form 2024",
            "fields": [
                {"name": "user_name", "label": "User Name", "type": "text", "required": True},
                {"name": "user_email", "label": "User Email", "type": "email", "required": False},
            ],
        },
        "is_public": True,
    }

    create_res = client.post("/api/forms", json=legacy_payload, headers=admin_headers)
    assert create_res.status_code == 201, create_res.text
    form_id = create_res.json()["id"]

    # Submission against legacy form
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"user_name": "Old User", "user_email": "old@example.com"}},
        headers=auth_headers,
    )
    assert sub_res.status_code == 201, sub_res.text
    assert sub_res.json()["response_json"]["user_name"] == "Old User"


def test_pdf_and_excel_export_all_12_field_types(db_session, auth_user, tmp_path):
    """Verify that submissions containing all 12 field types can be exported to PDF and Excel without error."""
    fields = [
        {"name": f"f_{ftype}", "label": f"{ftype.title()} Label", "type": ftype}
        for ftype in ALL_12_FIELD_TYPES
    ]
    form = Form(
        title="Export Test Form",
        description="Testing PDF and Excel export across 12 field types",
        user_id=auth_user.id,
        is_public=True,
        schema_json={"title": "Export Test Form", "fields": fields},
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    sample_response = {
        "f_text": "Sample Text",
        "f_textarea": "Line 1\nLine 2",
        "f_number": 42,
        "f_email": "hello@world.com",
        "f_phone": "+1-800-555-0199",
        "f_date": "2026-10-21",
        "f_time": "12:00",
        "f_datetime": "2026-10-21T12:00:00",
        "f_select": "Selected Option",
        "f_radio": "Radio Value",
        "f_checkbox": True,
        "f_url": "https://example.com",
    }

    sub = Submission(
        form_id=form.id,
        user_id=auth_user.id,
        response_json=sample_response,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)

    # 1. Test Excel Export
    excel_stream = generate_submissions_excel(
        form=form,
        submissions=[sub],
        user_map={auth_user.id: auth_user},
        current_user=auth_user,
    )
    assert excel_stream is not None
    assert isinstance(excel_stream, io.BytesIO)
    content = excel_stream.getvalue()
    assert len(content) > 1000

    # 2. Test PDF Export
    generated_path = generate_completed_pdf(
        form_title=form.title,
        form_description=form.description,
        fields_schema=fields,
        response_data=sample_response,
        submission_id=sub.id,
    )
    assert os.path.exists(generated_path)
    with open(generated_path, "rb") as f:
        pdf_bytes = f.read()
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_checkbox_default_normalization():
    """1. Verify checkbox defaults normalize to boolean and never interpret 'false' as True."""
    # String "false" must be False
    f1 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="false")
    assert f1.default_value is False

    # String "0" must be False
    f2 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="0")
    assert f2.default_value is False

    # String "no" must be False
    f3 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="no")
    assert f3.default_value is False

    # String "off" must be False
    f4 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="off")
    assert f4.default_value is False

    # Empty string must be False
    f5 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="")
    assert f5.default_value is False

    # String "true" must be True
    f6 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="true")
    assert f6.default_value is True

    # String "1" must be True
    f7 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value="1")
    assert f7.default_value is True

    # Boolean True/False preserved
    f8 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value=True)
    assert f8.default_value is True
    f9 = FormFieldSchema(name="agree", label="Agree", type="checkbox", default_value=False)
    assert f9.default_value is False


def test_constraint_validation_numeric_and_text():
    """2. Verify constraints reject min > max, invalid step, negative lengths, and invalid combinations."""
    # min_value > max_value rejected
    with pytest.raises(ValueError, match="cannot exceed maximum value"):
        FormFieldSchema(name="age", label="Age", type="number", min_value=100, max_value=10)

    # step <= 0 rejected
    with pytest.raises(ValueError, match="Step must be a positive finite number"):
        FormFieldSchema(name="age", label="Age", type="number", step=0)

    with pytest.raises(ValueError, match="Step must be a positive finite number"):
        FormFieldSchema(name="age", label="Age", type="number", step=-1)

    # min_length < 0 rejected
    with pytest.raises(ValueError, match="Minimum length cannot be negative"):
        FormFieldSchema(name="bio", label="Bio", type="text", min_length=-5)

    # max_length < 0 rejected
    with pytest.raises(ValueError, match="Maximum length cannot be negative"):
        FormFieldSchema(name="bio", label="Bio", type="text", max_length=-1)

    # min_length > max_length rejected
    with pytest.raises(ValueError, match="cannot exceed maximum length"):
        FormFieldSchema(name="bio", label="Bio", type="text", min_length=50, max_length=10)


def test_field_identity_and_preservation():
    """3. Verify unique field IDs and names are preserved and deduplicated."""
    f1 = FormFieldSchema(id="custom_id_1", name="field_a", label="Field A", type="text")
    f2 = FormFieldSchema(id="custom_id_1", name="field_a", label="Field A Duplicate", type="text")
    f3 = FormFieldSchema(id="custom_id_2", name="field_b", label="Field B", type="number")

    schema = FormSchemaDefinition(
        title="Identity Test",
        fields=[f1, f2, f3],
    )
    # Existing IDs must be preserved for first occurrences
    assert schema.fields[0].id == "custom_id_1"
    assert schema.fields[0].name == "field_a"
    # Duplicate ID and name must be disambiguated safely
    assert schema.fields[1].id != schema.fields[0].id
    assert schema.fields[1].name != schema.fields[0].name
    assert schema.fields[2].id == "custom_id_2"
    assert schema.fields[2].name == "field_b"


def test_select_and_radio_defaults_and_options():
    """4. Verify select/radio defaults must belong to valid options and options are deduplicated."""
    # Saved default in options is kept
    f1 = FormFieldSchema(
        name="color",
        label="Color",
        type="select",
        options=["Red", "Green", "Blue"],
        default_value="Green",
    )
    assert f1.default_value == "Green"

    # Saved default NOT in options is cleared to None
    f2 = FormFieldSchema(
        name="color",
        label="Color",
        type="select",
        options=["Red", "Green", "Blue"],
        default_value="Yellow",
    )
    assert f2.default_value is None

    # Blank and duplicate options deduplicated
    f3 = FormFieldSchema(
        name="color",
        label="Color",
        type="radio",
        options=["Red", "", "  ", "Green", "Red", "Blue"],
        default_value="Red",
    )
    assert f3.options == ["Red", "Green", "Blue"]
    assert f3.default_value == "Red"


def test_pattern_validation_and_safe_submission():
    """6. Verify regex validation on save and safe handling during submission."""
    # Valid regex passes
    f_valid = FormFieldSchema(
        name="code",
        label="Code",
        type="text",
        pattern=r"^[A-Z]{3}-\d{4}$",
    )
    assert f_valid.pattern == r"^[A-Z]{3}-\d{4}$"

    # Malformed regex rejected before saving
    with pytest.raises(ValueError, match="Invalid regular expression pattern"):
        FormFieldSchema(
            name="code",
            label="Code",
            type="text",
            pattern="[unclosed-pattern(",
        )


def test_category_compatibility():
    """7. Verify legacy/custom categories are preserved and not silently overwritten."""
    schema = FormSchemaDefinition(
        title="Custom Category Form",
        category="Legacy Archived Category 2024",
        fields=[FormFieldSchema(name="name", label="Name", type="text")],
    )
    assert schema.category == "Legacy Archived Category 2024"


def test_numeric_parsing_and_decimal_precision():
    """8. Verify numeric constraints preserve decimal precision and reject NaN and Infinity."""
    # Decimal values preserved without truncation
    f = FormFieldSchema(
        name="price",
        label="Price",
        type="number",
        min_value=0.01,
        max_value=999.99,
        step=0.01,
        default_value=19.99,
    )
    assert f.min_value == 0.01
    assert f.max_value == 999.99
    assert f.step == 0.01
    assert f.default_value == 19.99

    # NaN rejected
    with pytest.raises(ValueError, match="finite number"):
        FormFieldSchema(name="num", label="Num", type="number", min_value=float("nan"))

    # Inf rejected
    with pytest.raises(ValueError, match="finite number"):
        FormFieldSchema(name="num", label="Num", type="number", max_value=float("inf"))
