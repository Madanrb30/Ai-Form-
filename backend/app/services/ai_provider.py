import json
import re
import io
import base64
import logging
from typing import Dict, Any, Tuple, Optional, List
from PIL import Image
from groq import Groq, AuthenticationError, RateLimitError, APIError, APIConnectionError, APITimeoutError

from app.core.config import settings
from app.schemas.form import FormSchemaDefinition, FormFieldSchema

logger = logging.getLogger("ai_voice_form.ai_provider")

SYSTEM_FORM_GEN_PROMPT = """You are an expert form architect. Convert the user's natural language request into a clean, structured JSON form schema.
You MUST output ONLY a valid JSON object matching this schema:
{
  "title": "Short descriptive title",
  "description": "Brief description of the form",
  "fields": [
    {
      "name": "snake_case_field_name",
      "label": "Human Readable Label",
      "type": "text | email | number | date | textarea | select | checkbox | radio",
      "required": true or false,
      "placeholder": "Helpful placeholder",
      "options": ["Option 1", "Option 2"] // only for select, radio, or checkbox
    }
  ]
}

Supported field types:
- "text": single-line strings (name, register number, address, etc.)
- "email": email addresses
- "number": numeric values (age, salary, experience, rating, etc.)
- "date": dates (date of birth, start date, etc.)
- "textarea": multi-line text (comments, cover letter, feedback, etc.)
- "select": dropdown single-choice
- "radio": radio buttons
- "checkbox": boolean consent or toggle

Ensure all field names are unique snake_case strings.
Do not wrap your output in markdown code fences or backticks. Return raw JSON.
"""

SYSTEM_CONVERSATIONAL_PROMPT = """You are an intelligent, empathetic voice form filling assistant for the form: "{form_title}".
Your goal is to guide the user naturally through filling this form.

Current form fields and metadata:
{field_statuses}

User's last spoken statement: "{user_speech}"

Strict Extraction & Field Rules:
1. Identify any field values mentioned by the user and extract them.
2. Alphanumeric Identifiers (register numbers, student IDs, roll numbers, postal codes, phone numbers):
   - Preserve letters, digits, leading zeros, and meaningful separators exactly as strings.
   - NEVER convert identifiers into integers or floating-point numbers. Do not remove leading zeros.
   - If spoken with spaces or separated characters (e.g. 'A 1 2 3 4 5' or '23 AD 045' or '6 3 6 0 0 1'), format as a clean single identifier string (e.g. 'A12345', '23AD045', '636001').
   - If an identifier is ambiguous or incomplete, set "needs_confirmation": true and ask the user to clarify or repeat.
3. Dropdown & Select Fields:
   - You MUST ONLY select one of the EXACT allowed options specified in the field metadata.
   - NEVER invent new options that are not in the field's allowed options.
   - Map spoken abbreviations, acronyms, and variations (e.g. "Artificial Intelligence and Data Science" -> "AI&DS", "Electronics and Communication Engineering" -> "ECE") strictly to the exact allowed option.
   - If the user specifies an option that is not listed, do NOT populate the field; politely ask the user to choose from the available options.
   - Never silently select the first option as a fallback.
4. Field Types & Validation:
   - Numbers: Only parse as numbers if the field is an ordinary numeric quantity (age, experience, salary, count, rating).
   - Email: Validate format (user@domain.com).
   - Date: Format as YYYY-MM-DD.
5. Conversation State:
   - Do not overwrite or modify existing confirmed values for unrelated fields unless the user specifically asks to change them.
6. Compose a concise, friendly spoken response (1-2 sentences):
   - Acknowledge what was just filled or corrected.
   - If an invalid option or ambiguous value was mentioned, ask for clarification clearly.
   - If missing required fields remain, ask for the next missing field clearly.
   - If all required fields are filled, invite the user to review and submit the form.

You MUST respond strictly with a JSON object in this format:
{{
  "extracted_fields": {{
    "field_name": "extracted_value"
  }},
  "assistant_response": "What you speak to the user",
  "needs_confirmation": false,
  "confidence_notes": "Brief explanation if anything was ambiguous or invalid"
}}
"""

SYSTEM_DOCUMENT_EXTRACTION_PROMPT = """You are a document understanding AI. Analyze the provided document text and extract all detectable form fields into a structured JSON form schema.

Output ONLY a valid JSON object:
{
  "title": "Document Title",
  "description": "Form description based on document content",
  "fields": [
    {
      "name": "snake_case_field_name",
      "label": "Human Readable Label",
      "type": "text | email | number | date | textarea | select | checkbox | radio",
      "required": true or false,
      "placeholder": "Helpful placeholder",
      "options": ["Option 1", "Option 2"]
    }
  ]
}
"""

SYSTEM_OCR_VISION_PROMPT = """You are a rigorous, highly accurate document OCR and form extraction engine.
Analyze the provided document image(s) and extract all legitimate form fields, input areas, checkboxes, and fillable blanks into a structured JSON form schema.

Strict Guidelines:
1. Extract only real form fields evidenced by labels, fill-in underlines, bounding boxes, or checkboxes in the document.
2. DO NOT invent, hallucinate, or assume fields that are not visually present in the document.
3. DO NOT mark a field as required unless the document explicitly shows an asterisk (*), "required", or mandatory wording. Blank fields are NOT automatically required.
4. If a field label is blurred, ambiguous, or uncertain, mark "is_uncertain": true and provide your best reading.
5. If a field already has handwritten or printed filled-in content, capture it in "extracted_value".
6. Supported types: "text", "email", "number", "date", "textarea", "select", "checkbox", "radio".
7. Ensure all field names are clean, unique snake_case identifiers.

Output format (strictly valid JSON object):
{
  "title": "Document Title",
  "description": "Brief description based strictly on document content",
  "fields": [
    {
      "name": "snake_case_name",
      "label": "Human Readable Label",
      "type": "text | email | number | date | textarea | select | checkbox | radio",
      "required": false,
      "placeholder": "Optional hint",
      "options": ["Option 1", "Option 2"],
      "is_uncertain": false,
      "confidence": 0.95,
      "extracted_value": null
    }
  ]
}
"""


class AIProviderError(ValueError):
    def __init__(self, message: str, status_code: int = 500, is_retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.is_retryable = is_retryable


class AIProviderService:
    def __init__(self):
        self.client: Optional[Groq] = None

    def _get_client(self) -> Groq:
        api_key = settings.GROQ_API_KEY.strip()
        if not api_key or api_key == "your_actual_groq_api_key":
            raise AIProviderError(
                "GROQ_API_KEY is not configured on the backend. Please add your key to backend/.env",
                status_code=503,
                is_retryable=False
            )
        return Groq(api_key=api_key, timeout=25.0)

    def is_groq_configured(self) -> bool:
        api_key = settings.GROQ_API_KEY.strip()
        return bool(api_key and api_key != "your_actual_groq_api_key")

    def extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Sanitizes and extracts valid JSON from model response."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                return json.loads(match.group(0))
            raise AIProviderError("AI model returned malformed non-JSON output.", status_code=502)

    def generate_form_schema(self, prompt: str) -> FormSchemaDefinition:
        """Generates validated FormSchemaDefinition using Groq LLM."""
        client = self._get_client()
        model_name = settings.GROQ_MODEL

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_FORM_GEN_PROMPT},
                    {"role": "user", "content": f"Generate form for request: {prompt.strip()}"}
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content
            data = self.extract_json(raw_text)
            validated = FormSchemaDefinition(**data)
            return validated
        except AuthenticationError as e:
            logger.error(f"Groq authentication error: {e}")
            raise AIProviderError("Invalid Groq API Key configured on server.", status_code=401)
        except RateLimitError as e:
            logger.error(f"Groq rate limit exceeded: {e}")
            raise AIProviderError("Groq API rate limit exceeded. Please try again shortly.", status_code=429, is_retryable=True)
        except APIConnectionError as e:
            logger.error(f"Groq connection error: {e}")
            raise AIProviderError("Could not connect to Groq AI service. Network timeout.", status_code=504, is_retryable=True)
        except APIError as e:
            logger.error(f"Groq API error: {e}")
            raise AIProviderError(f"Groq service error: {e.message}", status_code=502)
        except Exception as e:
            logger.error(f"Unexpected error in generate_form_schema: {e}")
            raise AIProviderError(f"Form generation failed: {str(e)}", status_code=500)

    def extract_document_schema(self, document_text: str, filename: str) -> FormSchemaDefinition:
        """Extracts schema from raw document text using Groq LLM."""
        client = self._get_client()
        model_name = settings.GROQ_MODEL
        trimmed_text = document_text[:12000]

        try:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_DOCUMENT_EXTRACTION_PROMPT},
                        {
                            "role": "user",
                            "content": f"Document Filename: {filename}\n\nDocument Content:\n{trimmed_text}"
                        }
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    timeout=settings.DOCUMENT_PROCESSING_TIMEOUT,
                )
            except APIError as api_err:
                if "model_not_found" in str(api_err) or "does not exist" in str(api_err):
                    logger.info(f"Model {model_name} not available, falling back to {settings.GROQ_VISION_MODEL}")
                    response = client.chat.completions.create(
                        model=settings.GROQ_VISION_MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_DOCUMENT_EXTRACTION_PROMPT},
                            {
                                "role": "user",
                                "content": f"Document Filename: {filename}\n\nDocument Content:\n{trimmed_text}"
                            }
                        ],
                        temperature=0.1,
                        response_format={"type": "json_object"},
                        timeout=settings.DOCUMENT_PROCESSING_TIMEOUT,
                    )
                else:
                    raise

            raw_text = response.choices[0].message.content
            data = self.extract_json(raw_text)
            return FormSchemaDefinition(**data)
        except AuthenticationError as e:
            logger.error(f"Groq authentication error in document extraction: {e}")
            raise AIProviderError("Invalid Groq API Key configured on server.", status_code=401)
        except RateLimitError as e:
            logger.error(f"Groq rate limit exceeded in document extraction: {e}")
            raise AIProviderError("Groq API rate limit exceeded. Please try again shortly.", status_code=429, is_retryable=True)
        except (APIConnectionError, APITimeoutError) as e:
            logger.error(f"Groq connection error in document extraction: {e}")
            raise AIProviderError("Could not connect to Groq AI service. Network timeout.", status_code=504, is_retryable=True)
        except APIError as e:
            logger.error(f"Groq API error in document extraction: {e}")
            raise AIProviderError(f"Groq service error: {e.message}", status_code=502)
        except AIProviderError:
            raise
        except Exception as e:
            logger.error(f"Document extraction error via Groq: {e}")
            raise AIProviderError(f"Failed to extract fields from document: {str(e)}", status_code=500)

    def _prepare_image_for_vision(self, image_bytes: bytes) -> str:
        """Validates, resizes if needed, and encodes image to JPEG base64 data URI."""
        try:
            img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            raise AIProviderError(f"Corrupted or invalid image data: {str(e)}", status_code=400)

        # Minimum dimension requirement for Groq vision models (32px)
        if img.width < 32 or img.height < 32:
            raise AIProviderError("Image dimensions are too small (minimum 32x32 pixels required).", status_code=400)

        # Resize oversized images preserving text legibility
        max_dim = settings.MAX_IMAGE_DIMENSION
        if img.width > max_dim or img.height > max_dim:
            scale = max_dim / max(img.width, img.height)
            new_size = (max(32, int(img.width * scale)), max(32, int(img.height * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        if img.mode != "RGB":
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_str}"

    def extract_form_from_images(
        self,
        images: List[bytes],
        filename: str,
        page_numbers: Optional[List[int]] = None
    ) -> FormSchemaDefinition:
        """
        Extracts structured form fields from one or more document images using Groq Vision API.
        Enforces controlled batching, page tracking, and non-hallucinated OCR extraction.
        """
        if not self.is_groq_configured():
            raise AIProviderError(
                "GROQ_API_KEY is not configured on the server. Groq Vision OCR requires a valid API key.",
                status_code=503
            )

        if not images:
            raise AIProviderError("No document images provided for vision extraction.", status_code=400)

        client = self._get_client()
        model_name = settings.GROQ_VISION_MODEL
        page_nums = page_numbers or list(range(1, len(images) + 1))

        all_fields: List[FormFieldSchema] = []
        overall_title = None
        overall_desc = None
        seen_names = set()

        batch_size = max(1, settings.IMAGE_BATCH_SIZE)

        for i in range(0, len(images), batch_size):
            batch_images = images[i:i + batch_size]
            batch_pages = page_nums[i:i + batch_size]

            user_content = [
                {
                    "type": "text",
                    "text": (
                        f"Document: {filename} (Page(s): {', '.join(str(p) for p in batch_pages)}).\n"
                        "Carefully examine this document page and extract all authentic form fields into structured JSON."
                    )
                }
            ]

            for img_bytes in batch_images:
                data_uri = self._prepare_image_for_vision(img_bytes)
                user_content.append({"type": "image_url", "image_url": {"url": data_uri}})

            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_OCR_VISION_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    timeout=settings.DOCUMENT_PROCESSING_TIMEOUT,
                )
                raw_text = response.choices[0].message.content
                data = self.extract_json(raw_text)

                if not overall_title and data.get("title"):
                    overall_title = data.get("title")
                if not overall_desc and data.get("description"):
                    overall_desc = data.get("description")

                current_page = batch_pages[0] if batch_pages else 1
                for f_data in data.get("fields", []):
                    if not isinstance(f_data, dict):
                        continue
                    if "source_page" not in f_data or not f_data["source_page"]:
                        f_data["source_page"] = current_page

                    try:
                        f_obj = FormFieldSchema(**f_data)
                        if f_obj.name not in seen_names:
                            seen_names.add(f_obj.name)
                            all_fields.append(f_obj)
                    except Exception as val_err:
                        logger.warning(f"Skipping invalid extracted vision field: {val_err}")

            except AuthenticationError as e:
                logger.error(f"Groq vision authentication error: {e}")
                raise AIProviderError("Invalid Groq API Key configured on server.", status_code=401)
            except RateLimitError as e:
                logger.error(f"Groq vision rate limit exceeded: {e}")
                raise AIProviderError("Groq Vision API rate limit exceeded. Please try again shortly.", status_code=429, is_retryable=True)
            except (APIConnectionError, APITimeoutError) as e:
                logger.error(f"Groq vision connection timeout: {e}")
                raise AIProviderError("Could not connect to Groq Vision service. Network timeout.", status_code=504, is_retryable=True)
            except APIError as e:
                logger.error(f"Groq vision API error: {e}")
                raise AIProviderError(f"Groq Vision service error: {e.message}", status_code=502)
            except AIProviderError:
                raise
            except Exception as e:
                logger.error(f"Groq vision document extraction error: {e}")
                raise AIProviderError(f"Vision OCR processing failed: {str(e)}", status_code=500)

        if not all_fields:
            raise AIProviderError("No form fields could be detected in the document image(s).", status_code=422)

        title = overall_title or f"Extracted Form - {filename}"
        desc = overall_desc or f"Form fields extracted via Groq Vision OCR from {filename}."

        return FormSchemaDefinition(
            title=title,
            description=desc,
            fields=all_fields
        )

    def process_conversation_turn(
        self,
        form_title: str,
        field_statuses: str,
        user_speech: str
    ) -> Dict[str, Any]:
        """Performs stateful conversational follow-up and field extraction."""
        client = self._get_client()
        model_name = settings.GROQ_MODEL

        system_prompt = SYSTEM_CONVERSATIONAL_PROMPT.format(
            form_title=form_title,
            field_statuses=field_statuses,
            user_speech=user_speech
        )

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_speech}
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content
            return self.extract_json(raw_text)
        except AuthenticationError as e:
            logger.error(f"Groq authentication error in conversation turn: {e}")
            raise AIProviderError("Invalid Groq API Key configured on server.", status_code=401)
        except RateLimitError as e:
            logger.error(f"Groq rate limit exceeded in conversation turn: {e}")
            raise AIProviderError("Groq API rate limit exceeded. Please try again shortly.", status_code=429, is_retryable=True)
        except APIConnectionError as e:
            logger.error(f"Groq connection error in conversation turn: {e}")
            raise AIProviderError("Could not connect to Groq AI service. Network timeout.", status_code=504, is_retryable=True)
        except APIError as e:
            logger.error(f"Groq API error in conversation turn: {e}")
            raise AIProviderError(f"Groq service error: {e.message}", status_code=502)
        except Exception as e:
            logger.warning(f"Groq conversational turn failed: {e}")
            raise AIProviderError(f"Conversational processing error: {str(e)}", status_code=500)

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribes audio using Groq's cloud-hosted whisper-large-v3-turbo API.
        Does NOT run any local model (zero PyTorch/Whisper local inference).
        """
        if not audio_bytes or len(audio_bytes) == 0:
            raise AIProviderError("Audio recording is empty (0 bytes).", status_code=400)

        if len(audio_bytes) > settings.MAX_AUDIO_SIZE_BYTES:
            max_mb = settings.MAX_AUDIO_SIZE_BYTES // (1024 * 1024)
            raise AIProviderError(f"Audio file exceeds maximum size limit of {max_mb} MB.", status_code=413)

        client = self._get_client()
        model_name = settings.GROQ_TRANSCRIPTION_MODEL

        kwargs = {}
        if language and language.strip():
            kwargs["language"] = language.strip()
        if prompt and prompt.strip():
            kwargs["prompt"] = prompt.strip()

        try:
            transcription = client.audio.transcriptions.create(
                model=model_name,
                file=(filename, audio_bytes, content_type),
                response_format="verbose_json",
                temperature=0.0,
                **kwargs
            )

            text = getattr(transcription, "text", "") or ""
            duration = getattr(transcription, "duration", None)
            detected_lang = getattr(transcription, "language", None)

            return {
                "text": text.strip(),
                "model": model_name,
                "duration": duration,
                "language": detected_lang or language or "en",
            }
        except AuthenticationError as e:
            logger.error(f"Groq authentication error in transcription: {e}")
            raise AIProviderError("Invalid Groq API Key configured on server.", status_code=401)
        except RateLimitError as e:
            logger.error(f"Groq rate limit exceeded in transcription: {e}")
            raise AIProviderError("Groq Whisper API rate limit exceeded. Please try again shortly.", status_code=429, is_retryable=True)
        except APIConnectionError as e:
            logger.error(f"Groq connection error in transcription: {e}")
            raise AIProviderError("Could not connect to Groq Speech-to-Text service. Network timeout.", status_code=504, is_retryable=True)
        except APIError as e:
            logger.error(f"Groq API error in transcription: {e}")
            raise AIProviderError(f"Groq Whisper service error: {e.message}", status_code=502)
        except Exception as e:
            logger.error(f"Audio transcription failed: {e}")
            raise AIProviderError(f"Speech transcription failed: {str(e)}", status_code=500)


ai_provider = AIProviderService()

