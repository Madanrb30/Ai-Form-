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
    parse_spoken_date,
)
from app.schemas.form import is_identifier_field, is_name_field, is_valid_name
from app.services.ai_provider import ai_provider
from app.core.logging import logger
from app.services.intent_service import (
    IntentType,
    classify_utterance_intent,
    detect_clear_field,
    is_command_sentence,
)


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
        cleared_fields: List[str] = []

        # Step 1: Intent Classification
        classification = classify_utterance_intent(transcript, fields, state)
        intent = classification["intent"]

        # 1. Intent: GENERAL_CONVERSATION or empty transcript
        if intent == IntentType.GENERAL_CONVERSATION or not transcript:
            next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
            state["current_field"] = next_missing.get("name") if next_missing else None
            form_title = schema.get("title", form.title or "form")
            if next_missing:
                resp = f"Hello! Let's fill out the {form_title}. What is your {next_missing.get('label', next_missing.get('name'))}?"
            else:
                resp = f"Hello! All required fields for {form_title} are completed. Would you like to review and confirm before submitting?"
                state["stage"] = "confirming_submission"
            return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, state.get("stage", "filling"), history, transcript, intent=intent, state=state)

        # 2. Intent: CONFIRM_SUBMISSION
        if intent == IntentType.CONFIRM_SUBMISSION:
            missing_required = self._find_next_missing_field(fields, values, confirmed_fields)
            if missing_required:
                resp = f"We cannot submit just yet because your {missing_required.get('label')} is still required. What is your {missing_required.get('label')}?"
                state["current_field"] = missing_required.get("name")
                state["stage"] = "filling"
                return self._build_response(
                    session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state
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
                    transcript=transcript,
                    intent=intent
                )

        # 3. Intent: CANCEL_SUBMISSION
        if intent == IntentType.CANCEL_SUBMISSION:
            resp = "Understood. Which field would you like to review or update?"
            state["stage"] = "filling"
            return self._build_response(
                session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state
            )

        # 4. Intent: CLEAR_FIELD
        if intent == IntentType.CLEAR_FIELD:
            target_field = classification.get("target_field")
            if not target_field:
                clear_match = detect_clear_field(transcript, fields, state)
                if clear_match:
                    target_field = clear_match[0]

            if not target_field:
                resp = "Which field would you like to clear? Please tell me the field name."
                state["stage"] = "filling"
                return self._build_response(
                    session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state
                )

            target_name = target_field.get("name")
            target_label = target_field.get("label", target_name)
            ftype = target_field.get("type", "text")

            # Set value to type-appropriate empty representation
            if ftype == "checkbox":
                empty_val = False
            else:
                empty_val = ""

            values[target_name] = empty_val
            confirmed_fields.discard(target_name)
            needs_review.pop(target_name, None)
            state["last_modified_field"] = target_name
            state["current_field"] = target_name
            state["stage"] = "filling"
            cleared_fields = [target_name]

            next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
            if target_field.get("required"):
                resp = f"Cleared the {target_label} field. What is your {target_label}?"
            else:
                if next_missing:
                    resp = f"Cleared the {target_label} field. What is your {next_missing.get('label')}?"
                else:
                    resp = f"Cleared the {target_label} field. All required fields are completed. Would you like to review and confirm before submitting?"
                    state["stage"] = "confirming_submission"

            return self._build_response(
                session=session,
                db=db,
                values=values,
                confirmed_fields=confirmed_fields,
                needs_review=needs_review,
                fields=fields,
                reply=resp,
                stage=state.get("stage", "filling"),
                history=history,
                user_transcript=transcript,
                newly_filled=[],
                cleared_fields=cleared_fields,
                intent=intent,
                state=state
            )

        # 5. Intent: ASK_QUESTION
        if intent == IntentType.ASK_QUESTION:
            inquiry_field = classification.get("target_field") or self._detect_field_inquiry(text_lower, fields)
            if inquiry_field:
                fname = inquiry_field.get("name")
                flabel = inquiry_field.get("label", fname)
                curr_val = values.get(fname)

                if curr_val is not None and str(curr_val).strip() != "":
                    if any(w in text_lower for w in ["valid", "correct", "right", "good"]):
                        resp = f"Your {flabel} is currently recorded as '{curr_val}', and it is valid. Would you like to keep this or change it?"
                    elif any(w in text_lower for w in ["feel like", "feels like", "look like", "looks like", "sound like", "like a name"]):
                        resp = f"Your {flabel} is currently recorded as '{curr_val}'. It looks fine. Would you like to keep this or change it?"
                    else:
                        resp = f"Your {flabel} is currently recorded as '{curr_val}'. Would you like to keep this or change it?"
                else:
                    resp = f"You haven't entered your {flabel} yet. What is your {flabel}?"
                    state["current_field"] = fname

                return self._build_response(
                    session, db, values, confirmed_fields, needs_review, fields, resp, state.get("stage", "filling"), history, transcript, intent=intent, state=state
                )

            # Check for general status inquiry ("Is everything entered?", "Can I review?", "Does my form look correct?")
            if any(p in text_lower for p in ["is everything", "does my form", "check my answers", "review my answers", "how does my form"]):
                filled_summary = [f"{f.get('label', f.get('name'))}: '{values.get(f.get('name'))}'" for f in fields if values.get(f.get('name'))]
                next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
                if filled_summary:
                    summary_str = ", ".join(filled_summary[:4])
                    if len(filled_summary) > 4:
                        summary_str += f" and {len(filled_summary) - 4} more"
                    if next_missing:
                        resp = f"So far, you have entered: {summary_str}. Your {next_missing.get('label')} is still needed. What is your {next_missing.get('label')}?"
                    else:
                        resp = f"All required fields are completed: {summary_str}. Would you like to confirm and submit the form now?"
                        state["stage"] = "confirming_submission"
                else:
                    first_label = fields[0].get("label") if fields else "first detail"
                    resp = f"No fields have been entered yet. What is your {first_label}?"
                return self._build_response(
                    session, db, values, confirmed_fields, needs_review, fields, resp, state.get("stage", "filling"), history, transcript, intent=intent, state=state
                )

        # Check for ambiguous "that's wrong" or "no that is wrong" without specified field or replacement
        if re.search(r"\b(?:no\s*,?\s*)?(?:that(?:'s|\s+is)\s+wrong|that(?:'s|\s+is)\s+incorrect|it(?:'s|\s+is)\s+wrong)\b", text_lower):
            if not any(w in text_lower for w in ["change", "replace", "update", "to", "with", "as"]):
                resp = "Which field is incorrect? Please tell me what to update."
                return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state)

        # Voice navigation and control commands
        if any(cmd in text_lower for cmd in ["repeat the question", "repeat question", "what was the question", "repeat"]):
            curr = state.get("current_field")
            curr_label = curr
            for f in fields:
                if f.get("name") == curr:
                    curr_label = f.get("label", curr)
                    break
            resp = f"Please provide your {curr_label or 'next detail'}."
            return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, state.get("stage", "filling"), history, transcript, intent=intent, state=state)

        if any(cmd in text_lower for cmd in ["skip this field", "skip field", "skip"]):
            curr = state.get("current_field")
            if curr:
                needs_review[curr] = "Skipped by user"
            next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
            state["current_field"] = next_missing.get("name") if next_missing else None
            resp = f"Skipped. What is your {next_missing.get('label')}?" if next_missing else "All required fields are ready. You can review and submit your form."
            return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state)

        # 3. Check for "change the previous answer"
        newly_mapped = {}
        prev_match = re.search(
            r"\b(?:change|correct|update|replace)\s+(?:the\s+|my\s+)?(?:previous|last)\s+(?:answer|value|field|response)\b",
            text_lower
        )
        if prev_match:
            last_mod = state.get("last_modified_field")
            target_field = next((f for f in fields if f.get("name") == last_mod), None) if last_mod else None
            if not target_field:
                # Ambiguous: ask clarification question instead of changing arbitrary field
                resp = "Which previous answer would you like to change?"
                return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)

            # Check if replacement value is provided in the utterance (e.g., "Change the previous answer to Madan RB")
            val_match = re.search(r"\b(?:to|with|as)\s+(.+)$", transcript, re.IGNORECASE)
            if val_match:
                new_val_raw = val_match.group(1).strip()
                newly_mapped[target_field.get("name")] = new_val_raw
            else:
                state["current_field"] = target_field.get("name")
                resp = f"What would you like to change your {target_field.get('label', target_field.get('name'))} to?"
                return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)

        # 4. Check if user is directly answering the currently focused/prompted field
        current_field_name = state.get("current_field")
        curr_field_obj = next((f for f in fields if f.get("name") == current_field_name), None)

        direct_curr_match = None
        if curr_field_obj and not newly_mapped:
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
                    return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)
            elif is_ident:
                norm_id = normalize_spoken_identifier(transcript)
                words = [w for w in re.split(r"\s+", transcript.strip()) if w]
                if len(words) <= 10 and re.match(r"^[A-Za-z0-9_\-\+]+$", norm_id):
                    direct_curr_match = (current_field_name, norm_id)
            elif ftype == "email":
                clean_email = transcript.strip().replace(" at the rate ", "@").replace(" at ", "@").replace(" dot ", ".").replace(" ", "")
                clean_email = clean_email.strip(",.;:")
                if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
                    direct_curr_match = (current_field_name, clean_email)
            elif ftype in ("phone", "tel") or any(w in current_field_name.lower() for w in ["phone", "mobile"]):
                digits = re.sub(r"[^\d]", "", normalize_spoken_identifier(transcript))
                if len(digits) >= 7 and len(digits) <= 15:
                    direct_curr_match = (current_field_name, digits)
            elif ftype == "date":
                parsed_d = parse_spoken_date(transcript)
                if parsed_d:
                    direct_curr_match = (current_field_name, parsed_d)
            elif ftype == "number":
                norm_num = normalize_spoken_identifier(transcript)
                num_m = re.search(r"\b\d+(?:\.\d+)?\b", norm_num)
                if num_m:
                    val_num = float(num_m.group(0)) if "." in num_m.group(0) else int(num_m.group(0))
                    direct_curr_match = (current_field_name, val_num)
            elif ftype in ("text", "textarea"):
                is_q = (
                    transcript.strip().endswith("?")
                    or bool(re.search(r"^(does|do|is|are|was|were|can|could|would|should|how|what|why|did|has|have)\b", text_lower))
                    or any(p in text_lower for p in ["feel like", "feels like", "look like", "looks like", "sound like", "is valid", "valid or not", "is correct", "like a name"])
                )
                has_cmd_words = any(w in text_lower for w in ["change", "replace", "update", "set to", "my name", "my email", "my phone", "is wrong", "instead of"])
                if not is_q and not has_cmd_words and not any(w in text_lower for w in ["what", "why", "how", "repeat", "skip", "help", "cancel"]):
                    clean_ans = transcript.strip().strip(".?!")
                    if is_name_field(curr_field_obj):
                        if is_valid_name(clean_ans):
                            direct_curr_match = (current_field_name, clean_ans)
                    else:
                        if clean_ans and len(clean_ans) > 0:
                            direct_curr_match = (current_field_name, clean_ans)

        # 5. Extract values: Use deterministic slot-filling
        if not newly_mapped:
            newly_mapped = map_transcript_to_fields(transcript, schema)
        if direct_curr_match and direct_curr_match[0] not in newly_mapped:
            newly_mapped[direct_curr_match[0]] = direct_curr_match[1]

        # 6. Check for unhandled invalid dropdown option attempts
        for f in fields:
            fname = f.get("name")
            flabel = f.get("label", fname)
            ftype = f.get("type", "text")
            options = f.get("options") or []
            if ftype in ("select", "radio") and options and fname not in newly_mapped:
                pattern = rf"\b{re.escape(flabel.lower())}\b|\b{re.escape(fname.lower().replace('_', ' '))}\b"
                if re.search(pattern, text_lower):
                    opts_str = ", ".join(options)
                    needs_review[fname] = f"Spoken value is not a valid option for {flabel}. Available options: {opts_str}"
                    resp = f"That is not one of the available options for {flabel}. Please choose from: {opts_str}."
                    state["current_field"] = fname
                    return self._build_response(
                        session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state
                    )

        newly_filled = []
        assistant_reply = ""
        is_user_correction = any(w in text_lower for w in ["change", "replace", "correct", "update", "wrong", "incorrect", "instead", "not"])

        if newly_mapped:
            for k, v in newly_mapped.items():
                target_field = next((f for f in fields if f.get("name") == k), None)
                if not target_field:
                    continue

                ftype = target_field.get("type", "text")
                flbl = target_field.get("label", k)
                is_ident = is_identifier_field(target_field)
                val_str = str(v).strip()

                # Reject obvious command sentences or instructions targeting the field
                if is_command_sentence(val_str):
                    needs_review[k] = f"Command instruction ignored for {flbl}."
                    continue

                # Robust Type-specific validation
                if is_name_field(target_field):
                    if not is_valid_name(val_str) or is_command_sentence(val_str):
                        needs_review[k] = f"'{v}' does not appear to be a valid name."
                        resp = f"'{v}' does not appear to be a valid name. Please provide your full name."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state)
                    v = val_str
                elif is_ident:
                    norm_id = normalize_spoken_identifier(val_str)
                    if not re.match(r"^[A-Za-z0-9_\-\+]+$", norm_id) or is_command_sentence(val_str):
                        needs_review[k] = f"Invalid identifier for {flbl}: '{val_str}'"
                        resp = f"'{val_str}' does not appear to be a valid {flbl}. Please provide a valid {flbl}."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, intent=intent, state=state)
                    v = norm_id
                elif ftype in ("select", "radio"):
                    options = target_field.get("options") or []
                    matched_opt, is_ambig = match_dropdown_option(val_str, options)
                    if matched_opt:
                        v = matched_opt
                    else:
                        opts_str = ", ".join(options)
                        needs_review[k] = f"Invalid option '{v}' for {flbl}."
                        resp = f"'{v}' is not a valid option for {flbl}. Please choose from: {opts_str}."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)
                elif ftype == "email":
                    clean_email = val_str.replace(" at the rate ", "@").replace(" at ", "@").replace(" dot ", ".").replace(" ", "")
                    clean_email = clean_email.strip(",.;:")
                    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
                        needs_review[k] = f"Invalid email format: '{v}'"
                        resp = f"'{v}' does not appear to be a valid email address. Please provide a valid email, such as name@example.com."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)
                    v = clean_email
                elif ftype in ("phone", "tel") or any(w in k.lower() for w in ["phone", "mobile"]):
                    digits = re.sub(r"[^\d]", "", normalize_spoken_identifier(val_str))
                    if len(digits) < 7 or len(digits) > 15:
                        needs_review[k] = f"Invalid phone number: '{v}'"
                        resp = f"'{v}' does not appear to be a valid phone number. Please provide a valid phone number."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)
                    v = digits
                elif ftype == "number":
                    try:
                        v = float(val_str) if "." in val_str else int(val_str)
                    except (ValueError, TypeError):
                        needs_review[k] = f"Invalid number: '{v}'"
                        resp = f"'{v}' is not a valid number for {flbl}. Please provide a numeric value."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)
                elif ftype == "date":
                    parsed_d = parse_spoken_date(val_str)
                    if parsed_d:
                        v = parsed_d
                    elif not re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
                        needs_review[k] = f"Invalid date: '{v}'"
                        resp = f"'{v}' does not appear to be a valid date. Please provide a date like 20 October 2026."
                        state["current_field"] = k
                        return self._build_response(session, db, values, confirmed_fields, needs_review, fields, resp, "filling", history, transcript, state=state)

                # Overwrite protection / update handling
                is_field_corr = is_user_correction or (k in confirmed_fields)
                if k in confirmed_fields and not is_field_corr:
                    needs_review[k] = f"New value '{v}' proposed for already confirmed field."
                else:
                    if values.get(k) != v or k not in confirmed_fields:
                        newly_filled.append(k)
                    values[k] = v
                    confirmed_fields.add(k)
                    needs_review.pop(k, None)
                    state["last_modified_field"] = k

        # 7. Generate next conversational step & follow-up question
        next_missing = self._find_next_missing_field(fields, values, confirmed_fields)
        state["current_field"] = next_missing.get("name") if next_missing else None

        if newly_filled:
            field_labels = [f.get("label", f.get("name")) for f in fields if f.get("name") in newly_filled]
            if is_user_correction or any(k in confirmed_fields for k in newly_filled):
                if len(newly_filled) == 1:
                    fname = newly_filled[0]
                    ack = f"Updated your {field_labels[0]} to {values.get(fname)}."
                else:
                    ack = f"Updated your {', '.join(field_labels)}."
            else:
                ack = f"Got your {', '.join(field_labels)}."

            if next_missing:
                assistant_reply = f"{ack} What is your {next_missing.get('label')}?"
                state["stage"] = "filling"
            else:
                summary_items = [
                    f"{f.get('label', f.get('name'))}: {values.get(f.get('name'))}"
                    for f in fields if f.get('name') in values and values.get(f.get('name'))
                ]
                summary_snippet = ", ".join(summary_items[:4])
                if len(summary_items) > 4:
                    summary_snippet += f" and {len(summary_items) - 4} more"
                summary_clause = f" ({summary_snippet})" if summary_snippet else ""
                assistant_reply = f"{ack} All required fields are now completed{summary_clause}. Would you like to confirm and submit the form now?"
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
                    # Check if AI identified cleared fields
                    ai_cleared = ai_turn.get("cleared_fields", [])
                    if isinstance(ai_cleared, list):
                        for cf in ai_cleared:
                            target_field = next(
                                (f for f in fields if f.get("name") == cf or f.get("label", "").lower() == str(cf).lower()),
                                None
                            )
                            if target_field:
                                cf_name = target_field.get("name")
                                default_val = False if target_field.get("type") == "checkbox" else ""
                                values[cf_name] = default_val
                                confirmed_fields.discard(cf_name)
                                needs_review.pop(cf_name, None)
                                if cf_name not in cleared_fields:
                                    cleared_fields.append(cf_name)
                                state["last_modified_field"] = cf_name

                    ext = ai_turn.get("extracted_fields", {})
                    for k, v in ext.items():
                        target_field = next((f for f in fields if f.get("name") == k), None)
                        if not target_field:
                            continue

                        ftype = target_field.get("type", "text")
                        is_ident = is_identifier_field(target_field)
                        options = target_field.get("options") or []
                        val_str = str(v).strip()

                        # Reject command sentences extracted by AI as values
                        if is_command_sentence(val_str):
                            continue

                        if is_name_field(target_field):
                            if not is_valid_name(val_str):
                                needs_review[k] = f"'{v}' does not appear to be a valid name."
                                assistant_reply = f"'{v}' does not appear to be a valid name. Please provide your full name."
                                state["current_field"] = k
                                continue
                            v = val_str
                        elif is_ident:
                            words = [w for w in re.split(r"\s+", val_str) if w]
                            norm_id = normalize_spoken_identifier(val_str)
                            if len(words) > 10 or not re.match(r"^[A-Za-z0-9_\-\+]+$", norm_id):
                                continue
                            v = norm_id
                        elif ftype in ("select", "radio") and options:
                            matched_opt, is_ambig = match_dropdown_option(val_str, options)
                            if matched_opt:
                                v = matched_opt
                            else:
                                needs_review[k] = f"'{v}' is not a valid option for {target_field.get('label')}."
                                continue
                        elif ftype == "email":
                            clean_email = val_str.replace(" at the rate ", "@").replace(" at ", "@").replace(" dot ", ".").replace(" ", "").strip(",.;:")
                            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
                                needs_review[k] = f"'{v}' does not appear to be a valid email."
                                assistant_reply = f"'{v}' does not appear to be a valid email. Please provide a valid email address."
                                state["current_field"] = k
                                continue
                            v = clean_email
                        elif ftype in ("phone", "tel") or any(w in k.lower() for w in ["phone", "mobile"]):
                            digits = re.sub(r"[^\d]", "", normalize_spoken_identifier(val_str))
                            if len(digits) < 7 or len(digits) > 15:
                                needs_review[k] = f"'{v}' is not a valid phone number."
                                assistant_reply = f"'{v}' does not appear to be a valid phone number. Please provide a valid phone number."
                                state["current_field"] = k
                                continue
                            v = digits
                        elif ftype == "date":
                            parsed_d = parse_spoken_date(val_str)
                            if parsed_d:
                                v = parsed_d
                            elif not re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
                                needs_review[k] = f"'{v}' is not a valid date."
                                continue
                        elif ftype == "number":
                            try:
                                v = float(val_str) if "." in val_str else int(val_str)
                            except (ValueError, TypeError):
                                needs_review[k] = f"'{v}' is not a valid number."
                                continue

                        is_correction = any(w in text_lower for w in ["change", "replace", "correct", "update", "wrong", "instead"])
                        if k in confirmed_fields and not is_correction:
                            needs_review[k] = f"New value '{v}' proposed for already confirmed field."
                        else:
                            if values.get(k) != v or k not in confirmed_fields:
                                newly_filled.append(k)
                            values[k] = v
                            confirmed_fields.add(k)
                            needs_review.pop(k, None)
                            state["last_modified_field"] = k

                    if not assistant_reply:
                        assistant_reply = ai_turn.get("assistant_response") or ""
                except Exception as e:
                    logger.warning(f"Groq turn fallback: {e}")

            if not assistant_reply:
                if next_missing:
                    assistant_reply = f"I didn't quite catch that. Could you tell me your {next_missing.get('label')}?"
                else:
                    assistant_reply = "All required fields are completed! Would you like to confirm and submit the form now?"
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
            newly_filled=newly_filled,
            cleared_fields=cleared_fields,
            intent=intent,
            state=state,
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
        cleared_fields: Optional[List[str]] = None,
        is_submitted: bool = False,
        submission_id: Optional[int] = None,
        intent: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Missing required list independently validated against fields schema
        missing = [
            f.get("name") for f in fields
            if f.get("required") and (
                values.get(f.get("name")) is None
                or (isinstance(values.get(f.get("name")), str) and not str(values.get(f.get("name"))).strip())
                or values.get(f.get("name")) is False
            )
        ]
        is_completed = len(missing) == 0
        if not is_completed and stage == "confirming_submission":
            stage = "filling"

        history.append({"user": user_transcript, "assistant": reply})
        if len(history) > 20:
            history = history[-20:]

        curr_state = state or {}
        session.state_json = {
            "values": values,
            "confirmed_fields": list(confirmed_fields),
            "needs_review": needs_review,
            "history": history,
            "stage": stage,
            "last_modified_field": curr_state.get("last_modified_field"),
            "current_field": curr_state.get("current_field"),
        }
        db.commit()

        return {
            "session_id": session.id,
            "assistant_response": reply,
            "updated_values": values,
            "newly_filled": newly_filled or [],
            "cleared_fields": cleared_fields or [],
            "confirmed_fields": list(confirmed_fields),
            "missing_fields": missing,
            "needs_review": needs_review,
            "stage": stage,
            "is_completed": is_completed,
            "is_submitted": is_submitted,
            "submission_id": submission_id,
            "last_modified_field": curr_state.get("last_modified_field"),
            "current_field": curr_state.get("current_field"),
            "intent": intent,
        }

    def _detect_field_inquiry(self, text_lower: str, fields: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        cleaned = text_lower.strip()
        # If it's an explicit command or assignment, it's not an inquiry
        if any(cmd in cleaned for cmd in [
            "change my ", "change the ", "change it to", "replace my ", "replace the ",
            "update my ", "update the ", "set my ", "set the ", "my email is", "my name is",
            "my phone is", "my department is", "my date of birth is", "my dob is", "my gender is"
        ]):
            return None

        is_q = (
            cleaned.endswith("?")
            or bool(re.search(r"^(does|do|is|are|was|were|can|could|would|should|how|what|why|did|has|have|check|verify|tell me)\b", cleaned))
            or any(p in cleaned for p in ["feel like", "feels like", "look like", "looks like", "sound like", "is valid", "valid or not", "is correct", "correct or not", "like a name"])
        )
        if not is_q:
            return None

        for f in fields:
            fname = f.get("name")
            flabel = f.get("label", fname)
            aliases = [flabel.lower(), fname.lower().replace("_", " ")]
            if "name" in fname:
                aliases.extend(["name", "full name"])
            if "email" in fname:
                aliases.extend(["email", "email address", "mail id"])
            if "phone" in fname or "mobile" in fname:
                aliases.extend(["phone", "phone number", "mobile", "mobile number"])
            if "dept" in fname or "department" in fname:
                aliases.extend(["department", "dept", "branch", "stream"])
            if "birth" in fname or "dob" in fname or "date" in fname:
                aliases.extend(["date of birth", "dob", "birthday", "date"])
            if "reg" in fname:
                aliases.extend(["register number", "registration number", "reg no"])
            if "gender" in fname:
                aliases.extend(["gender", "sex"])

            for alias in sorted(aliases, key=len, reverse=True):
                if re.search(rf"\b{re.escape(alias)}\b", cleaned):
                    return f
        return None

    def _is_submission_confirmation(self, text_lower: str, current_stage: Optional[str]) -> bool:
        cleaned = text_lower.strip().lower()

        # Never treat corrections or edits as confirmation even if they start with 'yes' or 'sari'
        if any(w in cleaned for w in ["change", "update", "replace", "wrong", "instead", "correction", "மாற்று"]):
            return False
        if any(re.search(rf"\b{re.escape(w)}\b", cleaned) for w in ["correct this", "correct my", "correct it"]):
            return False

        # Direct explicit submit command (English, Tamil, and Tanglish)
        explicit_phrases = [
            "submit the form", "submit form", "submit it", "submit now",
            "confirm submit", "confirm submission", "please submit",
            "go ahead and submit", "proceed to submit", "finish and submit",
            "submit my response", "submit response", "i want to submit",
            # Tanglish
            "submit pannunga", "submit pannidunga", "form submit pannunga",
            "form-ai submit pannunga", "form ah submit pannunga",
            "confirm pannunga", "submit pannidalam", "submit pannalam",
            # Tamil script
            "சமர்ப்பிக்கவும்", "படிவத்தை சமர்ப்பிக்கவும்", "உறுதிப்படுத்தவும்",
            "submit பண்ணுங்க", "submit பண்ணிடுங்க", "படிவம் சமர்ப்பி"
        ]
        if any(phrase in cleaned for phrase in explicit_phrases):
            return True

        # Standalone submit or confirm
        if cleaned in [
            "submit", "confirm", "yes, submit", "yes submit",
            "சமர்ப்பி", "உறுதிப்படுத்து"
        ]:
            return True

        # Only evaluate affirmative answers if currently in reviewing or confirming_submission stage
        if current_stage in ("reviewing", "confirming_submission"):
            affirmative_exact = [
                # English
                "yes", "yeah", "yep", "sure", "ok", "okay", "yup",
                "proceed", "go ahead", "confirm", "yes please",
                "yes submit", "looks good", "everything is correct", "all good",
                # Tanglish
                "aam", "aama", "aamaa", "sari", "seri",
                "sari submit pannunga", "seri submit pannunga", "ellam sari",
                "correct ah irukku", "correct-aa irukku", "correct irukku",
                # Tamil script
                "ஆமாம்", "ஆம்", "சரி", "சரியாக உள்ளது", "சரி சமர்ப்பிக்கவும்"
            ]
            if cleaned in affirmative_exact:
                return True

            # If user begins with an affirmative word, verify it is a brief confirmation
            # and not providing a new sentence or field value (max 4 words)
            affirmative_prefixes = [
                "yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "submit",
                "aam", "aama", "sari", "seri", "ஆமாம்", "ஆம்", "சரி"
            ]
            words = cleaned.split()
            if len(words) <= 4 and any(cleaned.startswith(w) for w in affirmative_prefixes):
                # Ensure no field keywords like email, phone, name are being answered
                field_hints = ["name", "email", "phone", "address", "dept", "department", "பெயர்", "மின்னஞ்சல்"]
                if not any(hint in cleaned for hint in field_hints):
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
        intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        from app.models.submission import Submission
        from app.models.draft import Draft
        from app.services.pdf_service import generate_completed_pdf

        # Strict validation: prevent submission if any required field is missing
        missing = [
            f.get("name") for f in fields
            if f.get("required") and (
                values.get(f.get("name")) is None
                or (isinstance(values.get(f.get("name")), str) and not str(values.get(f.get("name"))).strip())
                or values.get(f.get("name")) is False
            )
        ]
        if missing:
            missing_label = next((f.get("label", f.get("name")) for f in fields if f.get("name") == missing[0]), missing[0])
            reply = f"We cannot submit just yet because your {missing_label} is still required. What is your {missing_label}?"
            return self._build_response(
                session=session,
                db=db,
                values=values,
                confirmed_fields=confirmed_fields,
                needs_review=needs_review,
                fields=fields,
                reply=reply,
                stage="filling",
                history=history,
                user_transcript=transcript,
                newly_filled=newly_filled,
                intent=intent,
            )

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
            "cleared_fields": [],
            "confirmed_fields": list(confirmed_fields),
            "missing_fields": [],
            "needs_review": needs_review,
            "stage": "submitted",
            "is_completed": True,
            "is_submitted": True,
            "submission_id": new_sub.id,
            "intent": intent,
        }


conversation_manager = ConversationManager()
