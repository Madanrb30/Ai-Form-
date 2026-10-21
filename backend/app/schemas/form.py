import re
import math
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
    "textarea",
    "number",
    "email",
    "phone",
    "date",
    "time",
    "datetime",
    "select",
    "radio",
    "checkbox",
    "url",
]


def normalize_boolean(val: Any) -> Optional[bool]:
    """
    Normalizes arbitrary values to strict booleans without treating
    the string "false", "0", or "no" as True.
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return False
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("true", "1", "yes", "on", "t"):
            return True
        if s in ("false", "0", "no", "off", "f", ""):
            return False
    return bool(val)


def sanitize_json_value(val: Any) -> Any:
    """
    Recursively sanitizes values to ensure strict JSON serializability.
    Converts pypdf objects (ByteStringObject, TextStringObject, NameObject,
    DictionaryObject, ArrayObject), bytes, non-UTF-8 data, and signature
    containers into clean JSON-serializable primitives (str, int, float, bool, None,
    list, dict).
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    if isinstance(val, (bytes, bytearray)):
        # Attempt standard decodings for PDF and binary strings
        for enc in ("utf-16", "utf-8", "latin-1"):
            try:
                decoded = val.decode(enc).strip("\x00").strip()
                if all(ord(c) >= 32 or c in "\n\r\t" for c in decoded):
                    return decoded
            except Exception:
                pass
        # Fallback to UTF-8 with replacement for any remaining non-UTF-8 bytes
        cleaned = val.decode("utf-8", errors="replace").strip("\x00").strip()
        return cleaned if cleaned else None

    # Handle dictionary-like objects (e.g. pypdf DictionaryObject or dict)
    if isinstance(val, dict):
        # Digital signature dictionary (/Type == '/Sig' or contains /Contents)
        if val.get("/Type") == "/Sig" or "/Contents" in val:
            signer = val.get("/Name") or val.get("/Reason")
            return sanitize_json_value(signer) if signer else None

        clean_dict = {}
        for k, v in val.items():
            k_str = str(k).lstrip("/")
            if k_str in ("Contents", "Cert", "ByteRange"):
                continue
            sanitized_v = sanitize_json_value(v)
            if sanitized_v is not None:
                clean_dict[k_str] = sanitized_v
        return clean_dict if clean_dict else None

    # Handle list-like objects (e.g. pypdf ArrayObject, list, tuple, set)
    if isinstance(val, (list, tuple, set)):
        clean_list = [sanitize_json_value(x) for x in val]
        return [x for x in clean_list if x is not None]

    # Handle string-like objects (e.g. pypdf TextStringObject, NameObject, str)
    if isinstance(val, str):
        return str(val).replace("\x00", "").strip()

    # Fallback for other objects: convert to string
    try:
        return str(val)
    except Exception:
        return None


class FormFieldSchema(BaseModel):
    id: Optional[str] = Field(default=None, description="Stable internal field identifier")
    name: str = Field(..., description="Unique machine-readable field identifier")
    label: str = Field(..., description="Human-readable field label")
    type: FieldType = Field(..., description="Input control type")
    required: bool = Field(default=False, description="Whether the field is mandatory")
    placeholder: Optional[str] = Field(default=None, description="Input placeholder text")
    description: Optional[str] = Field(default=None, description="Field help text or instructions")
    options: Optional[List[str]] = Field(default=None, description="Options for select, radio, or multi-checkbox")
    default_value: Optional[Any] = Field(default=None, description="Initial default value")
    min_value: Optional[float] = Field(default=None, description="Minimum numeric value for number fields")
    max_value: Optional[float] = Field(default=None, description="Maximum numeric value for number fields")
    step: Optional[float] = Field(default=None, description="Step increment for number fields")
    min_length: Optional[int] = Field(default=None, description="Minimum character length")
    max_length: Optional[int] = Field(default=None, description="Maximum character length")
    pattern: Optional[str] = Field(default=None, description="Custom regex pattern for validation")
    source_page: Optional[int] = Field(default=None, description="Source page number where field was detected")
    confidence: Optional[float] = Field(default=None, description="Confidence score between 0.0 and 1.0")
    is_uncertain: Optional[bool] = Field(default=False, description="Flagged for user review if ambiguous")
    extracted_value: Optional[Any] = Field(default=None, description="Extracted filled-in value if present in document")
    is_identifier: Optional[bool] = Field(
        default=False,
        description="Whether this field represents an alphanumeric identifier (register number, student ID, roll number, postal code, phone, etc.)"
    )

    @field_validator("extracted_value", "default_value", mode="before")
    @classmethod
    def sanitize_field_values(cls, v: Any) -> Any:
        return sanitize_json_value(v)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: Any) -> str:
        if not v or not isinstance(v, str):
            return "text"
        v_clean = v.strip().lower()
        mapping = {
            "string": "text",
            "str": "text",
            "phone": "phone",
            "tel": "phone",
            "mobile": "phone",
            "telephone": "phone",
            "url": "url",
            "uri": "url",
            "link": "url",
            "website": "url",
            "int": "number",
            "integer": "number",
            "float": "number",
            "decimal": "number",
            "numeric": "number",
            "dropdown": "select",
            "choice": "select",
            "combobox": "select",
            "boolean": "checkbox",
            "bool": "checkbox",
            "multi-line": "textarea",
            "multiline": "textarea",
            "paragraph": "textarea",
            "datetime": "datetime",
            "datetime-local": "datetime",
            "timestamp": "datetime",
            "time": "time",
            "date": "date",
        }
        mapped = mapping.get(v_clean, v_clean)
        allowed = (
            "text",
            "textarea",
            "number",
            "email",
            "phone",
            "date",
            "time",
            "datetime",
            "select",
            "radio",
            "checkbox",
            "url",
        )
        if mapped not in allowed:
            return "text"
        return mapped

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip().lower()
        clean = re.sub(r"[^a-z0-9_]", "_", clean)
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = "field"
        if not re.match(r"^[a-z0-9_]{1,64}$", clean):
            clean = clean[:64].rstrip("_") or "field"
        return clean

    @field_validator("label", mode="before")
    @classmethod
    def validate_label(cls, v: Any) -> str:
        if v is None:
            return "Field"
        v_str = str(v).strip()
        if not v_str:
            return "Field"
        if len(v_str) > 128:
            v_str = v_str[:128].strip()
        return v_str

    @model_validator(mode="after")
    def validate_choice_options(self):
        if not self.id:
            self.id = f"f_{self.name}"

        # 1. Checkbox field handling
        if self.type == "checkbox":
            self.options = None
            self.min_value = None
            self.max_value = None
            self.step = None
            self.min_length = None
            self.max_length = None
            self.pattern = None
            self.default_value = normalize_boolean(self.default_value) if self.default_value is not None else False

        # 2. Select & Radio choice fields
        elif self.type in ("select", "radio"):
            self.min_value = None
            self.max_value = None
            self.step = None
            self.min_length = None
            self.max_length = None
            self.pattern = None

            if not self.options or len(self.options) == 0:
                self.options = ["Option 1", "Option 2"]
            else:
                # Deduplicate while preserving order and rejecting empty options
                seen_opts = set()
                clean_opts = []
                for o in self.options:
                    cleaned_o = str(o).strip()
                    if cleaned_o and cleaned_o not in seen_opts:
                        seen_opts.add(cleaned_o)
                        clean_opts.append(cleaned_o)
                self.options = clean_opts if clean_opts else ["Option 1", "Option 2"]

            # Saved default must belong to the final list of valid options
            if self.default_value is not None:
                val_str = str(self.default_value).strip()
                if val_str in self.options:
                    self.default_value = val_str
                else:
                    self.default_value = None

        # 3. Numeric fields
        elif self.type == "number":
            self.options = None
            self.min_length = None
            self.max_length = None
            self.pattern = None

            if self.min_value is not None:
                if math.isnan(self.min_value) or math.isinf(self.min_value):
                    raise ValueError(f"Field '{self.label}': Minimum value must be a finite number.")
            if self.max_value is not None:
                if math.isnan(self.max_value) or math.isinf(self.max_value):
                    raise ValueError(f"Field '{self.label}': Maximum value must be a finite number.")
            if self.step is not None:
                if math.isnan(self.step) or math.isinf(self.step) or self.step <= 0:
                    raise ValueError(f"Field '{self.label}': Step must be a positive finite number.")
            if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
                raise ValueError(f"Field '{self.label}': Minimum value ({self.min_value}) cannot exceed maximum value ({self.max_value}).")

            if self.default_value is not None and str(self.default_value).strip() != "":
                try:
                    num = float(self.default_value)
                    if math.isnan(num) or math.isinf(num):
                        self.default_value = None
                    else:
                        # Validate against bounds if set
                        if self.min_value is not None and num < self.min_value:
                            self.default_value = None
                        elif self.max_value is not None and num > self.max_value:
                            self.default_value = None
                        else:
                            self.default_value = num
                except (ValueError, TypeError):
                    self.default_value = None
            else:
                self.default_value = None

        # 4. Text & String fields
        elif self.type in ("text", "textarea", "email", "phone", "url"):
            self.options = None
            self.min_value = None
            self.max_value = None
            self.step = None

            if self.min_length is not None:
                if self.min_length < 0:
                    raise ValueError(f"Field '{self.label}': Minimum length cannot be negative.")
            if self.max_length is not None:
                if self.max_length < 0:
                    raise ValueError(f"Field '{self.label}': Maximum length cannot be negative.")
            if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
                raise ValueError(f"Field '{self.label}': Minimum length ({self.min_length}) cannot exceed maximum length ({self.max_length}).")

            if self.pattern and str(self.pattern).strip():
                pat_str = str(self.pattern).strip()
                try:
                    re.compile(pat_str)
                    self.pattern = pat_str
                except re.error as e:
                    raise ValueError(f"Field '{self.label}': Invalid regular expression pattern: {e}")
            else:
                self.pattern = None

            if self.default_value is not None:
                if isinstance(self.default_value, bool):
                    self.default_value = None
                else:
                    self.default_value = str(self.default_value).strip() or None

        # 5. Date / Time fields
        else:
            self.options = None
            self.min_value = None
            self.max_value = None
            self.step = None
            self.min_length = None
            self.max_length = None
            self.pattern = None

            if self.default_value is not None:
                if isinstance(self.default_value, bool):
                    self.default_value = None
                else:
                    self.default_value = str(self.default_value).strip() or None

        # Automatically detect identifier fields if not explicitly configured
        if not self.is_identifier and (self.type == "phone" or is_identifier_field({"name": self.name, "label": self.label})):
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
    category: Optional[str] = Field(default="General", max_length=100, description="Form category (e.g. Education, Careers, General)")
    fields: List[FormFieldSchema] = Field(..., min_length=1, max_length=50, description="List of form fields")

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, v: Any) -> str:
        if v is None:
            return "General"
        v_str = str(v).strip()
        return v_str if v_str else "General"

    @model_validator(mode="after")
    def validate_unique_field_identity(self):
        names = set()
        ids = set()
        for idx, f in enumerate(self.fields):
            # Guarantee stable unique field id
            if not f.id or str(f.id).strip() == "":
                f.id = f"f_{f.name}_{idx + 1}"
            elif f.id in ids:
                base_id = f.id
                counter = 2
                while f"{base_id}_{counter}" in ids:
                    counter += 1
                f.id = f"{base_id}_{counter}"
            ids.add(f.id)

            # Guarantee unique field name
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
    cleared_fields: List[str] = Field(default_factory=list, description="Fields explicitly cleared in this turn")
    intent: Optional[str] = Field(default=None, description="Classified intent of the utterance")


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


class PdfExtractAndMapResponse(BaseModel):
    form_id: int
    extracted_fields: Dict[str, Any]
    confidence_scores: Dict[str, float] = Field(default_factory=dict)
    source_evidence: Dict[str, str] = Field(default_factory=dict)
    needs_review: Dict[str, str] = Field(default_factory=dict)
    missing_required_fields: List[str] = Field(default_factory=list)
    all_missing_fields: List[str] = Field(default_factory=list)
    merged_values: Dict[str, Any] = Field(default_factory=dict)
    total_matched: int
    total_fields: int
    message: str
    extraction_strategy: str = "digital_text"
    pages_processed: int = 1


class FormExportPdfRequest(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict, description="Form values to render in exported PDF")

