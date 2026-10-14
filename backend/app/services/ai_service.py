import json
import re
import logging
from typing import Dict, Any, Tuple

from app.core.config import settings
from app.schemas.form import FormSchemaDefinition, FormFieldSchema
from app.services.ai_provider import ai_provider, AIProviderError

logger = logging.getLogger("ai_voice_form.ai_service")


def extract_json_from_ai_text(text: str) -> Dict[str, Any]:
    """Backward-compatible helper to extract JSON from AI text."""
    return ai_provider.extract_json(text)


def generate_demo_form_schema(prompt: str) -> FormSchemaDefinition:
    """
    Deterministic offline demo generator used when AI_DEMO_MODE=True
    or when GROQ_API_KEY is not configured.
    """
    p_lower = prompt.lower()

    # 1. Common pre-configured templates
    if "student" in p_lower:
        title = "Student Registration Form"
        description = "Official student enrollment and departmental registration form"
        fields = [
            FormFieldSchema(name="full_name", label="Full Name", type="text", required=True, placeholder="Enter full name"),
            FormFieldSchema(name="register_number", label="Register Number", type="text", required=True, placeholder="e.g. REG-2026-001"),
            FormFieldSchema(name="department", label="Department", type="select", required=True, options=["Artificial Intelligence & Data Science", "Computer Science & Engineering", "Information Technology", "Electronics & Communication", "Mechanical Engineering"]),
            FormFieldSchema(name="email", label="Email Address", type="email", required=True, placeholder="student@university.edu"),
            FormFieldSchema(name="phone_number", label="Phone Number", type="text", required=True, placeholder="+1 555-0199"),
            FormFieldSchema(name="date_of_birth", label="Date of Birth", type="date", required=True),
            FormFieldSchema(name="gender", label="Gender", type="radio", required=True, options=["Male", "Female", "Non-Binary", "Prefer not to say"]),
        ]
        return FormSchemaDefinition(title=title, description=description, fields=fields)

    if "feedback" in p_lower or "survey" in p_lower:
        title = "Customer Feedback & Survey"
        description = "Share your thoughts and rate your experience with our services"
        fields = [
            FormFieldSchema(name="customer_name", label="Your Name", type="text", required=False, placeholder="Optional"),
            FormFieldSchema(name="email", label="Email Address", type="email", required=True, placeholder="you@domain.com"),
            FormFieldSchema(name="satisfaction_rating", label="Overall Satisfaction", type="radio", required=True, options=["Excellent", "Good", "Average", "Needs Improvement"]),
            FormFieldSchema(name="service_used", label="Service Evaluated", type="select", required=True, options=["Customer Support", "Product Quality", "Delivery Speed", "Website Experience"]),
            FormFieldSchema(name="would_recommend", label="Would you recommend us to a colleague?", type="checkbox", required=False, default_value=True),
            FormFieldSchema(name="comments", label="Detailed Feedback", type="textarea", required=True, placeholder="Describe your experience..."),
        ]
        return FormSchemaDefinition(title=title, description=description, fields=fields)

    if "job" in p_lower or "application" in p_lower or "hiring" in p_lower:
        title = "Job Application Form"
        description = "Career application form for prospective team members"
        fields = [
            FormFieldSchema(name="candidate_name", label="Full Legal Name", type="text", required=True, placeholder="Jane Doe"),
            FormFieldSchema(name="email", label="Email Address", type="email", required=True, placeholder="jane.doe@example.com"),
            FormFieldSchema(name="phone", label="Phone Number", type="text", required=True, placeholder="+1 555-123-4567"),
            FormFieldSchema(name="position", label="Target Position", type="select", required=True, options=["Frontend Engineer", "Backend Developer", "Full Stack AI Engineer", "Product Designer"]),
            FormFieldSchema(name="years_experience", label="Years of Relevant Experience", type="number", required=True, placeholder="3"),
            FormFieldSchema(name="available_start_date", label="Earliest Available Start Date", type="date", required=True),
            FormFieldSchema(name="cover_letter", label="Why are you a great fit?", type="textarea", required=False, placeholder="Write a brief cover letter..."),
        ]
        return FormSchemaDefinition(title=title, description=description, fields=fields)

    # 2. Dynamic token-based schema synthesis
    clean_prompt = re.sub(r"^(create|build|generate|make)\s+(a|an)?\s*", "", p_lower, flags=re.IGNORECASE)
    parts = re.split(r"containing|with|includes|including|fields?:", clean_prompt, maxsplit=1)

    title_raw = parts[0].strip() or "Dynamic Custom Form"
    title = title_raw.title()
    if not title.lower().endswith("form"):
        title += " Form"

    fields = []
    if len(parts) > 1 and parts[1].strip():
        raw_items = re.split(r",|\band\b", parts[1])
        for item in raw_items:
            item_clean = item.strip()
            if not item_clean or len(item_clean) < 2:
                continue

            f_lower = item_clean.lower()
            f_type = "text"
            options = None

            if "email" in f_lower:
                f_type = "email"
            elif any(w in f_lower for w in ["date", "dob", "birth", "deadline"]):
                f_type = "date"
            elif any(w in f_lower for w in ["number", "age", "quantity", "count", "salary", "rating", "gpa"]):
                f_type = "number"
            elif any(w in f_lower for w in ["gender", "sex"]):
                f_type = "radio"
                options = ["Male", "Female", "Other"]
            elif any(w in f_lower for w in ["department", "role", "country", "category"]):
                f_type = "select"
                options = ["Option A", "Option B", "Option C"]
            elif any(w in f_lower for w in ["agree", "terms", "subscribe", "confirm"]):
                f_type = "checkbox"
            elif any(w in f_lower for w in ["message", "comment", "feedback", "description", "note"]):
                f_type = "textarea"

            f_name = re.sub(r"[^a-z0-9_]", "_", f_lower).strip("_")
            f_name = re.sub(r"_+", "_", f_name)[:40] or f"field_{len(fields)+1}"
            f_label = item_clean.strip().title()

            fields.append(
                FormFieldSchema(
                    name=f_name,
                    label=f_label,
                    type=f_type,
                    required=True,
                    placeholder=f"Enter {f_label.lower()}",
                    options=options
                )
            )

    if not fields:
        fields = [
            FormFieldSchema(name="full_name", label="Full Name", type="text", required=True, placeholder="Enter full name"),
            FormFieldSchema(name="email", label="Email Address", type="email", required=True, placeholder="name@domain.com"),
            FormFieldSchema(name="message", label="Message or Notes", type="textarea", required=False, placeholder="Provide any additional details"),
        ]

    return FormSchemaDefinition(
        title=title,
        description=f"Generated based on prompt: '{prompt[:100]}'",
        fields=fields,
    )


def generate_form_schema(prompt: str) -> Tuple[FormSchemaDefinition, bool, str, str]:
    """
    Main form generation entry point.
    Returns: (FormSchemaDefinition, is_demo, provider, message)
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    # If explicit demo mode is enabled
    if settings.AI_DEMO_MODE:
        logger.info("Using deterministic offline Demo Mode generator.")
        schema = generate_demo_form_schema(prompt)
        provider_name = "demo_mode"
        msg = "Generated using deterministic offline Demo Mode. Set GROQ_API_KEY in backend/.env for live Groq AI."
        return schema, True, provider_name, msg

    # If demo mode is not explicitly enabled, check if Groq is configured
    if not ai_provider.is_groq_configured():
        raise AIProviderError(
            "GROQ_API_KEY is not configured on the backend. Please set GROQ_API_KEY in backend/.env or enable AI_DEMO_MODE=True.",
            status_code=503,
            is_retryable=False
        )

    # Live Groq generation
    logger.info(f"Querying Groq API ({settings.GROQ_MODEL}) for form generation...")
    schema = ai_provider.generate_form_schema(prompt)
    return (
        schema,
        False,
        f"groq ({settings.GROQ_MODEL})",
        "Generated successfully using Groq AI."
    )
