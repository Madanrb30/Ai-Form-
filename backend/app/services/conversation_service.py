import uuid
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.conversation import ConversationSession
from app.models.form import Form
from app.services.voice_mapping import (
    map_transcript_to_fields,
    match_dropdown_option,
    normalize_spoken_identifier,
)
from app.schemas.form import is_identifier_field
from app.services.ai_provider import ai_provider
from app.core.logging import logger


class ConversationManager:
    def get_or_create_session(
        self,
        db: Session,
        form_id: int,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ConversationSession:
        if session_id:
            existing = db.query(ConversationSession).filter(ConversationSession.id == session_id).first()
            if existing:
                from fastapi import HTTPException, status
                # 1. Enforce form isolation
                if existing.form_id != form_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Conversation session belongs to a different form."
                    )
                # 2. Prevent cross-user session tampering & anonymous hijacking
                if existing.user_id is not None:
                    if user_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required to access this conversation session."
                        )
                    if existing.user_id != user_id:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have permission to access this conversation session."
                        )
                elif user_id is not None:
                    existing.user_id = user_id
                    db.commit()
                return existing


        new_id = session_id or f"sess_{uuid.uuid4().hex[:16]}"
        new_session = ConversationSession(
            id=new_id,
            form_id=form_id,
            user_id=user_id,
            state_json={
                "values": {},
                "confirmed_fields": [],
                "needs_review": {},
                "history": [],
                "current_field": None,
                "stage": "filling",
            },
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return new_session

    def process_turn(
        self,
        db: Session,
        form: Form,
        session: ConversationSession,
        transcript: str,
        client_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        schema = form.schema_json
        fields = schema.get("fields", [])
        state = dict(session.state_json or {})

        # Synchronize values with client state if passed
        values = dict(state.get("values", {}))
        if client_values:
            values.update(client_values)

        confirmed_fields = set(state.get("confirmed_fields", []))
        needs_review = dict(state.get("needs_review", {}))
        history = list(state.get("history", []))

        text_lower = transcript.strip().lower()

        # 1. Check for submission confirmation or submit voice commands
        is_confirm_submit = self._is_submission_confirmation(text_lower, state.get("stage"))
        if is_confirm_submit:
            missing_required = self._find_next_missing_field(fields, values, confirmed_fields)
            if missing_required:
                resp = f"We cannot submit just yet because your {missing_required.get('label')} is still required. What is your {missing_required.get('label')}?"
                state["current_field"] = missing_required.get("name")
                return self._build_response(
                    session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript
                )
            else:
                return self._execute_submission(
                    session=session,
                    db=db,
                    form=form,
                    values=values,
                    confirmed_fields=confirmed_fields,
                    needs_review=needs_review,
                    fields=fields,
                    history=history,
                    transcript=transcript
                )

        # Handle user rejection or hold during submission confirmation (when not providing a correction)
        if state.get("stage") in ("reviewing", "confirming_submission") and any(
            w in text_lower for w in ["no", "wait", "hold on", "not yet", "cancel", "stop"]
        ) and not any(w in text_lower for w in ["change", "update", "instead", "replace", "correct"]):
            resp = "Understood. Which field would you like to review or update?"
            state["stage"] = "filling"
            return self._build_response(
                session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript
            )

        # 2. Check for standard voice navigation and control commands
        if any(cmd in text_lower for cmd in ["repeat the question", "repeat question", "what was the question", "repeat"]):
            curr = state.get("current_field")
            curr_label = curr
            for f in fields:
                if f.get("name") == curr:
                    curr_label = f.get("label", curr)
                    break
            resp = f"Please provide your {curr_label or 'next detail'}."
            return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, state.get("stage", "filling"), history, transcript)

        if any(cmd in text_lower for cmd in ["skip this field", "skip field", "skip"]):
            curr = state.get("current_field")
            if curr:
                needs_review[curr] = "Skipped by user"
            next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
            state["current_field"] = next_missing.get("name") if next_missing else None
            resp = f"Skipped. What is your {next_missing.get('label')}?" if next_missing else "All required fields are ready. You can review and submit your form."
            return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript)

        # 2. Check if user is directly answering the currently focused/prompted field
        current_field_name = state.get("current_field")
        curr_field_obj = next((f for f in fields if f.get("name") == current_field_name), None)

        direct_curr_match = None
        if curr_field_obj:
            ftype = curr_field_obj.get("type", "text")
            is_ident = is_identifier_field(curr_field_obj)
            options = curr_field_obj.get("options") or []

            if ftype in ("select", "radio") and options:
                matched_opt, is_ambig = match_dropdown_option(transcript, options)
                if matched_opt:
                    direct_curr_match = (current_field_name, matched_opt)
                elif is_ambig:
                    needs_review[current_field_name] = f"Multiple matching options for {curr_field_obj.get('label')}. Please clarify."
                    resp = f"Did you mean one of: {', '.join(options)}?"
                    return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript)
            elif is_ident:
                norm_id = normalize_spoken_identifier(transcript)
                # If transcript was an identifier answer (no long English sentence words)
                words = [w for w in re.split(r"\s+", transcript.strip()) if w]
                if len(words) <= 10 and re.match(r"^[A-Za-z0-9_\-\+]+$", norm_id):
                    direct_curr_match = (current_field_name, norm_id)

        # 3. Extract values: Use deterministic slot-filling
        newly_mapped = map_transcript_to_fields(transcript, schema)
        if direct_curr_match:
            newly_mapped[direct_curr_match[0]] = direct_curr_match[1]

        # 4. Check for unhandled invalid dropdown option attempts
        # e.g., "My department is Biotechnology" when options are AI&DS, CSE, ECE, Mechanical
        for f in fields:
            fname = f.get("name")
            flabel = f.get("label", fname)
            ftype = f.get("type", "text")
            options = f.get("options") or []
            if ftype in ("select", "radio") and options and fname not in newly_mapped:
                # Check if the field was mentioned by name in transcript
                pattern = rf"\b{re.escape(flabel.lower())}\b|\b{re.escape(fname.lower().replace('_', ' '))}\b"
                if re.search(pattern, text_lower):
                    # User attempted to answer this field, but value was not valid
                    opts_str = ", ".join(options)
                    needs_review[fname] = f"Spoken value is not a valid option for {flabel}. Available options: {opts_str}"
                    resp = f"That is not one of the available options for {flabel}. Please choose from: {opts_str}."
                    state["current_field"] = fname
                    return self._build_response(
                        session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript
                    )

        newly_filled = []
        assistant_reply = ""

        if newly_mapped:
            for k, v in newly_mapped.items():
                target_field = next((f for f in fields if f.get("name") == k), None)
                if not target_field:
                    continue

                # Type-specific validation
                ftype = target_field.get("type", "text")
                is_ident = is_identifier_field(target_field)
                if is_ident:
                    v = normalize_spoken_identifier(str(v))
                elif ftype in ("select", "radio"):
                    options = target_field.get("options") or []
                    matched_opt, is_ambig = match_dropdown_option(str(v), options)
                    if matched_opt:
                        v = matched_opt
                    else:
                        needs_review[k] = f"Invalid option '{v}' for {target_field.get('label')}."
                        continue

                # Overwrite protection
                is_correction = any(w in text_lower for w in ["change", "replace", "correct", "update", "wrong", "instead"])
                if k in confirmed_fields and not is_correction:
                    needs_review[k] = f"New value '{v}' proposed for already confirmed field."
                else:
                    values[k] = v
                    confirmed_fields.add(k)
                    newly_filled.append(k)
                    needs_review.pop(k, None)

        # 5. Generate next conversational step & follow-up question
        next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
        state["current_field"] = next_missing.get("name") if next_missing else None

        if newly_filled:
            field_labels = [f.get("label") for f in fields if f.get("name") in newly_filled]
            ack = f"Got your {', '.join(field_labels)}."
            if next_missing:
                assistant_reply = f"{ack} What is your {next_missing.get('label')}?"
            else:
                if any(w in text_lower for w in ["submit", "send it", "finish"]):
                    return self._execute_submission(
                        session=session,
                        db=db,
                        form=form,
                        values=values,
                        confirmed_fields=confirmed_fields,
                        needs_review=needs_review,
                        fields=fields,
                        history=history,
                        transcript=transcript,
                        newly_filled=newly_filled
                    )
                assistant_reply = f"{ack} All required fields are now completed! Would you like to submit the form now?"
                state["stage"] = "confirming_submission"
        else:
            # If no fields extracted via deterministic rules, attempt Groq AI interpretation if configured
            if ai_provider.is_groq_configured():
                try:
                    statuses = self._format_field_statuses(fields, values, confirmed_fields)
                    ai_turn = ai_provider.process_conversation_turn(
                        form_title=schema.get("title", "Form"),
                        field_statuses=statuses,
                        user_speech=transcript
                    )
                    ext = ai_turn.get("extracted_fields", {})
                    for k, v in ext.items():
                        target_field = next((f for f in fields if f.get("name") == k), None)
                        if not target_field:
                            continue

                        ftype = target_field.get("type", "text")
                        is_ident = is_identifier_field(target_field)
                        options = target_field.get("options") or []

                        if is_ident:
                            v = normalize_spoken_identifier(str(v))
                        elif ftype in ("select", "radio") and options:
                            matched_opt, is_ambig = match_dropdown_option(str(v), options)
                            if matched_opt:
                                v = matched_opt
                            else:
                                needs_review[k] = f"'{v}' is not a valid option for {target_field.get('label')}."
                                continue
                        elif ftype == "number":
                            try:
                                v = float(v) if "." in str(v) else int(v)
                            except (ValueError, TypeError):
                                needs_review[k] = f"'{v}' is not a valid number."
                                continue

                        is_correction = any(w in text_lower for w in ["change", "replace", "correct", "update", "wrong", "instead"])
                        if k in confirmed_fields and not is_correction:
                            needs_review[k] = f"New value '{v}' proposed for already confirmed field."
                        else:
                            values[k] = v
                            confirmed_fields.add(k)
                            newly_filled.append(k)
                            needs_review.pop(k, None)

                    assistant_reply = ai_turn.get("assistant_response") or ""
                except Exception as e:
                    logger.warning(f"Groq turn fallback: {e}")

            if not assistant_reply:
                if next_missing:
                    assistant_reply = f"I didn't quite catch that. Could you tell me your {next_missing.get('label')}?"
                else:
                    assistant_reply = "All required fields are completed! Would you like to submit the form now?"
                    state["stage"] = "confirming_submission"

        return self._build_response(
            session=session,
            db=db,
            values=values,
            confirmed_fields=confirmed_fields,
            needs_review=needs_review,
            fields=fields,
            reply=assistant_reply,
            stage=state.get("stage", "filling"),
            history=history,
            user_transcript=transcript,
            newly_filled=newly_filled
        )

    def _find_next_missing_field(
        self,
        fields: List[Dict[str, Any]],
        values: Dict[str, Any],
        confirmed_fields: set
    ) -> Optional[Dict[str, Any]]:
        for f in fields:
            fname = f.get("name")
            required = f.get("required", False)
            val = values.get(fname)
            is_empty = val is None or (isinstance(val, str) and not val.strip()) or val is False
            if required and is_empty:
                return f
        return None

    def _format_field_statuses(
        self,
        fields: List[Dict[str, Any]],
        values: Dict[str, Any],
        confirmed_fields: set
    ) -> str:
        lines = []
        for f in fields:
            fname = f.get("name")
            flabel = f.get("label", fname)
            ftype = f.get("type", "text")
            options = f.get("options") or []
            is_ident = is_identifier_field(f)
            req = "Required" if f.get("required") else "Optional"
            val = values.get(fname, "")
            status = "CONFIRMED" if fname in confirmed_fields else "POPULATED" if val else "MISSING"

            line_parts = [
                f"- {flabel} (id: {fname})",
                f"type: {ftype}",
                f"{req}",
                f"status: {status}",
            ]
            if is_ident:
                line_parts.append("is_identifier: true")
            if ftype in ("select", "radio") and options:
                line_parts.append(f"allowed_options: {options}")
            line_parts.append(f"value: '{val}'")

            lines.append(" | ".join(line_parts))
        return "\n".join(lines)

    def _build_response(
        self,
        session: ConversationSession,
        db: Session,
        values: Dict[str, Any],
        confirmed_fields: set,
        needs_review: Dict[str, str],
        fields: List[Dict[str, Any]],
        reply: str,
        stage: str,
        history: List[Dict[str, Any]],
        user_transcript: str,
        newly_filled: Optional[List[str]] = None,
        is_submitted: bool = False,
        submission_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        # Missing required list
        missing = [
            f.get("name") for f in fields
            if f.get("required") and (values.get(f.get("name")) is None or str(values.get(f.get("name"))).strip() == "")
        ]

        history.append({"user": user_transcript, "assistant": reply})
        if len(history) > 20:
            history = history[-20:]

        session.state_json = {
            "values": values,
            "confirmed_fields": list(confirmed_fields),
            "needs_review": needs_review,
            "history": history,
            "stage": stage,
        }
        db.commit()

        return {
            "session_id": session.id,
            "assistant_response": reply,
            "updated_values": values,
            "newly_filled": newly_filled or [],
            "confirmed_fields": list(confirmed_fields),
            "missing_fields": missing,
            "needs_review": needs_review,
            "stage": stage,
            "is_completed": len(missing) == 0,
            "is_submitted": is_submitted,
            "submission_id": submission_id,
        }

    def _is_submission_confirmation(self, text_lower: str, current_stage: Optional[str]) -> bool:
        cleaned = text_lower.strip().lower()
        # Direct explicit submit command
        explicit_phrases = [
            "submit the form", "submit form", "submit it", "submit now",
            "confirm submit", "confirm submission", "please submit",
            "go ahead and submit", "proceed to submit", "finish and submit",
            "submit my response", "submit response", "i want to submit"
        ]
        if any(phrase in cleaned for phrase in explicit_phrases):
            return True

        # Standalone submit or confirm
        if cleaned in ["submit", "confirm", "yes, submit", "yes submit"]:
            return True

        # If in reviewing or confirming_submission stage:
        if current_stage in ("reviewing", "confirming_submission"):
            if cleaned in [
                "yes", "yeah", "yep", "sure", "ok", "okay", "yup",
                "proceed", "go ahead", "confirm", "yes please",
                "yes submit", "looks good", "everything is correct"
            ]:
                return True
            if any(cleaned.startswith(w) for w in ["yes", "yeah", "yep", "sure", "confirm", "submit"]):
                return True

        return False

    def _execute_submission(
        self,
        session: ConversationSession,
        db: Session,
        form: Form,
        values: Dict[str, Any],
        confirmed_fields: set,
        needs_review: Dict[str, str],
        fields: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
        transcript: str,
        newly_filled: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        from app.models.submission import Submission
        from app.models.draft import Draft
        from app.services.pdf_service import generate_completed_pdf

        # 1. Create submission record in database
        new_sub = Submission(
            form_id=form.id,
            user_id=session.user_id,
            response_json=values,
        )
        db.add(new_sub)
        db.commit()
        db.refresh(new_sub)

        # 2. Generate publication-ready PDF in background (failsafe)
        try:
            pdf_path = generate_completed_pdf(
                form_title=form.title,
                form_description=form.description,
                fields_schema=fields,
                response_data=values,
                submission_id=new_sub.id,
                original_pdf_path=form.original_document_path,
            )
            new_sub.generated_pdf_path = pdf_path
            db.commit()
        except Exception as e:
            logger.warning(f"Could not generate PDF for conversational submission {new_sub.id}: {e}")

        # 3. Clean up database drafts for this user/session
        try:
            draft_q = db.query(Draft).filter(Draft.form_id == form.id)
            if session.user_id:
                drafts = draft_q.filter(Draft.user_id == session.user_id).all()
            elif session.id:
                drafts = draft_q.filter(Draft.user_id.is_(None), Draft.session_id == session.id).all()
            else:
                drafts = []
            for d in drafts:
                db.delete(d)
            db.commit()
        except Exception as d_err:
            logger.warning(f"Could not clear draft after conversational submission: {d_err}")

        reply = f"Your form has been successfully submitted! Your response has been recorded with submission ID #{new_sub.id}. You can download your completed PDF now."

        history.append({"user": transcript, "assistant": reply})
        if len(history) > 20:
            history = history[-20:]

        session.state_json = {
            "values": values,
            "confirmed_fields": list(confirmed_fields),
            "needs_review": needs_review,
            "history": history,
            "stage": "submitted",
        }
        db.commit()

        logger.info(f"Conversational form submission created: Submission {new_sub.id} for Form {form.id} by user {session.user_id}")

        return {
            "session_id": session.id,
            "assistant_response": reply,
            "updated_values": values,
            "newly_filled": newly_filled or [],
            "confirmed_fields": list(confirmed_fields),
            "missing_fields": [],
            "needs_review": needs_review,
            "stage": "submitted",
            "is_completed": True,
            "is_submitted": True,
            "submission_id": new_sub.id,
        }


conversation_manager = ConversationManager()
