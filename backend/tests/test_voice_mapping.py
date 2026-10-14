import pytest
from app.services.voice_mapping import (
    map_transcript_to_fields,
    normalize_spoken_identifier,
    match_dropdown_option,
)


def test_alphanumeric_identifier_normalization():
    # 1. Letters followed by digits
    assert normalize_spoken_identifier("A 1 2 3 4 5") == "A12345"
    assert normalize_spoken_identifier("a 12345") == "A12345"
    assert normalize_spoken_identifier("A one two three four five") == "A12345"

    # 2. Digits followed by letters / mixed
    assert normalize_spoken_identifier("23 AD 045") == "23AD045"
    assert normalize_spoken_identifier("2 3 A D 0 4 5") == "23AD045"
    assert normalize_spoken_identifier("AI 2026 001") == "AI2026001"
    assert normalize_spoken_identifier("a i 2 0 2 6 0 0 1") == "AI2026001"

    # 3. Leading zeros preserved (must not be dropped or cast to int)
    assert normalize_spoken_identifier("012345") == "012345"
    assert normalize_spoken_identifier("0 1 2 3 4 5") == "012345"
    assert normalize_spoken_identifier("007") == "007"
    assert normalize_spoken_identifier("double zero seven") == "007"

    # 4. Postal code & Phone number
    assert normalize_spoken_identifier("6 3 6 0 0 1") == "636001"
    assert normalize_spoken_identifier("six three six zero zero one") == "636001"
    assert normalize_spoken_identifier("9 8 7 6 5 4 3 2 1 0") == "9876543210"
    assert normalize_spoken_identifier("nine eight seven six five four three two one zero") == "9876543210"

    # 5. Hyphenated identifiers
    assert normalize_spoken_identifier("REG - 2026 - 001") == "REG-2026-001"


def test_dropdown_matching_deterministic_hierarchy():
    options = ["AI&DS", "CSE", "ECE", "Mechanical"]

    # 1. Exact match
    res, amb = match_dropdown_option("AI&DS", options)
    assert res == "AI&DS" and not amb

    # 2. Case-insensitive match
    res, amb = match_dropdown_option("cse", options)
    assert res == "CSE" and not amb
    res, amb = match_dropdown_option("mechanical", options)
    assert res == "Mechanical" and not amb

    # 3. Unambiguous spoken synonym / acronym
    # Spoken: "I belong to AI and Data Science."
    res, amb = match_dropdown_option("I belong to AI and Data Science.", options)
    assert res == "AI&DS" and not amb

    # Spoken: "My department is CSE."
    res, amb = match_dropdown_option("My department is CSE.", options)
    assert res == "CSE" and not amb

    # Spoken: "Choose Electronics and Communication Engineering."
    res, amb = match_dropdown_option("Choose Electronics and Communication Engineering.", options)
    assert res == "ECE" and not amb

    # Spoken acronym variations: "AI and DS" or "Artificial Intelligence & Data Science"
    res, amb = match_dropdown_option("Artificial Intelligence & Data Science", options)
    assert res == "AI&DS" and not amb

    # 4. Invalid or unavailable option: Never invent, never pick first option
    res, amb = match_dropdown_option("Biotechnology", options)
    assert res is None and not amb

    res, amb = match_dropdown_option("Civil", options)
    assert res is None and not amb

    # 5. Ambiguous speech with multiple matches
    res, amb = match_dropdown_option("Engineering", ["Computer Engineering", "Mechanical Engineering"])
    assert res is None and amb is True

    # 6. Empty / whitespace transcript
    res, amb = match_dropdown_option("", options)
    assert res is None and not amb


def test_voice_mapping_full_form_schema():
    schema = {
        "title": "College Registration Form",
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text"},
            {"name": "register_number", "label": "Register Number", "type": "text", "is_identifier": True},
            {"name": "roll_number", "label": "Roll Number", "type": "text", "is_identifier": True},
            {"name": "postal_code", "label": "Postal Code", "type": "text", "is_identifier": True},
            {"name": "phone_number", "label": "Phone Number", "type": "text", "is_identifier": True},
            {"name": "department", "label": "Department", "type": "select", "options": ["AI&DS", "CSE", "ECE", "Mechanical"]},
            {"name": "email", "label": "Email Address", "type": "email"},
            {"name": "years_experience", "label": "Years of Experience", "type": "number"},
        ]
    }

    transcript = (
        "My name is Madan RB and register number is A 1 2 3 4 5 and roll number is 23 AD 045 "
        "and postal code is 6 3 6 0 0 1 and phone number is 9 8 7 6 5 4 3 2 1 0 "
        "and department is Artificial Intelligence and Data Science and email is madan at test dot com "
        "and years of experience 3"
    )

    mapped = map_transcript_to_fields(transcript, schema)

    # Identifiers must remain exact formatted strings without loss of zeros or letters
    assert mapped["register_number"] == "A12345"
    assert isinstance(mapped["register_number"], str)

    assert mapped["roll_number"] == "23AD045"
    assert isinstance(mapped["roll_number"], str)

    assert mapped["postal_code"] == "636001"
    assert isinstance(mapped["postal_code"], str)

    assert mapped["phone_number"] == "9876543210"
    assert isinstance(mapped["phone_number"], str)

    # Dropdown must be mapped to the exact configured option "AI&DS"
    assert mapped["department"] == "AI&DS"

    # Email and number fields
    assert mapped["email"] == "madan@test.com"
    assert mapped["years_experience"] == "3"


def test_voice_map_invalid_dropdown_not_selected():
    schema = {
        "title": "Registration",
        "fields": [
            {"name": "department", "label": "Department", "type": "select", "options": ["AI&DS", "CSE", "ECE", "Mechanical"]},
        ]
    }

    # Spoken option "Biotechnology" does not exist in options
    transcript = "My department is Biotechnology"
    mapped = map_transcript_to_fields(transcript, schema)

    # Must NOT invent Biotechnology and must NOT default to options[0] ("AI&DS")
    assert "department" not in mapped


def test_voice_map_endpoint_integration(client, auth_headers):
    res = client.post(
        "/api/forms",
        json={
            "title": "Student Registration Form",
            "schema_json": {
                "title": "Student Registration",
                "fields": [
                    {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                    {"name": "register_number", "label": "Register Number", "type": "text", "is_identifier": True, "required": True},
                    {"name": "department", "label": "Department", "type": "select", "options": ["AI&DS", "CSE", "ECE", "Mechanical"], "required": True},
                    {"name": "email", "label": "Email Address", "type": "email", "required": True}
                ]
            }
        },
        headers=auth_headers
    )
    assert res.status_code == 201
    form_id = res.json()["id"]

    # Post transcript with spaced alphanumeric register number and spoken department synonym
    vm_res = client.post(
        f"/api/forms/{form_id}/voice-map",
        json={"transcript": "My name is Madan and register number is A 1 2 3 4 5 and department is Artificial Intelligence and Data Science"}
    )
    assert vm_res.status_code == 200
    data = vm_res.json()
    assert data["matched_count"] >= 3
    assert data["mapped_fields"]["full_name"] == "Madan"
    assert data["mapped_fields"]["register_number"] == "A12345"
    assert data["mapped_fields"]["department"] == "AI&DS"
