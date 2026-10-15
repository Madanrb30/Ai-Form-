import re
import warnings
from datetime import datetime
from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

# Suppress Pydantic warning for schema_json shadowing legacy BaseModel.schema_json method
warnings.filterwarnings(
    "ignore",
    message='Field name "schema_json" in ".*" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)

FieldType = Literal[
    "text",
    "email",
    "number",
    "date",
    "textarea",
    "select",
    "checkbox",
    "radio",
]


class FormFieldSchema(BaseModel):
    name: str = Field(..., description="Unique machine-readable field identifier")
    label: str = Field(..., description="Human-readable field label")
    type: FieldType = Field(..., description="Input control type")
    required: bool = Field(default=False, description="Whether the field is mandatory")
    placeholder: Optional[str] = Field(default=None, description="Input placeholder text")
    options: Optional[List[str]] = Field(default=None, description="Options for select, radio, or multi-checkbox")
    default_value: Optional[Any] = Field(default=None, description="Initial default value")
    source_page: Optional[int] = Field(default=None, description="Source page number where field was detected")
    confidence: Optional[float] = Field(default=None, description="Confidence score between 0.0 and 1.0")
    is_uncertain: Optional[bool] = Field(default=False, description="Flagged for user review if ambiguous")
    extracted_value: Optional[Any] = Field(default=None, description="Extracted filled-in value if present in document")
    is_identifier: Optional[bool] = Field(
        default=False,
        description="Whether this field represents an alphanumeric identifier (register number, student ID, roll number, postal code, phone, etc.)"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip().lower()
        clean = re.sub(r"[^a-z0-9_]", "_", clean)
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = "field"
        if not re.match(r"^[a-z0-9_]{1,64}$", clean):
            raise ValueError("Field name must contain only letters, numbers, and underscores (max 64 chars)")
        return clean

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 128:
            raise ValueError("Field label must be between 1 and 128 characters")
        return v

    @model_validator(mode="after")
    def validate_choice_options(self):
        if self.type in ("select", "radio") and not self.options:
            self.options = ["Option 1", "Option 2"]
        # Automatically detect identifier fields if not explicitly configured
        if not self.is_identifier and is_identifier_field({"name": self.name, "label": self.label}):
            self.is_identifier = True
        return self


IDENTIFIER_KEYWORDS = {
    "reg", "register", "registration", "roll", "roll_no", "roll_number",
    "student_id", "id", "code", "postal", "postal_code", "zip", "zip_code",
    "pin", "pin_code", "phone", "phone_number", "mobile", "mobile_number",
    "contact", "contact_number", "aadhaar", "pan", "ssn", "passport", "license",
    "serial", "account", "account_number"
}


def is_identifier_field(field: Any) -> bool:
    """Helper to detect if a field represents an alphanumeric or numeric identifier."""
    if isinstance(field, dict):
        if field.get("is_identifier"):
            return True
        name = str(field.get("name", "")).lower()
        label = str(field.get("label", "")).lower()
    else:
        if getattr(field, "is_identifier", False):
            return True
        name = str(getattr(field, "name", "")).lower()
        label = str(getattr(field, "label", "")).lower()

    # Do not treat generic names as identifiers
    if name in ("full_name", "first_name", "last_name", "name", "candidate_name", "customer_name", "user_name"):
        return False

    name_tokens = set(re.split(r"[^a-z0-9]+", name))
    label_tokens = set(re.split(r"[^a-z0-9]+", label))
    tokens = name_tokens | label_tokens

    return any(k in tokens for k in IDENTIFIER_KEYWORDS)


def is_name_field(field: Any) -> bool:
    """Helper to detect if a field represents a person's name."""
    if isinstance(field, dict):
        name = str(field.get("name", "")).lower()
        label = str(field.get("label", "")).lower()
    else:
        name = str(getattr(field, "name", "")).lower()
        label = str(getattr(field, "label", "")).lower()

    if any(n in name for n in ["full_name", "first_name", "last_name", "candidate_name", "student_name", "applicant_name", "user_name"]):
        return True
    if name == "name" or label == "name":
        return True
    if "name" in name.split("_") or "name" in label.split():
        excluded = ["file", "form", "dept", "department", "company", "college", "school", "org", "organization"]
        if not any(ex in name or ex in label for ex in excluded):
            return True
    return False


def is_valid_name(val: Any) -> bool:
    """
    Validates whether a string is a genuine personal name.
    Rejects questions, conversational inquiries, sentences, and non-name phrases.
    """
    if not val or not isinstance(val, str) or not val.strip():
        return False
    v = val.strip().lower()

    if "?" in val:
        return False

    question_phrases = [
        "feel like", "feels like", "look like", "looks like", "sound like", "sounds like",
        "like a name", "is valid", "valid or not", "what is", "how is", "is correct",
        "correct or not", "tell me", "check my", "verify my", "does my", "is my",
        "my name", "the name", "a name", "change my", "replace my", "update my", "set my"
    ]
    if any(phrase in v for phrase in question_phrases):
        return False

    if any(v.startswith(p) for p in ["does ", "do ", "is ", "are ", "can ", "could ", "what ", "how ", "why ", "did ", "change ", "replace ", "update ", "set "]):
        return False

    command_words = {"change", "replace", "update", "set", "wrong", "incorrect", "instead", "cancel", "stop"}
    if any(w in command_words for w in re.split(r"\s+", v)):
        return False

    conversational_non_names = {
        "yes", "no", "ok", "okay", "sure", "cancel", "stop", "wait", "hold on",
        "wrong", "incorrect", "a name", "my name", "the name", "name",
        "unknown", "none", "nothing", "skip", "repeat", "fine", "good"
    }
    if v in conversational_non_names:
        return False

    cleaned_chars = re.sub(r"[\s\.\'\-]", "", val)
    if len(cleaned_chars) < 2:
        return False

    if not re.match(r"^[\w\s\.\'\-]+$", val, re.UNICODE):
        return False

    if not any(c.isalpha() for c in val):
        return False

    return True



class FormSchemaDefinition(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Title of the form")
    description: Optional[str] = Field(default=None, max_length=1000, description="Brief description")
    fields: List[FormFieldSchema] = Field(..., min_length=1, max_length=50, description="List of form fields")

    @model_validator(mode="after")
    def validate_unique_field_names(self):
        names = set()
        for f in self.fields:
            if f.name in names:
                base_name = f.name
                counter = 2
                while f"{base_name}_{counter}" in names:
                    counter += 1
                f.name = f"{base_name}_{counter}"
            names.add(f.name)
        return self


class FormGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000, description="Natural language instructions for form")


class FormGenerateResponse(BaseModel):
    schema_data: FormSchemaDefinition
    is_demo: bool
    provider: str
    message: Optional[str] = None


class FormCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    schema_json: FormSchemaDefinition
    is_public: Optional[bool] = Field(default=True, description="Whether the form is publicly viewable and fillable")
    original_document_path: Optional[str] = None


class FormUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    schema_json: Optional[FormSchemaDefinition] = None
    is_public: Optional[bool] = None


class FormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    title: str
    description: Optional[str] = None
    schema_json: FormSchemaDefinition
    user_id: Optional[int] = None
    is_public: bool = True
    original_document_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime



class VoiceMapRequest(BaseModel):
    transcript: str = Field(..., description="Recognized speech transcript to map to form fields")


class VoiceMapResponse(BaseModel):
    mapped_fields: Dict[str, Any]
    transcript: str
    total_fields: int
    matched_count: int


class ConversationTurnRequest(BaseModel):
    transcript: str = Field(..., description="User spoken transcript or typed message")
    session_id: Optional[str] = Field(default=None, description="Current conversation session ID")
    current_values: Optional[Dict[str, Any]] = Field(default=None, description="Client form values state")


class ConversationTurnResponse(BaseModel):
    session_id: str
    assistant_response: str
    updated_values: Dict[str, Any]
    newly_filled: List[str]
    confirmed_fields: List[str]
    missing_fields: List[str]
    needs_review: Dict[str, str]
    stage: str
    is_completed: bool
    is_submitted: bool = False
    submission_id: Optional[int] = None


class DraftSaveRequest(BaseModel):
    values_json: Dict[str, Any]
    session_id: Optional[str] = None


class DraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    form_id: int
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    values_json: Dict[str, Any]
    status: str
    updated_at: datetime


class DocumentExtractResponse(BaseModel):
    schema_data: FormSchemaDefinition
    filename: str
    file_path: str
    detected_fields_count: int
    has_acroform: bool
    message: str
    extraction_strategy: Optional[str] = Field(default="digital_text", description="Strategy used: digital_text, acroform, groq_vision, or hybrid")
    pages_processed: Optional[int] = Field(default=1, description="Number of pages processed")
    uncertain_fields_count: Optional[int] = Field(default=0, description="Number of fields flagged as ambiguous/uncertain")

