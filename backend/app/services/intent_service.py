import re
from typing import Dict, Any, List, Optional, Tuple


class IntentType:
    PROVIDE_VALUE = "PROVIDE_VALUE"
    CORRECT_VALUE = "CORRECT_VALUE"
    CLEAR_FIELD = "CLEAR_FIELD"
    ASK_QUESTION = "ASK_QUESTION"
    CONFIRM_SUBMISSION = "CONFIRM_SUBMISSION"
    CANCEL_SUBMISSION = "CANCEL_SUBMISSION"
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"


def get_field_aliases(f: Dict[str, Any]) -> List[str]:
    """Generates comprehensive case-insensitive aliases for a form field."""
    fname = f.get("name", "")
    flabel = f.get("label", "")
    ftype = f.get("type", "text")
    aliases = [flabel.lower(), fname.lower().replace("_", " ")]

    if "name" in fname or "name" in flabel.lower():
        aliases.extend(["name", "full name", "applicant name", "user name", "பெயர்"])
    if "email" in fname or "email" in flabel.lower():
        aliases.extend(["email", "email address", "mail", "mail id", "மின்னஞ்சல்"])
    if "phone" in fname or "mobile" in fname or "phone" in flabel.lower() or ftype in ("phone", "tel"):
        aliases.extend(["phone", "phone number", "mobile", "mobile number", "contact", "contact number", "தொலைபேசி"])
    if "dept" in fname or "department" in fname or "dept" in flabel.lower() or "department" in flabel.lower():
        aliases.extend(["department", "dept", "branch", "stream", "course", "துறை"])
    if "reg" in fname or "reg" in flabel.lower():
        aliases.extend(["register number", "registration number", "reg no", "register no", "reg number", "roll number", "roll no", "பதிவு எண்"])
    if "roll" in fname or "roll" in flabel.lower():
        aliases.extend(["roll number", "roll no", "roll"])
    if "id" in fname or "student" in fname:
        aliases.extend(["student id", "id number", "id"])
    if "dob" in fname or "birth" in fname or "date" in fname or ftype == "date":
        aliases.extend(["date of birth", "dob", "birthday", "birth date", "date", "பிறந்த தேதி"])
    if "gender" in fname or "gender" in flabel.lower():
        aliases.extend(["gender", "sex", "பாலினம்"])
    if "address" in fname:
        aliases.extend(["address", "residential address", "location", "முகவரி"])
    if "feedback" in fname or "comment" in fname or "notes" in fname:
        aliases.extend(["feedback", "comments", "comment", "notes", "message"])

    return sorted(list(set(a for a in aliases if a.strip())), key=len, reverse=True)


def find_referenced_field(text_lower: str, fields: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Identifies which form field is referenced in the utterance based on aliases."""
    # Strip conversational prefixes
    clean_text = re.sub(
        r"^(?:madan|assistant|hey|hello|hi|please|vanakkam)[,\s]+",
        "",
        text_lower.strip(),
        flags=re.IGNORECASE
    )

    for f in fields:
        for alias in get_field_aliases(f):
            if re.search(rf"\b{re.escape(alias)}\b", clean_text):
                return f
    return None


def is_clear_command(text_lower: str) -> bool:
    """Checks if utterance contains vocabulary or phrasing requesting to clear/remove a field."""
    patterns = [
        r"\b(?:clear|remove|delete|empty|wipe|erase|reset)\b",
        r"\b(?:leave|make|keep)\s+(?:it\s+|the\s+[^.]+\s+)?blank\b",
        r"\b(?:wrong|incorrect|mistake)[,.;\s]+(?:please\s+)?(?:clear|remove|delete|empty|wipe)\b",
        r"\b(?:clear|remove|delete|empty|wipe)\s+(?:the\s+)?(?:data|value|entry|content)\b",
        r"\b(?:clear|remove|delete|empty)\s+(?:this|that|it)\b",
    ]
    return any(re.search(p, text_lower) for p in patterns)


def detect_clear_field(
    transcript: str,
    fields: List[Dict[str, Any]],
    state: Dict[str, Any]
) -> Optional[Tuple[Dict[str, Any], str]]:
    """
    Detects if the utterance is a CLEAR_FIELD command and resolves the target field.
    Returns (target_field_dict, rationale) or None.
    """
    text_lower = transcript.strip().lower()
    if not is_clear_command(text_lower):
        return None

    # 1. Direct field name mention (e.g., "Clear the register number", "Remove the email")
    matched_field = find_referenced_field(text_lower, fields)
    if matched_field:
        return matched_field, f"Direct field match: {matched_field.get('name')}"

    # 2. Relative references: "previous answer", "last field", "clear it", "remove it", "it is wrong, clear it"
    if any(p in text_lower for p in ["previous", "last", "it", "that", "this"]):
        last_mod = state.get("last_modified_field")
        curr = state.get("current_field")
        target_name = last_mod or curr
        if target_name:
            target_obj = next((f for f in fields if f.get("name") == target_name), None)
            if target_obj:
                return target_obj, f"Relative reference resolved to: {target_name}"

    return None


def is_command_sentence(text: str) -> bool:
    """
    Detects if a candidate value string is actually a conversational command / instruction
    rather than a genuine data value.
    """
    t = text.lower().strip()
    if not t:
        return False

    command_patterns = [
        r"\b(?:clear|remove|delete|empty|wipe|erase|reset)\b",
        r"\b(?:data in|value in|in the field|the field)\b",
        r"\b(?:is wrong|was wrong|incorrect|mistake)\b",
        r"\b(?:leave\s+(?:it\s+)?blank)\b",
        r"\b(?:change|replace|update|switch)\s+(?:it|this|that)\b",
    ]
    for p in command_patterns:
        if re.search(p, t):
            return True
    return False


def classify_utterance_intent(
    transcript: str,
    fields: List[Dict[str, Any]],
    state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Classifies a user utterance into one of 7 explicit intents:
    - PROVIDE_VALUE
    - CORRECT_VALUE
    - CLEAR_FIELD
    - ASK_QUESTION
    - CONFIRM_SUBMISSION
    - CANCEL_SUBMISSION
    - GENERAL_CONVERSATION
    """
    text_lower = transcript.strip().lower()
    stage = state.get("stage", "filling")

    # 1. CONFIRM_SUBMISSION (check explicit submit first)
    explicit_submit = [
        "submit the form", "submit form", "submit it", "submit now",
        "confirm submit", "confirm submission", "please submit",
        "proceed to submit", "finish and submit", "submit my response",
        "submit response", "i want to submit", "confirm and submit",
        "submit pannunga", "submit pannidunga", "form submit pannunga",
        "சமர்ப்பிக்கவும்", "படிவத்தை சமர்ப்பிக்கவும்", "உறுதிப்படுத்தவும்"
    ]
    if any(p in text_lower for p in explicit_submit):
        return {
            "intent": IntentType.CONFIRM_SUBMISSION,
            "target_field": None,
            "rationale": "Explicit submit command"
        }
    if stage in ("reviewing", "confirming_submission") and text_lower in [
        "yes", "yeah", "sure", "ok", "okay", "confirm", "proceed", "all good", "looks good",
        "aam", "aama", "sari", "seri", "ஆமாம்", "ஆம்", "சரி"
    ]:
        return {
            "intent": IntentType.CONFIRM_SUBMISSION,
            "target_field": None,
            "rationale": "Affirmative confirmation during review/confirm stage"
        }

    # 2. CANCEL_SUBMISSION
    cancel_words = [
        r"\bno\b", r"\bwait\b", r"\bhold on\b", r"\bnot yet\b",
        r"\bcancel\b", r"\bstop\b", r"\bdon'?t submit\b", r"\bdo not submit\b"
    ]
    if stage in ("reviewing", "confirming_submission") and any(re.search(p, text_lower) for p in cancel_words):
        if not any(w in text_lower for w in ["change", "update", "instead", "replace", "correct", "to", "with"]):
            return {
                "intent": IntentType.CANCEL_SUBMISSION,
                "target_field": None,
                "rationale": "User cancelled or put submission on hold"
            }

    # 3. CLEAR_FIELD
    clear_match = detect_clear_field(transcript, fields, state)
    if clear_match:
        return {
            "intent": IntentType.CLEAR_FIELD,
            "target_field": clear_match[0],
            "rationale": clear_match[1]
        }

    # 4. ASK_QUESTION
    is_q = (
        text_lower.endswith("?")
        or bool(re.search(r"^(?:does|do|is|are|was|were|can|could|would|should|how|what|why|did|has|have|check|verify|tell me)\b", text_lower))
        or any(p in text_lower for p in [
            "feel like", "feels like", "look like", "looks like", "sound like",
            "is valid", "valid or not", "is correct", "like a name"
        ])
    )
    is_cmd_correction = any(w in text_lower for w in [
        "change my", "change the", "replace my", "replace the",
        "update my", "update the", "set my", "set the", "to", "with", "instead"
    ])
    if is_q and not is_cmd_correction:
        inquiry_field = find_referenced_field(text_lower, fields)
        return {
            "intent": IntentType.ASK_QUESTION,
            "target_field": inquiry_field,
            "rationale": "User inquired about field or form status"
        }

    # 5. GENERAL_CONVERSATION
    greeting_patterns = [
        r"\bstart\b", r"\bhello\b", r"\bhi\b", r"\bhey\b",
        r"\bvanakkam\b", r"வணக்கம்", r"\bthank you\b", r"\bthanks\b", r"\bhelp\b"
    ]
    if not text_lower or (any(re.search(p, text_lower) for p in greeting_patterns) and not find_referenced_field(text_lower, fields)):
        return {
            "intent": IntentType.GENERAL_CONVERSATION,
            "target_field": None,
            "rationale": "Greeting or general conversational acknowledgement"
        }

    # 6. CORRECT_VALUE
    corr_patterns = [
        r"\b(?:change|replace|update|correct)\s+(?:the\s+|my\s+)?",
        r"\b(?:is wrong|was wrong|incorrect)[,.;\s]+(?:change|replace|update|set|make|to)\b",
        r"\b(?:should be|instead of)\b",
    ]
    if any(re.search(p, text_lower) for p in corr_patterns):
        ref_field = find_referenced_field(text_lower, fields)
        return {
            "intent": IntentType.CORRECT_VALUE,
            "target_field": ref_field,
            "rationale": "User expressed explicit correction"
        }

    # 7. PROVIDE_VALUE (default for slot filling)
    ref_field = find_referenced_field(text_lower, fields)
    return {
        "intent": IntentType.PROVIDE_VALUE,
        "target_field": ref_field,
        "rationale": "Default value provision"
    }
