from app.models.form import Form
from app.models.submission import Submission


def test_create_and_retrieve_form(db_session):
    test_schema = {
        "title": "Contact Us",
        "description": "Customer inquiry form",
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text", "required": True},
            {"name": "email", "label": "Email Address", "type": "email", "required": True}
        ]
    }
    
    new_form = Form(
        title="Contact Us",
        description="Customer inquiry form",
        schema_json=test_schema
    )
    db_session.add(new_form)
    db_session.commit()
    db_session.refresh(new_form)

    assert new_form.id is not None
    assert new_form.created_at is not None
    assert new_form.updated_at is not None

    # Retrieve from DB
    retrieved = db_session.query(Form).filter(Form.id == new_form.id).first()
    assert retrieved is not None
    assert retrieved.title == "Contact Us"
    assert retrieved.schema_json["fields"][0]["name"] == "full_name"


def test_create_and_retrieve_submission(db_session):
    test_schema = {
        "title": "Feedback Form",
        "fields": [
            {"name": "feedback", "label": "Feedback", "type": "textarea", "required": True}
        ]
    }
    form = Form(title="Feedback Form", schema_json=test_schema)
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    submission_data = {"feedback": "Great voice application!"}
    submission = Submission(form_id=form.id, response_json=submission_data)
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    assert submission.id is not None
    assert submission.form_id == form.id
    assert submission.response_json["feedback"] == "Great voice application!"

    # Test relationship
    assert len(form.submissions) == 1
    assert form.submissions[0].id == submission.id
