import os
import re
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import cast, String

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
    PdfExtractAndMapResponse,
    FormExportPdfRequest,
    is_identifier_field,
)
from app.schemas.submission import (
    SubmissionCreate,
    SubmissionResponse,
    UserSubmissionResponse,
)
from app.services.ai_service import generate_form_schema
from app.services.voice_mapping import map_transcript_to_fields
from app.services.conversation_service import conversation_manager
from app.services.pdf_service import (
    generate_completed_pdf,
    process_document_hybrid,
    extract_and_map_pdf_personal_info,
)
from app.services.excel_service import generate_submissions_excel
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
    Requires administrator authorization (ADMIN or SUPER_ADMIN).
    Ordinary USER accounts cannot create administrator-managed forms or any new forms.
    """
    if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create forms. Only administrators can create forms."
        )

    orig_doc = None
    if form_in.original_document_path:
        clean_doc = os.path.basename(form_in.original_document_path)
        candidate_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, clean_doc))
        real_upload_dir = os.path.normcase(os.path.realpath(settings.UPLOAD_DIR))
        real_candidate = os.path.normcase(os.path.realpath(candidate_path))
        if real_candidate.startswith(real_upload_dir) and os.path.exists(candidate_path):
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
    logger.info(f"Form created with ID: {new_form.id} by {current_user.role} user {current_user.id} (public={new_form.is_public})")
    return new_form


@router.get("", response_model=List[FormResponse])
def list_forms(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve saved forms. Authenticated users see their own forms plus all public forms;
    unauthenticated visitors see only explicitly public forms.
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


@router.get("/user/submissions", response_model=List[UserSubmissionResponse])
def get_user_submissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Retrieve submissions for the logged-in user with strict ownership enforcement.
    Non-admins only see their own authored submissions.
    """
    submissions = (
        db.query(Submission)
        .filter(Submission.user_id == current_user.id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    result = []
    for sub in submissions:
        form_title = sub.form.title if sub.form else "Archived Form"
        result.append(
            UserSubmissionResponse(
                id=sub.id,
                form_id=sub.form_id,
                form_title=form_title,
                response_json=sub.response_json or {},
                created_at=sub.created_at,
                status="Completed",
                generated_pdf_path=sub.generated_pdf_path,
                user_id=sub.user_id,
            )
        )
    return result


@router.get("/submissions/{sub_id}/pdf")
@router.get("/{form_id}/submissions/{sub_id}/pdf")
def download_submission_pdf(
    sub_id: int,
    form_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Download publication-ready completed PDF for this submission.
    Requires authentication. Access is permitted strictly to the submission author, form owner, or admin.
    Submission IDs are never trusted as proof of ownership.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to download this submission PDF."
        )

    submission = db.query(Submission).filter(Submission.id == sub_id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {sub_id} not found."
        )

    if form_id is not None and submission.form_id != form_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission does not match the specified form."
        )

    form = db.query(Form).filter(Form.id == submission.form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The form associated with submission {sub_id} was not found."
        )

    is_owner = (form.user_id is not None) and (current_user.id == form.user_id)
    is_author = (submission.user_id is not None) and (current_user.id == submission.user_id)
    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]

    if not (is_owner or is_author or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to download this submission PDF."
        )

    pdf_path = submission.generated_pdf_path
    pdf_valid = False
    if pdf_path and os.path.exists(pdf_path):
        real_upload_dir = os.path.normcase(os.path.realpath(settings.UPLOAD_DIR))
        real_pdf_path = os.path.normcase(os.path.realpath(pdf_path))
        if real_pdf_path.startswith(real_upload_dir) and os.path.getsize(pdf_path) > 100:
            pdf_valid = True

    if not pdf_valid:
        try:
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
        except Exception as gen_err:
            logger.error(f"Failed to generate completed PDF for submission {sub_id}: {gen_err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate submission PDF: {str(gen_err)}"
            )

    real_upload_dir = os.path.normcase(os.path.realpath(settings.UPLOAD_DIR))
    real_pdf_path = os.path.normcase(os.path.realpath(pdf_path))
    if not real_pdf_path.startswith(real_upload_dir) or not os.path.exists(real_pdf_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid submission PDF path."
        )

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", form.title).strip("_") or "form"
    filename = f"{safe_title}_submission_{sub_id}.pdf"
    return FileResponse(
        path=real_pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/{form_id}", response_model=FormResponse)
def get_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve a specific form by its ID.
    Enforces privacy: if a form is private (is_public=False), only the owner or admins can view it.
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
    Only the form owner or administrators can modify a form.
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

    if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify forms. Only administrators can modify forms."
        )

    is_super_admin = current_user.role == "SUPER_ADMIN"

    # Protect unowned shared templates from non-super-admins
    if form.user_id is None and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared system templates can only be modified by super administrators."
        )

    # Standard admins can only modify forms they own
    if form.user_id is not None and form.user_id != current_user.id and not is_super_admin:
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
    logger.info(f"Form {form_id} updated successfully by user {current_user.id} (public={form.is_public})")
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
    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]

    # Non-super-admins cannot delete shared system templates
    if form.user_id is None and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared system templates cannot be deleted."
        )

    # Ordinary USER accounts cannot delete administrator-managed forms
    if form.is_public and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete administrator-managed forms."
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
        is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
        if form.user_id != current_user.id and not is_admin:
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


def _filter_submissions_query(
    query,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    """Shared filter logic for submissions table, CSV, and Excel exports."""
    if start_date:
        try:
            s_clean = start_date.strip()
            if len(s_clean) == 10:
                dt_start = datetime.strptime(s_clean, "%Y-%m-%d")
            else:
                dt_start = datetime.fromisoformat(s_clean.replace("Z", "+00:00"))
            query = query.filter(Submission.created_at >= dt_start)
        except Exception as e:
            logger.warning(f"Could not parse start_date '{start_date}': {e}")

    if end_date:
        try:
            e_clean = end_date.strip()
            if len(e_clean) == 10:
                dt_end = datetime.strptime(e_clean, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            else:
                dt_end = datetime.fromisoformat(e_clean.replace("Z", "+00:00"))
            query = query.filter(Submission.created_at <= dt_end)
        except Exception as e:
            logger.warning(f"Could not parse end_date '{end_date}': {e}")

    if search:
        s_val = search.strip()
        if s_val:
            if s_val.isdigit():
                sub_id = int(s_val)
                query = query.outerjoin(User, Submission.user_id == User.id).filter(
                    (Submission.id == sub_id) |
                    (cast(Submission.response_json, String).ilike(f"%{s_val}%")) |
                    (User.email.ilike(f"%{s_val}%")) |
                    (User.full_name.ilike(f"%{s_val}%"))
                )
            else:
                query = query.outerjoin(User, Submission.user_id == User.id).filter(
                    (cast(Submission.response_json, String).ilike(f"%{s_val}%")) |
                    (User.email.ilike(f"%{s_val}%")) |
                    (User.full_name.ilike(f"%{s_val}%"))
                )

    if status_filter:
        st_clean = status_filter.strip().lower()
        if st_clean not in ("all", "completed"):
            query = query.filter(Submission.id == -1)

    return query


@router.get("/{form_id}/submissions", response_model=List[SubmissionResponse])
def get_form_submissions(
    form_id: int,
    search: Optional[str] = Query(None, description="Search keyword in responses or respondent"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD or ISO)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD or ISO)"),
    status_filter: Optional[str] = Query(None, description="Filter by submission status"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Retrieve submissions for a specific form with consistent filtering.
    - Requires authentication.
    - Form creator and Admins see all submissions for their form.
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
    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
    is_owner = (form.user_id is not None and current_user.id == form.user_id)
    if not form.is_public and not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    # If the current user is the owner of the form or an admin, return all submissions
    if is_owner or is_admin:
        query = db.query(Submission).filter(Submission.form_id == form_id)
    else:
        query = db.query(Submission).filter(Submission.form_id == form_id, Submission.user_id == current_user.id)

    query = _filter_submissions_query(
        query=query,
        search=search,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
    )

    return query.order_by(Submission.created_at.desc()).all()


@router.get("/{form_id}/export-excel")
@router.get("/{form_id}/submissions/export-excel")
def export_form_submissions_excel(
    form_id: int,
    search: Optional[str] = Query(None, description="Search keyword in responses or respondent"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD or ISO)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD or ISO)"),
    status_filter: Optional[str] = Query(None, description="Filter by submission status"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Export form submissions as a formatted multi-sheet Excel (.xlsx) workbook.
    - Sheet 1: Submission Summary (ID, Respondent info, Date, Status)
    - Sheet 2: Response Details (ID, Field Identifier, Field Label, Field Value)
    - Enforces role-based data isolation:
      * Standard USER can only export their own submissions for published forms.
      * Form owner & ADMIN / SUPER_ADMIN can export all submissions for forms they manage.
    - Preserves Unicode (e.g. Tamil characters) and sanitizes spreadsheet formula injection.
    - Shares exact same filtering rules with submissions table and CSV export.
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
            detail="Authentication required to export submissions."
        )

    # Privacy check for private forms
    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
    is_owner = (form.user_id is not None) and (form.user_id == current_user.id)
    if not form.is_public and not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    # Determine permitted submissions scope
    if is_owner or is_admin:
        query = db.query(Submission).filter(Submission.form_id == form_id)
    else:
        query = db.query(Submission).filter(
            Submission.form_id == form_id,
            Submission.user_id == current_user.id
        )

    # Apply shared filters
    query = _filter_submissions_query(
        query=query,
        search=search,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
    )
    submissions = query.order_by(Submission.created_at.desc()).all()

    # Pre-fetch user map for respondent details
    user_ids = {s.user_id for s in submissions if s.user_id}
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u for u in users}

    excel_buffer = generate_submissions_excel(
        form=form,
        submissions=submissions,
        user_map=user_map,
        current_user=current_user,
    )

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", form.title).strip("_") or "Form"
    filename = f"{safe_title}_Submissions.xlsx"

    return Response(
        content=excel_buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
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


@router.post("/{form_id}/extract-pdf", response_model=PdfExtractAndMapResponse)
async def extract_pdf_for_published_form(
    form_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Extract personal information from an uploaded PDF and map it strictly
    to the authorized field definitions of the selected published form.

    Enforces:
    - JWT authentication required (ownership-isolated per user)
    - Authorization check against private forms
    - Format verification (.pdf extension, %PDF- magic byte signature, 15MB size limit)
    - Graceful rejection of encrypted, corrupted, empty, or unsupported documents
    - Safe in-memory text parsing & OCR without exposing documents publicly
    - Merging extracted values into user's draft without corrupting existing user input
    """
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Form with ID {form_id} was not found"
        )

    # Privacy & ownership check
    if not form.is_public:
        is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
        if form.user_id != current_user.id and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this private form."
            )

    filename = file.filename or "personal_document.pdf"
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a PDF document (.pdf)."
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

    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PDF file structure. File content does not match a valid PDF document."
        )

    logger.info(
        f"Extracting PDF personal information for form {form_id} by user {current_user.id} "
        f"(filename={os.path.basename(filename)}, size={len(file_bytes)} bytes)"
    )

    try:
        extraction_result = extract_and_map_pdf_personal_info(
            file_bytes=file_bytes,
            filename=os.path.basename(filename),
            form_schema=form.schema_json or {}
        )
    except AIProviderError as e:
        logger.error(f"AI provider error during PDF extraction: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        logger.warning(f"Validation error in PDF personal info extraction: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during PDF personal info extraction: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract personal information from PDF due to an unexpected internal error."
        )

    extracted_fields = extraction_result["extracted_fields"]

    # Integrate with draft persistence: merge with existing user draft
    existing_draft = db.query(Draft).filter(
        Draft.form_id == form_id,
        Draft.user_id == current_user.id
    ).first()

    merged_values: Dict[str, Any] = {}
    if existing_draft and existing_draft.values_json:
        merged_values.update(existing_draft.values_json)

    # Apply extracted values (preserving fields where user has existing non-empty values unless empty)
    for k, v in extracted_fields.items():
        if not merged_values.get(k):
            merged_values[k] = v
        else:
            # Keep user value if already present, but record extracted_fields in response
            pass

    # Ensure all extracted fields are in merged_values if draft had nothing
    for k, v in extracted_fields.items():
        if k not in merged_values:
            merged_values[k] = v

    if existing_draft:
        existing_draft.values_json = merged_values
    else:
        new_draft = Draft(
            form_id=form_id,
            user_id=current_user.id,
            values_json=merged_values,
            status="in_progress",
        )
        db.add(new_draft)

    db.commit()

    total_fields_count = len(form.schema_json.get("fields", []) if form.schema_json else [])

    return PdfExtractAndMapResponse(
        form_id=form_id,
        extracted_fields=extracted_fields,
        confidence_scores=extraction_result.get("confidence_scores", {}),
        source_evidence=extraction_result.get("source_evidence", {}),
        needs_review=extraction_result.get("needs_review", {}),
        missing_required_fields=extraction_result.get("missing_required_fields", []),
        all_missing_fields=extraction_result.get("all_missing_fields", []),
        merged_values=merged_values,
        total_matched=len(extracted_fields),
        total_fields=total_fields_count,
        message=extraction_result.get("message", "Personal information extracted and mapped to form successfully."),
        extraction_strategy=extraction_result.get("strategy", "digital_text"),
        pages_processed=extraction_result.get("pages_processed", 1),
    )


@router.post("/{form_id}/export-pdf")
def export_form_completed_pdf(
    form_id: int,
    req: FormExportPdfRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Generate and download a completed PDF document for this form independent of submission.
    Includes the user's filled or corrected values.
    Validates form access and schema before generating output.
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
                detail="Authentication required to export this private form."
            )
        is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
        if form.user_id != current_user.id and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to export this private form."
            )

    schema_dict = form.schema_json or {}
    fields_list = schema_dict.get("fields", [])

    temp_id = uuid.uuid4().hex[:8]
    try:
        pdf_path = generate_completed_pdf(
            form_title=form.title,
            form_description=form.description,
            fields_schema=fields_list,
            response_data=req.values or {},
            submission_id=f"PREVIEW-{temp_id}",
            original_pdf_path=form.original_document_path,
        )
    except Exception as e:
        logger.error(f"Failed to generate export PDF for form {form_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate completed PDF: {str(e)}"
        )

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", form.title).strip("_") or "form"
    filename = f"{safe_title}_completed.pdf"

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
