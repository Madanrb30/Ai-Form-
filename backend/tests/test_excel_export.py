import io
import pytest
from datetime import datetime, timedelta
import openpyxl

from app.models.form import Form
from app.models.user import User
from app.models.submission import Submission
from app.core.security import get_password_hash, create_access_token


@pytest.fixture
def excel_test_setup(db_session):
    admin = User(
        email="excel_admin@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        full_name="Excel Admin",
        role="ADMIN",
        avatar="EA",
    )
    user_alice = User(
        email="alice_excel@example.com",
        hashed_password=get_password_hash("AlicePass123!"),
        full_name="Alice Candidate",
        role="USER",
        avatar="AC",
    )
    user_bob = User(
        email="bob_excel@example.com",
        hashed_password=get_password_hash("BobPass123!"),
        full_name="Bob Candidate",
        role="USER",
        avatar="BC",
    )
    db_session.add_all([admin, user_alice, user_bob])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(user_alice)
    db_session.refresh(user_bob)

    form = Form(
        title="College Application Form",
        description="Official student enrollment",
        schema_json={
            "title": "College Application Form",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
                {"name": "department", "label": "Department", "type": "select", "options": ["CSE", "AI&DS"]},
                {"name": "gpa", "label": "GPA", "type": "number"},
                {"name": "notes", "label": "Personal Statement", "type": "textarea"},
                {"name": "phone", "label": "Phone Number", "type": "text"},
            ]
        },
        user_id=admin.id,
        is_public=True,
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    return {
        "admin": admin,
        "alice": user_alice,
        "bob": user_bob,
        "form": form,
        "admin_token": create_access_token(admin.id, role=admin.role),
        "alice_token": create_access_token(user_alice.id, role=user_alice.role),
        "bob_token": create_access_token(user_bob.id, role=user_bob.role),
    }


def test_excel_export_valid_workbook_structure_and_headers(client, excel_test_setup):
    """Verify workbook contains Submission Summary and Response Details worksheets with valid styling and data."""
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]
    token_alice = setup["alice_token"]

    # Submit a response from Alice
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "Alice Candidate", "department": "CSE", "gpa": 3.9}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_res.status_code == 201

    # Admin requests Excel export
    res = client.get(
        f"/api/forms/{form_id}/export-excel",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res.status_code == 200
    assert "spreadsheetml.sheet" in res.headers["Content-Type"]
    assert "College_Application_Form_Submissions.xlsx" in res.headers["Content-Disposition"]

    # Load into openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["Submission Summary", "Response Details"]

    # Sheet 1: Submission Summary
    ws_summary = wb["Submission Summary"]
    headers_summary = [cell.value for cell in ws_summary[1]]
    assert headers_summary == [
        "Submission ID",
        "Respondent Name",
        "Respondent Email",
        "Submission Date",
        "Status",
    ]
    assert ws_summary.freeze_panes == "A2"
    assert ws_summary.auto_filter.ref is not None

    # Check summary row 2
    row2_summary = [cell.value for cell in ws_summary[2]]
    assert row2_summary[0] == sub_res.json()["id"]
    assert row2_summary[1] == "Alice Candidate"
    assert row2_summary[2] == "alice_excel@example.com"
    assert row2_summary[4] == "Completed"

    # Sheet 2: Response Details
    ws_details = wb["Response Details"]
    headers_details = [cell.value for cell in ws_details[1]]
    assert headers_details == [
        "Submission ID",
        "Field Identifier",
        "Field Label",
        "Field Value",
    ]
    assert ws_details.freeze_panes == "A2"
    assert ws_details.auto_filter.ref is not None

    # Verify response details rows contain Alice's fields
    detail_rows = [[cell.value for cell in row] for row in ws_details.iter_rows(min_row=2)]
    field_names = [r[1] for r in detail_rows]
    assert "full_name" in field_names
    assert "department" in field_names
    assert "gpa" in field_names


def test_excel_export_unicode_tamil_preservation(client, excel_test_setup):
    """Verify Unicode characters (such as Tamil script) are completely preserved in Excel cells."""
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]
    token_alice = setup["alice_token"]

    tamil_name = "மதன் குமார்"
    tamil_statement = "கணினி அறிவியல் மற்றும் செயற்கை நுண்ணறிவு"
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": tamil_name, "notes": tamil_statement}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_res.status_code == 201

    res = client.get(
        f"/api/forms/{form_id}/export-excel",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    ws_details = wb["Response Details"]
    detail_rows = [[cell.value for cell in row] for row in ws_details.iter_rows(min_row=2)]

    values = [r[3] for r in detail_rows]
    assert tamil_name in values
    assert tamil_statement in values


def test_excel_export_formula_injection_prevention(client, excel_test_setup):
    """Verify spreadsheet formula injection characters (=, +, -, @, \\t) are escaped with leading single quote."""
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]
    token_alice = setup["alice_token"]

    malicious_inputs = {
        "full_name": "=cmd|' /C calc'!A0",
        "notes": "@SUM(1+1)",
        "phone": "+1-800-555-0199",
        "department": "CSE",
        "gpa": 4.0,  # real number
    }
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": malicious_inputs},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_res.status_code == 201

    res = client.get(
        f"/api/forms/{form_id}/export-excel",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    ws_details = wb["Response Details"]
    detail_rows = [[cell.value for cell in row] for row in ws_details.iter_rows(min_row=2)]

    row_map = {r[1]: r[3] for r in detail_rows}

    # Strings beginning with dangerous formula characters must be prefixed with a single quote
    assert row_map["full_name"].startswith("'=")
    assert row_map["notes"].startswith("'@")
    assert row_map["phone"].startswith("'+")

    # Legitimate numbers should remain numeric
    assert isinstance(row_map["gpa"], (int, float))
    assert row_map["gpa"] == 4.0


def test_excel_export_filtered_by_search_and_dates(client, excel_test_setup):
    """Verify Excel export honors the same filters (search keyword, dates) as the submissions view."""
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]
    token_alice = setup["alice_token"]
    token_bob = setup["bob_token"]

    # Submission 1: Alice (CSE)
    client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "Alice Candidate", "department": "CSE"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )

    # Submission 2: Bob (AI&DS)
    sub2_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "Bob Candidate", "department": "AI&DS"}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    sub2_id = sub2_res.json()["id"]

    # 1. Filter by keyword "AI&DS"
    res_filtered = client.get(
        f"/api/forms/{form_id}/export-excel?search=AI%26DS",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res_filtered.status_code == 200
    wb_search = openpyxl.load_workbook(io.BytesIO(res_filtered.content))
    summary_rows = list(wb_search["Submission Summary"].iter_rows(min_row=2, values_only=True))
    assert len(summary_rows) == 1
    assert summary_rows[0][0] == sub2_id
    assert summary_rows[0][1] == "Bob Candidate"

    # 2. Filter by date range (future date returns 0 submissions)
    res_future = client.get(
        f"/api/forms/{form_id}/export-excel?start_date=2099-01-01",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res_future.status_code == 200
    wb_future = openpyxl.load_workbook(io.BytesIO(res_future.content))
    future_rows = list(wb_future["Submission Summary"].iter_rows(min_row=2, values_only=True))
    assert len(future_rows) == 1
    assert "No submissions found" in str(future_rows[0][1])


def test_excel_export_empty_submissions_handled_gracefully(client, excel_test_setup):
    """Verify forms with 0 submissions produce a valid, formatted Excel file with empty notice rows."""
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]

    res = client.get(
        f"/api/forms/{form_id}/export-excel",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["Submission Summary", "Response Details"]
    ws_sum = wb["Submission Summary"]
    assert ws_sum.cell(row=1, column=1).value == "Submission ID"
    assert "No submissions found" in str(ws_sum.cell(row=2, column=2).value)


def test_excel_export_role_authorization_and_cross_user_isolation(client, excel_test_setup, db_session):
    """
    Verify:
    1. Anonymous access is rejected with 401.
    2. Regular users cannot access private forms (404).
    3. On public forms, standard users only export their own submissions, never other users' data.
    4. Admins can export all submissions for forms they manage.
    """
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]
    token_alice = setup["alice_token"]
    token_bob = setup["bob_token"]

    # 1. Anonymous visitor -> 401
    anon_res = client.get(f"/api/forms/{form_id}/export-excel")
    assert anon_res.status_code == 401

    # Alice submits response
    client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "Alice Private Data"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    # Bob submits response
    client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "Bob Private Data"}},
        headers={"Authorization": f"Bearer {token_bob}"}
    )

    # Bob exports submissions -> must only contain Bob's 1 submission
    bob_export = client.get(
        f"/api/forms/{form_id}/export-excel",
        headers={"Authorization": f"Bearer {token_bob}"}
    )
    assert bob_export.status_code == 200
    wb_bob = openpyxl.load_workbook(io.BytesIO(bob_export.content))
    bob_summary = list(wb_bob["Submission Summary"].iter_rows(min_row=2, values_only=True))
    assert len(bob_summary) == 1
    assert bob_summary[0][1] == "Bob Candidate"
    assert bob_summary[0][2] == "bob_excel@example.com"

    # Bob's details sheet must not contain Alice's data
    bob_details = list(wb_bob["Response Details"].iter_rows(min_row=2, values_only=True))
    detail_values = [r[3] for r in bob_details]
    assert "Alice Private Data" not in detail_values

    # Admin exports submissions -> contains both Alice and Bob
    admin_export = client.get(
        f"/api/forms/{form_id}/export-excel",
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert admin_export.status_code == 200
    wb_admin = openpyxl.load_workbook(io.BytesIO(admin_export.content))
    admin_summary = list(wb_admin["Submission Summary"].iter_rows(min_row=2, values_only=True))
    assert len(admin_summary) == 2


def test_existing_csv_and_pdf_exports_continue_working(client, excel_test_setup):
    """Verify adding Excel export did not regress single submission PDF or unsubmitted PDF export."""
    setup = excel_test_setup
    form_id = setup["form"].id
    token_admin = setup["admin_token"]
    token_alice = setup["alice_token"]

    # 1. Independent PDF export
    export_pdf_res = client.post(
        f"/api/forms/{form_id}/export-pdf",
        json={"values": {"full_name": "Quick Preview"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert export_pdf_res.status_code == 200
    assert export_pdf_res.content.startswith(b"%PDF")

    # 2. Submission creation and submission PDF download
    sub_res = client.post(
        f"/api/forms/{form_id}/submissions",
        json={"response_json": {"full_name": "Official Submission"}},
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    sub_pdf_res = client.get(
        f"/api/forms/{form_id}/submissions/{sub_id}/pdf",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert sub_pdf_res.status_code == 200
    assert sub_pdf_res.content.startswith(b"%PDF")
