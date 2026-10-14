import os
import re
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models.form import Form
from app.models.submission import Submission
from app.models.draft import Draft
from app.models.user import User
from app.api.deps import get_current_user_optional
from app.schemas.form import (
    FormGenerateRequest,
    FormGenerateResponse,
    FormCreate,
    FormUpdate,
    FormResponse,
    VoiceMapRequest,
    VoiceMapResponse,
    ConversationTurnRequest,
    ConversationTurnResponse,
    DraftSaveRequest,
    DraftResponse,
    DocumentExtractResponse,
    is_identifier_field,
)
from app.schemas.submission import (
    SubmissionCreate,
    SubmissionResponse,
)
from app.services.ai_service import generate_form_schema, generate_demo_form_schema
from app.services.voice_mapping import map_transcript_to_fields
from app.services.conversation_service import conversation_manager
from app.services.pdf_service import extract_pdf_content, generate_completed_pdf, process_document_hybrid
from app.services.ai_provider import ai_provider, AIProviderError
from app.core.logging import logger

router = APIRouter(prefix="/forms", tags=["Forms"])


@router.post("/generate", response_model=FormGenerateResponse)
def generate_form(request: FormGenerateRequest):
    """
    Generate a dynamic form schema from a natural-language description.
    Uses Groq AI (or offline Demo Mode when key is unconfigured).
    """
    if not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt cannot be empty"
        )

    schema_data, is_demo, provider, message = generate_form_schema(request.prompt)
    return FormGenerateResponse(
        schema_data=schema_data,
        is_demo=is_demo,
        provider=provider,
        message=message,
    )


@router.post("/upload-document", response_model=DocumentExtractResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Upload an existing PDF or image document, extract its text/fields,
    and synthesize an editable form schema using AI.
    """
    filename = file.filename or "uploaded_document.pdf"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in [".pdf", ".png", ".jpg", ".jpeg", ".txt"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a PDF, PNG, JPG/JPEG, or TXT document."
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB."
        )

    # Save to disk
    unique_name = f"{uuid.uuid4().hex[:12]}_{filename}"
    save_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    with open(save_path, "wb") as f_out:
        f_out.write(file_bytes)

    # Process document via hybrid extraction strategy
    try:
        schema_data, strategy, msg, pages_proc, uncertain_count = process_document_hybrid(
            file_bytes=file_bytes,
            filename=filename,
            ext=ext
        )
    except AIProviderError as e:
        logger.error(f"AI provider error during document extraction: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        logger.warning(f"Validation error in document processing: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected document extraction failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document extraction failed: {str(e)}"
        )

    return DocumentExtractResponse(
        schema_data=schema_data,
        filename=filename,
        file_path=save_path,
        detected_fields_count=len(schema_data.fields),
        has_acroform=(strategy == "acroform"),
        message=msg,
        extraction_strategy=strategy,
        pages_processed=pages_proc,
        uncertain_fields_count=uncertain_count,
    )


@router.post("", response_model=FormResponse, status_code=status.HTTP_201_CREATED)
def create_form(
    form_in: FormCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Persist a new form and its schema into the SQLite database.
    """
    new_form = Form(
        title=form_in.title.strip(),
        description=form_in.description.strip() if form_in.description else None,
        schema_json=form_in.schema_json.model_dump(),
        user_id=current_user.id if current_user else None,
    )
    db.add(new_form)
    db.commit()
    db.refresh(new_form)
    logger.info(f"Form created with ID: {new_form.id}")
    return new_form


@router.get("", response_model=List[FormResponse])
def list_forms(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve all saved forms sorted by newest first.
    """
    forms = db.query(Form).order_by(Form.created_at.desc()).all()
    return forms


@router.get("/{form_id}", response_model=FormResponse)
def get_form(form_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a specific form by its ID.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )
    return form


@router.put("/{form_id}", response_model=FormResponse)
def update_form(
    form_id: int,
    form_in: FormUpdate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Update title, description, or schema of an existing form.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    # Enforce ownership if form is assigned to a user
    if form.user_id is not None:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to modify this form."
            )
        if form.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this form."
            )

    if form_in.title is not None:
        form.title = form_in.title.strip()
    if form_in.description is not None:
        form.description = form_in.description.strip()
    if form_in.schema_json is not None:
        form.schema_json = form_in.schema_json.model_dump()

    db.commit()
    db.refresh(form)
    logger.info(f"Form {form_id} updated successfully")
    return form


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Delete a form and all associated submissions (cascaded).
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if form.user_id is not None:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to delete this form."
            )
        if form.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this form."
            )

    db.delete(form)
    db.commit()
    logger.info(f"Form {form_id} and associated submissions deleted")
    return None


@router.post("/{form_id}/conversation", response_model=ConversationTurnResponse)
def process_conversation_turn(
    form_id: int,
    req: ConversationTurnRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Stateful conversational form-filling assistant.
    Tracks session state, detects missing required fields, handles natural language corrections,
    and returns conversational follow-up questions.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    session = conversation_manager.get_or_create_session(
        db=db,
        form_id=form_id,
        session_id=req.session_id,
        user_id=current_user.id if current_user else None,
    )

    result = conversation_manager.process_turn(
        db=db,
        form=form,
        session=session,
        transcript=req.transcript,
        client_values=req.current_values,
    )
    return ConversationTurnResponse(**result)


@router.get("/{form_id}/draft", response_model=Optional[DraftResponse])
def get_form_draft(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve server-side saved draft for this form and user.
    """
    query = db.query(Draft).filter(Draft.form_id == form_id)
    if current_user:
        draft = query.filter(Draft.user_id == current_user.id).first()
    else:
        # Unauthenticated users can only access anonymous drafts
        draft = query.filter(Draft.user_id.is_(None)).order_by(Draft.updated_at.desc()).first()

    return draft


@router.post("/{form_id}/draft", response_model=DraftResponse)
def save_form_draft(
    form_id: int,
    req: DraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Server-side debounced autosave draft endpoint.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    query = db.query(Draft).filter(Draft.form_id == form_id)
    if current_user:
        draft = query.filter(Draft.user_id == current_user.id).first()
    else:
        draft = query.filter(Draft.user_id.is_(None)).first()

    if draft:
        draft.values_json = req.values_json
    else:
        draft = Draft(
            form_id=form_id,
            user_id=current_user.id if current_user else None,
            values_json=req.values_json,
            status="in_progress",
        )
        db.add(draft)

    db.commit()
    db.refresh(draft)
    return draft


@router.delete("/{form_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def delete_form_draft(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Clear draft once form is submitted or discarded.
    """
    query = db.query(Draft).filter(Draft.form_id == form_id)
    if current_user:
        drafts = query.filter(Draft.user_id == current_user.id).all()
    else:
        drafts = query.filter(Draft.user_id.is_(None)).all()

    for d in drafts:
        db.delete(d)
    db.commit()
    return None


@router.post("/{form_id}/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def create_submission(
    form_id: int,
    sub_in: SubmissionCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Submit a filled form response with server-side validation against the form's schema.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    schema = form.schema_json
    fields = schema.get("fields", [])
    user_data = sub_in.response_json
    validation_errors = []

    for field in fields:
        fname = field.get("name")
        flabel = field.get("label", fname)
        ftype = field.get("type", "text")
        required = field.get("required", False)
        val = user_data.get(fname)

        # Check required
        if required:
            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
                validation_errors.append(f"'{flabel}' is required.")
                continue

        # Type validations if value present
        if val is not None and str(val).strip():
            if ftype == "number" and not is_identifier_field(field):
                try:
                    float(val)
                except ValueError:
                    validation_errors.append(f"'{flabel}' must be a valid number.")
            elif ftype == "email":
                if "@" not in str(val) or "." not in str(val):
                    validation_errors.append(f"'{flabel}' must be a valid email address.")
            elif ftype in ("select", "radio"):
                options = field.get("options") or []
                if options and str(val) not in options:
                    validation_errors.append(f"'{flabel}' must be one of the allowed options: {', '.join(options)}.")

    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Form validation failed", "errors": validation_errors}
        )

    new_sub = Submission(
        form_id=form_id,
        user_id=current_user.id if current_user else None,
        response_json=user_data,
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)

    # Automatically generate completed PDF document in background
    try:
        pdf_path = generate_completed_pdf(
            form_title=form.title,
            form_description=form.description,
            fields_schema=fields,
            response_data=user_data,
            submission_id=new_sub.id,
            original_pdf_path=form.original_document_path,
        )
        new_sub.generated_pdf_path = pdf_path
        db.commit()
    except Exception as e:
        logger.warning(f"Could not generate PDF for submission {new_sub.id}: {e}")

    # Remove draft upon successful submission
    try:
        drafts = db.query(Draft).filter(Draft.form_id == form_id).all()
        for d in drafts:
            db.delete(d)
        db.commit()
    except Exception:
        pass

    logger.info(f"Submission {new_sub.id} created for form {form_id}")
    return new_sub


@router.get("/{form_id}/submissions", response_model=List[SubmissionResponse])
def get_form_submissions(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve all submissions for a specific form.
    Only form creator or submission authors can view submissions on user-owned forms.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    # If the form is owned by a specific user:
    if form.user_id is not None:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to view this form's submissions."
            )
        if current_user.id != form.user_id:
            # Other authenticated users only see their own submissions
            submissions = (
                db.query(Submission)
                .filter(Submission.form_id == form_id, Submission.user_id == current_user.id)
                .order_by(Submission.created_at.desc())
                .all()
            )
            return submissions

    submissions = (
        db.query(Submission)
        .filter(Submission.form_id == form_id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    return submissions


@router.get("/{form_id}/submissions/{sub_id}/pdf")
def download_submission_pdf(
    form_id: int,
    sub_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Download publication-ready completed PDF for this submission.
    """
    submission = db.query(Submission).filter(Submission.id == sub_id, Submission.form_id == form_id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {sub_id} not found"
        )

    form = db.query(Form).filter(Form.id == form_id).first()

    # Enforce authorization if form or submission is tied to a user
    if (form and form.user_id is not None) or (submission.user_id is not None):
        is_owner = current_user and form and (current_user.id == form.user_id)
        is_author = current_user and (submission.user_id is not None) and (current_user.id == submission.user_id)
        if not is_owner and not is_author:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to download this submission PDF."
            )

    pdf_path = submission.generated_pdf_path

    if not pdf_path or not os.path.exists(pdf_path):
        pdf_path = generate_completed_pdf(
            form_title=form.title if form else "Form Submission",
            form_description=form.description if form else None,
            fields_schema=form.schema_json.get("fields", []) if form else [],
            response_data=submission.response_json,
            submission_id=submission.id,
        )
        submission.generated_pdf_path = pdf_path
        db.commit()

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", form.title if form else "submission")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{safe_title}_submission_{sub_id}.pdf"
    )


@router.post("/{form_id}/voice-map", response_model=VoiceMapResponse)
def voice_map_fields(form_id: int, req: VoiceMapRequest, db: Session = Depends(get_db)):
    """
    Deterministic rule-based slot-filling voice mapping.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    schema = form.schema_json
    mapped = map_transcript_to_fields(req.transcript, schema)
    total_fields = len(schema.get("fields", []))

    return VoiceMapResponse(
        mapped_fields=mapped,
        transcript=req.transcript,
        total_fields=total_fields,
        matched_count=len(mapped),
    )
