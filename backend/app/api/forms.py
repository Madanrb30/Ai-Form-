import os
import re
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models.form import Form
from app.models.submission import Submission
from app.models.draft import Draft
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.api.deps import get_current_user_optional, get_current_user_required
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
from app.services.ai_service import generate_form_schema
from app.services.voice_mapping import map_transcript_to_fields
from app.services.conversation_service import conversation_manager
from app.services.pdf_service import generate_completed_pdf, process_document_hybrid
from app.services.ai_provider import AIProviderError
from app.services.audit_service import record_audit_log
from app.core.logging import logger

router = APIRouter(prefix="/forms", tags=["Forms"])


@router.post("/generate", response_model=FormGenerateResponse)
def generate_form(request: FormGenerateRequest):
    """
    Generate a dynamic form schema from a natural-language description.
    Uses Groq AI (or offline Demo Mode when configured).
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

    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}
    if ext not in allowed_extensions:
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

    # Content signature & MIME validation (magic bytes inspection)
    if ext == ".pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF file structure. File content does not match a valid PDF document."
            )
    elif ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PNG file structure. File content does not match a valid PNG image."
            )
    elif ext in [".jpg", ".jpeg"]:
        if not file_bytes.startswith(b"\xff\xd8"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JPEG file structure. File content does not match a valid JPEG image."
            )
    elif ext == ".txt":
        try:
            file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid text document. File content is not valid UTF-8 text."
            )

    # Sanitize filename and enforce safe storage inside UPLOAD_DIR
    safe_base = os.path.basename(filename)
    safe_slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", safe_base)
    unique_name = f"{uuid.uuid4().hex[:12]}_{safe_slug}"
    save_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    
    real_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    real_save_path = os.path.abspath(save_path)
    if os.path.commonpath([real_upload_dir, real_save_path]) != real_upload_dir:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document storage path.")

    with open(save_path, "wb") as f_out:
        f_out.write(file_bytes)

    # Record persistent document ownership tracking
    try:
        doc_record = UploadedDocument(
            filename=safe_base,
            storage_path=unique_name,
            file_size=len(file_bytes),
            content_type=file.content_type,
            user_id=current_user.id if current_user else None,
        )
        db.add(doc_record)
        db.commit()
    except Exception as db_err:
        logger.warning(f"Could not record uploaded document in database: {db_err}")

    # Process document via hybrid extraction strategy
    try:
        schema_data, strategy, msg, pages_proc, uncertain_count = process_document_hybrid(
            file_bytes=file_bytes,
            filename=safe_slug,
            ext=ext
        )
    except AIProviderError as e:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        logger.error(f"AI provider error during document extraction: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        logger.warning(f"Validation error in document processing: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        logger.error(f"Unexpected document extraction failure: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document extraction failed due to an unexpected internal error. Please try again."
        )

    return DocumentExtractResponse(
        schema_data=schema_data,
        filename=safe_base,
        file_path=unique_name,
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
    current_user: User = Depends(get_current_user_required)
):
    """
    Persist a new form and its schema into the SQLite database.
    Requires authentication. User ID is derived strictly from validated JWT.
    """
    orig_doc = None
    if form_in.original_document_path:
        # Validate that document is contained within UPLOAD_DIR
        clean_doc = os.path.basename(form_in.original_document_path)
        candidate_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, clean_doc))
        real_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
        if os.path.commonpath([real_upload_dir, candidate_path]) == real_upload_dir and os.path.exists(candidate_path):
            orig_doc = candidate_path

    new_form = Form(
        title=form_in.title.strip(),
        description=form_in.description.strip() if form_in.description else None,
        schema_json=form_in.schema_json.model_dump(),
        user_id=current_user.id,
        is_public=form_in.is_public if form_in.is_public is not None else True,
        original_document_path=orig_doc,
    )
    db.add(new_form)
    db.commit()
    db.refresh(new_form)
    logger.info(f"Form created with ID: {new_form.id} by user {current_user.id}")
    return new_form


@router.get("", response_model=List[FormResponse])
def list_forms(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve saved forms. Authenticated users see their own forms plus all public forms;
    unauthenticated visitors see only explicitly public forms.
    Administrators (ADMIN / SUPER_ADMIN) have access to manage all forms.
    """
    if current_user:
        forms = (
            db.query(Form)
            .filter((Form.user_id == current_user.id) | (Form.is_public == True))
            .order_by(Form.created_at.desc())
            .all()
        )
    else:
        forms = (
            db.query(Form)
            .filter(Form.is_public == True)
            .order_by(Form.created_at.desc())
            .all()
        )
    return forms


@router.get("/user/stats")
def get_user_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Returns user-isolated statistics for dashboard cards:
    - total_accessible_forms: forms accessible to user (public + owned)
    - my_forms_count: personal forms created by this user
    - shared_templates_count: public template forms
    - my_submissions_count: completed submissions authored by this user
    - my_drafts_count: in-progress drafts authored by this user
    """
    shared_count = db.query(Form).filter(Form.is_public == True).count()
    if not current_user:
        return {
            "total_accessible_forms": shared_count,
            "my_forms_count": 0,
            "shared_templates_count": shared_count,
            "my_submissions_count": 0,
            "my_drafts_count": 0,
        }

    my_forms = db.query(Form).filter(Form.user_id == current_user.id).count()
    total_forms = (
        db.query(Form)
        .filter((Form.user_id == current_user.id) | (Form.is_public == True))
        .count()
    )

    my_subs = db.query(Submission).filter(Submission.user_id == current_user.id).count()
    my_drafts = db.query(Draft).filter(Draft.user_id == current_user.id).count()

    return {
        "total_accessible_forms": total_forms,
        "my_forms_count": my_forms,
        "shared_templates_count": shared_count,
        "my_submissions_count": my_subs,
        "my_drafts_count": my_drafts,
    }


@router.get("/{form_id}", response_model=FormResponse)
def get_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve a specific form by its ID.
    Enforces privacy: if a form is private (is_public=False), only the owner can view it.
    Unauthenticated users receive 401; unauthorized users receive 403 to enforce strict ownership.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    # Privacy enforcement on private forms
    if not form.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this private form."
            )
        if form.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this private form."
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
    Update title, description, schema, or visibility of an existing form.
    Only the form owner can modify a form. Shared system templates cannot be modified.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to modify this form."
        )

    # Protect unowned shared templates
    if form.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared system templates cannot be modified."
        )

    # Enforce ownership
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
    if form_in.is_public is not None:
        form.is_public = form_in.is_public

    db.commit()
    db.refresh(form)
    logger.info(f"Form {form_id} updated successfully by user {current_user.id}")
    return form


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_form(
    form_id: int,
    confirm_delete_submissions: bool = Query(False, description="Explicit confirmation to delete form along with its submissions"),
    confirm_submissions: bool = Query(False, description="Alternative alias for confirm_delete_submissions"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Delete a form and all associated dependent records (cascaded).
    - SUPER_ADMIN can delete any form (shared templates or user-created forms).
    - Regular users and standard ADMINs can only delete forms they own.
    - If a form has submissions, explicit confirmation (confirm_delete_submissions=true) is required
      to prevent unintentional data loss.
    - Administrative actions are recorded in the immutable audit log.
    - If an error occurs, the database transaction is rolled back.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to delete this form."
        )

    is_super_admin = current_user.role == "SUPER_ADMIN"

    # Non-super-admins cannot delete shared system templates
    if form.user_id is None and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared system templates cannot be deleted."
        )

    # Non-super-admins can only delete forms they own
    if form.user_id is not None and form.user_id != current_user.id and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this form."
        )

    # Check dependent submissions
    subs_count = len(form.submissions) if form.submissions else 0
    confirmed = confirm_delete_submissions or confirm_submissions

    if subs_count > 0 and not confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Form has {subs_count} associated submission(s). Explicit confirmation is required to permanently delete this form and all of its submission records."
        )

    drafts_count = len(form.drafts) if form.drafts else 0

    try:
        # Collect file paths to clean up ONLY after successful database deletion
        pdf_paths_to_clean = []
        if form.submissions:
            for sub in form.submissions:
                if sub.generated_pdf_path:
                    pdf_paths_to_clean.append(sub.generated_pdf_path)

        orig_doc_to_clean = form.original_document_path
        form_title = form.title
        form_owner_id = form.user_id

        # Perform atomic database deletion first
        db.delete(form)
        db.commit()

        # Clean up physical files ONLY after database transaction commits safely
        for pdf_path in pdf_paths_to_clean:
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except OSError as e:
                    logger.warning(f"Could not delete PDF file {pdf_path}: {e}")

        if orig_doc_to_clean and os.path.exists(orig_doc_to_clean):
            try:
                os.remove(orig_doc_to_clean)
            except OSError as e:
                logger.warning(f"Could not delete document file {orig_doc_to_clean}: {e}")

        # Audit administrative or user deletion
        record_audit_log(
            db=db,
            action="FORM_DELETED",
            actor_id=current_user.id,
            actor_email=current_user.email,
            target_type="Form",
            target_id=str(form_id),
            details={
                "form_id": form_id,
                "title": form_title,
                "owner_id": form_owner_id,
                "deleted_by_role": current_user.role,
                "submissions_deleted": subs_count,
                "drafts_deleted": drafts_count,
            },
            status="SUCCESS"
        )
        logger.info(f"Form {form_id} ('{form_title}') successfully deleted by {current_user.role} user {current_user.id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete form {form_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred while deleting the form: {str(e)}"
        )


@router.get("/{form_id}/original-document")
def get_original_document(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Download the original source document associated with this form if available.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form or not form.original_document_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original document not found.")

    if not form.is_public:
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        if form.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original document not found.")

    real_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    real_doc_path = os.path.abspath(form.original_document_path)
    if os.path.commonpath([real_upload_dir, real_doc_path]) != real_upload_dir or not os.path.exists(real_doc_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original document file not found.")

    return FileResponse(
        path=real_doc_path,
        filename=os.path.basename(real_doc_path)
    )


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

    # Privacy check
    if not form.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this private form."
            )
        if form.user_id != current_user.id:
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
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve server-side saved draft for this form and user/session.
    Anonymous users only access drafts associated with their specific session_id.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if not form.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this private form."
            )
        if form.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Form with ID {form_id} was not found"
            )

    query = db.query(Draft).filter(Draft.form_id == form_id)
    if current_user:
        draft = query.filter(Draft.user_id == current_user.id).first()
    else:
        clean_session = (session_id or "").strip()
        if clean_session:
            draft = query.filter(Draft.user_id.is_(None), Draft.session_id == clean_session).first()
        else:
            draft = query.filter(Draft.user_id.is_(None), Draft.session_id.is_(None)).first()

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
    Isolated per authenticated user or guest session.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if not form.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this private form."
            )
        if form.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this private form."
            )

    query = db.query(Draft).filter(Draft.form_id == form_id)
    if current_user:
        draft = query.filter(Draft.user_id == current_user.id).first()
    else:
        clean_session = (req.session_id or "").strip()
        if clean_session:
            draft = query.filter(Draft.user_id.is_(None), Draft.session_id == clean_session).first()
        else:
            draft = query.filter(Draft.user_id.is_(None), Draft.session_id.is_(None)).first()

    if draft:
        draft.values_json = req.values_json
    else:
        draft = Draft(
            form_id=form_id,
            user_id=current_user.id if current_user else None,
            session_id=req.session_id if not current_user else None,
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
    session_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Clear draft once form is submitted or discarded.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    query = db.query(Draft).filter(Draft.form_id == form_id)
    if current_user:
        drafts = query.filter(Draft.user_id == current_user.id).all()
    else:
        clean_session = (session_id or "").strip()
        if clean_session:
            drafts = query.filter(Draft.user_id.is_(None), Draft.session_id == clean_session).all()
        else:
            drafts = query.filter(Draft.user_id.is_(None), Draft.session_id.is_(None)).all()

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

    if not form.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to submit to this private form."
            )
        if form.user_id != current_user.id:
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

    # Automatically generate completed PDF document in background (failsafe)
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

    # Remove only the submitting user's draft upon successful submission
    try:
        draft_query = db.query(Draft).filter(Draft.form_id == form_id)
        if current_user:
            user_drafts = draft_query.filter(Draft.user_id == current_user.id).all()
        else:
            user_drafts = []
        for d in user_drafts:
            db.delete(d)
        db.commit()
    except Exception as draft_err:
        logger.warning(f"Could not clear draft after submission: {draft_err}")

    logger.info(f"Submission {new_sub.id} created for form {form_id}")
    return new_sub


@router.get("/{form_id}/submissions", response_model=List[SubmissionResponse])
def get_form_submissions(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve submissions for a specific form.
    - Requires authentication.
    - Form creator sees all submissions for their form.
    - Other authenticated users see only their own submissions.
    - Anonymous visitors cannot access submission histories.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view submission history."
        )

    # Privacy check
    if not form.is_public and form.user_id != current_user.id:
        is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Form with ID {form_id} was not found"
            )

    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
    # If the current user is the owner of the form or an admin, return all submissions
    if (form.user_id is not None and current_user.id == form.user_id) or is_admin:
        submissions = (
            db.query(Submission)
            .filter(Submission.form_id == form_id)
            .order_by(Submission.created_at.desc())
            .all()
        )
        return submissions

    # Otherwise, return only the current user's submissions
    submissions = (
        db.query(Submission)
        .filter(Submission.form_id == form_id, Submission.user_id == current_user.id)
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
    Requires authentication. Access is permitted only to the submission author, form owner, or admin.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    submission = db.query(Submission).filter(Submission.id == sub_id, Submission.form_id == form_id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {sub_id} not found"
        )

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to download this submission PDF."
        )

    is_owner = (form.user_id is not None) and (current_user.id == form.user_id)
    is_author = (submission.user_id is not None) and (current_user.id == submission.user_id)
    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
    has_access = is_owner or is_author or is_admin or (submission.user_id is None and form.is_public)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to download this submission PDF."
        )

    pdf_path = submission.generated_pdf_path

    if not pdf_path or not os.path.exists(pdf_path):
        schema_dict = form.schema_json or {}
        pdf_path = generate_completed_pdf(
            form_title=form.title,
            form_description=form.description,
            fields_schema=schema_dict.get("fields", []),
            response_data=submission.response_json or {},
            submission_id=submission.id,
            original_pdf_path=form.original_document_path,
        )
        submission.generated_pdf_path = pdf_path
        db.commit()

    # Enforce path containment
    real_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    real_pdf_path = os.path.abspath(pdf_path)
    if os.path.commonpath([real_upload_dir, real_pdf_path]) != real_upload_dir or not os.path.exists(real_pdf_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid submission PDF path."
        )

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", form.title)
    return FileResponse(
        path=real_pdf_path,
        media_type="application/pdf",
        filename=f"{safe_title}_submission_{sub_id}.pdf"
    )


@router.post("/{form_id}/voice-map", response_model=VoiceMapResponse)
def voice_map_fields(
    form_id: int,
    req: VoiceMapRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Deterministic rule-based slot-filling voice mapping.
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    if not form.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this private form."
            )
        if form.user_id != current_user.id:
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
