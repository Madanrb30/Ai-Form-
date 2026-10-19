import os
import io
import re
import html
import logging
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from app.core.config import settings
from app.schemas.form import (
    FormSchemaDefinition,
    FormFieldSchema,
    is_identifier_field,
    is_name_field,
    is_valid_name,
)
from app.services.ai_provider import ai_provider, AIProviderError
from app.services.ai_service import generate_demo_form_schema
import pypdfium2 as pdfium
from PIL import Image

logger = logging.getLogger("ai_voice_form.pdf_service")


def extract_pdf_content(file_bytes: bytes) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts text and any existing AcroForm interactive fields from PDF.
    Returns: (extracted_text, detected_fields)
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    if reader.is_encrypted:
        raise ValueError("The uploaded PDF is password-protected or encrypted. Please upload an unencrypted document.")
    text_content = []
    detected_fields = []

    # 1. Extract plain text across pages
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_content.append(f"--- Page {i+1} ---\n{page_text}")

    full_text = "\n\n".join(text_content).strip()

    # 2. Check for AcroForm fields
    try:
        acro_form = reader.get_fields()
        if acro_form:
            for field_name, field_data in acro_form.items():
                detected_fields.append({
                    "name": field_name,
                    "type": field_data.get("/FT", "text"),
                    "value": field_data.get("/V", None),
                })
    except Exception as e:
        logger.warning(f"Could not read AcroForm fields: {e}")

    return full_text, detected_fields


def analyze_pdf_pages(file_bytes: bytes) -> Dict[str, Any]:
    """
    Analyzes PDF pages for selectable text and AcroForm fields.
    Classifies pages into digital vs scanned.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise ValueError("The uploaded PDF is password-protected or encrypted. Please upload an unencrypted document.")
        total_pages = len(reader.pages)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Corrupted or invalid PDF document: {str(e)}")

    if total_pages > settings.MAX_DOCUMENT_PAGES:
        raise ValueError(f"Document has {total_pages} pages, which exceeds the maximum limit of {settings.MAX_DOCUMENT_PAGES} pages.")

    digital_pages = []
    scanned_pages = []
    page_texts = {}
    full_text_parts = []

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        txt = (page.extract_text() or "").strip()
        page_texts[page_num] = txt
        if len(txt) >= 25:
            digital_pages.append(page_num)
            full_text_parts.append(f"--- Page {page_num} ---\n{txt}")
        else:
            scanned_pages.append(page_num)

    acro_fields = []
    try:
        fields_dict = reader.get_fields()
        if fields_dict:
            for field_name, field_data in fields_dict.items():
                acro_fields.append({
                    "name": field_name,
                    "type": field_data.get("/FT", "text"),
                    "value": field_data.get("/V", None),
                })
    except Exception as e:
        logger.warning(f"Could not read AcroForm fields: {e}")

    return {
        "total_pages": total_pages,
        "digital_pages": digital_pages,
        "scanned_pages": scanned_pages,
        "acro_fields": acro_fields,
        "page_texts": page_texts,
        "full_text": "\n\n".join(full_text_parts).strip(),
    }


def render_pdf_page_to_image(file_bytes: bytes, page_num: int) -> bytes:
    """
    Renders a single PDF page (1-indexed) into JPEG bytes using pypdfium2.
    Falls back to pypdf embedded image extraction if rendering fails.
    """
    page_idx = page_num - 1
    try:
        doc = pdfium.PdfDocument(file_bytes)
        if page_idx < 0 or page_idx >= len(doc):
            raise ValueError(f"Page index {page_num} out of bounds")
        page = doc[page_idx]
        pil_img = page.render(scale=2.0).to_pil()
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    except Exception as render_err:
        logger.warning(f"pypdfium2 rendering failed for page {page_num}: {render_err}, checking embedded images.")
        reader = PdfReader(io.BytesIO(file_bytes))
        page = reader.pages[page_idx]
        if page.images and len(page.images) > 0:
            return page.images[0].data
        raise ValueError(f"Could not render or extract image for PDF page {page_num}: {render_err}")


def validate_and_read_image(file_bytes: bytes) -> bytes:
    """Validates uploaded image file bytes and returns normalized JPEG bytes."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
    except Exception as e:
        raise ValueError(f"Invalid or corrupted image file: {str(e)}")

    img = Image.open(io.BytesIO(file_bytes))
    if img.width < 32 or img.height < 32:
        raise ValueError("Image dimensions must be at least 32x32 pixels.")

    max_dim = settings.MAX_IMAGE_DIMENSION
    if img.width > max_dim or img.height > max_dim:
        scale = max_dim / max(img.width, img.height)
        new_size = (max(32, int(img.width * scale)), max(32, int(img.height * scale)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def process_document_hybrid(
    file_bytes: bytes,
    filename: str,
    ext: str
) -> Tuple[FormSchemaDefinition, str, str, int, int]:
    """
    Executes hybrid document extraction strategy:
    - Image Upload: Image validation + Groq Vision model
    - Digital PDF: Local pypdf text + Groq text model (or AcroForm interactive fields)
    - Scanned PDF: In-memory image rendering + Groq Vision model
    - Hybrid PDF: Text extraction on digital pages + Vision OCR on scanned pages
    Returns: (schema_data, strategy, message, pages_processed, uncertain_count)
    """
    # 0. Text Document Processing
    if ext == ".txt":
        txt_content = file_bytes.decode("utf-8", errors="ignore").strip()
        if not txt_content:
            raise ValueError("Uploaded text document is empty.")
        if ai_provider.is_groq_configured():
            schema = ai_provider.extract_document_schema(txt_content, filename)
            msg = "Fields extracted from text document using Groq AI."
        else:
            schema = generate_demo_form_schema(f"Text Document: {filename}\n{txt_content[:1000]}")
            msg = "Fields extracted from text document (Demo Mode)."
        return schema, "digital_text", msg, 1, 0

    # 1. Image Document Processing
    if ext in (".png", ".jpg", ".jpeg"):
        norm_img = validate_and_read_image(file_bytes)
        if not ai_provider.is_groq_configured():
            if settings.AI_DEMO_MODE:
                schema = generate_demo_form_schema(f"Image Form: {filename}")
                return schema, "groq_vision", "Image processed in Demo Mode (GROQ_API_KEY not configured).", 1, 0
            raise AIProviderError("GROQ_API_KEY is not configured on server. Image OCR requires a valid Groq API key.", status_code=503)

        schema = ai_provider.extract_form_from_images([norm_img], filename, [1])
        uncertain = sum(1 for f in schema.fields if f.is_uncertain)
        msg = f"Form fields extracted using Groq Vision OCR ({settings.GROQ_VISION_MODEL})."
        return schema, "groq_vision", msg, 1, uncertain

    # 2. PDF Document Processing
    analysis = analyze_pdf_pages(file_bytes)
    total_pages = analysis["total_pages"]
    digital_pages = analysis["digital_pages"]
    scanned_pages = analysis["scanned_pages"]
    acro_fields = analysis["acro_fields"]
    full_text = analysis["full_text"]

    # 2A. Interactive AcroForm
    if acro_fields:
        fields = []
        for f in acro_fields:
            field_name = f["name"]
            ftype = "text"
            if f.get("type") in ("/Btn", "checkbox"):
                ftype = "checkbox"
            elif f.get("type") in ("/Ch", "select"):
                ftype = "select"
            fields.append(FormFieldSchema(
                name=field_name,
                label=field_name.replace("_", " ").title(),
                type=ftype,
                required=False,
                source_page=1,
                confidence=1.0,
                is_uncertain=False,
                extracted_value=f.get("value"),
            ))
        title = filename.replace(".pdf", "").replace("_", " ").title()
        schema = FormSchemaDefinition(
            title=title,
            description=f"Interactive PDF AcroForm fields extracted directly from {filename}.",
            fields=fields,
        )
        msg = f"Extracted {len(fields)} interactive AcroForm field(s) directly from PDF."
        return schema, "acroform", msg, total_pages, 0

    # 2B. Pure Digital PDF (all pages have selectable text)
    if len(scanned_pages) == 0 and full_text:
        if ai_provider.is_groq_configured():
            schema = ai_provider.extract_document_schema(full_text, filename)
            msg = "Fields extracted successfully from digital PDF text using Groq AI."
        else:
            schema = generate_demo_form_schema(f"Form for {filename}\n{full_text[:1000]}")
            msg = "Fields extracted from digital PDF using document structure analyzer (Demo Mode)."
        return schema, "digital_text", msg, total_pages, 0

    # 2C. Pure Scanned PDF (all pages are scanned)
    if len(digital_pages) == 0:
        if not ai_provider.is_groq_configured():
            if settings.AI_DEMO_MODE:
                schema = generate_demo_form_schema(f"Scanned Form: {filename}")
                msg = "Scanned PDF detected. Processed in Demo Mode (GROQ_API_KEY not configured)."
                return schema, "groq_vision", msg, total_pages, 0
            raise AIProviderError("GROQ_API_KEY is not configured on server. Scanned PDF OCR requires a valid Groq API key.", status_code=503)

        page_images = [render_pdf_page_to_image(file_bytes, p) for p in scanned_pages]
        schema = ai_provider.extract_form_from_images(page_images, filename, scanned_pages)
        uncertain = sum(1 for f in schema.fields if f.is_uncertain)
        msg = f"Scanned PDF converted and parsed using Groq Vision OCR ({settings.GROQ_VISION_MODEL}) across {total_pages} page(s)."
        return schema, "groq_vision", msg, total_pages, uncertain

    # 2D. Hybrid PDF (mixed digital and scanned pages)
    # Extract digital text
    digital_text = "\n\n".join(f"Page {p}:\n{analysis['page_texts'][p]}" for p in digital_pages)
    if ai_provider.is_groq_configured():
        digital_schema = ai_provider.extract_document_schema(digital_text, filename)
    else:
        digital_schema = generate_demo_form_schema(f"Hybrid Form: {filename}")

    # Tag source_page for digital fields
    for f in digital_schema.fields:
        if not f.source_page:
            f.source_page = digital_pages[0] if digital_pages else 1

    # Extract scanned pages with vision
    if ai_provider.is_groq_configured():
        try:
            scanned_images = [render_pdf_page_to_image(file_bytes, p) for p in scanned_pages]
            vision_schema = ai_provider.extract_form_from_images(scanned_images, filename, scanned_pages)
            seen_names = {f.name for f in digital_schema.fields}
            combined_fields = list(digital_schema.fields)
            for vf in vision_schema.fields:
                if vf.name not in seen_names:
                    seen_names.add(vf.name)
                    combined_fields.append(vf)
            digital_schema.fields = combined_fields
            uncertain = sum(1 for f in digital_schema.fields if f.is_uncertain)
            msg = f"Hybrid extraction: {len(digital_pages)} digital page(s) and {len(scanned_pages)} scanned page(s) processed."
            return digital_schema, "hybrid", msg, total_pages, uncertain
        except Exception as vision_err:
            logger.warning(f"Vision extraction failed for scanned pages in hybrid document: {vision_err}")
            msg = f"Hybrid extraction partial: Digital pages extracted; scanned pages {scanned_pages} incomplete ({str(vision_err)})."
            return digital_schema, "hybrid_partial", msg, total_pages, 0

    return digital_schema, "hybrid", f"Extracted digital pages {digital_pages}; scanned pages {scanned_pages} require Groq Vision API key.", total_pages, 0


def generate_completed_pdf(
    form_title: str,
    form_description: Optional[str],
    fields_schema: List[Dict[str, Any]],
    response_data: Dict[str, Any],
    submission_id: Any,
    original_pdf_path: Optional[str] = None
) -> str:
    """
    Generates a professional completed PDF document of the form submission.
    If original PDF had fillable AcroForm fields, tries to fill them;
    otherwise generates a clean, publication-ready PDF summary using ReportLab.
    """
    out_filename = f"submission_{submission_id}.pdf"
    out_path = os.path.join(settings.UPLOAD_DIR, out_filename)

    # 1. Check if original PDF has AcroForms to fill (with path traversal guard)
    if original_pdf_path:
        real_upload_dir = os.path.realpath(settings.UPLOAD_DIR)
        real_orig_path = os.path.realpath(original_pdf_path)
        if (real_orig_path.startswith(real_upload_dir) or os.path.dirname(real_orig_path) == real_upload_dir) and os.path.exists(real_orig_path):
            try:
                reader = PdfReader(real_orig_path)
                if reader.get_fields():
                    writer = PdfWriter()
                    writer.append(reader)
                    # Map fields
                    field_dict = {}
                    for f in fields_schema:
                        fname = f.get("name")
                        if fname in response_data:
                            field_dict[fname] = str(response_data[fname])
                    writer.update_page_form_field_values(writer.pages[0], field_dict)
                    with open(out_path, "wb") as f_out:
                        writer.write(f_out)
                    return out_path
            except Exception as e:
                logger.warning(f"AcroForm filling failed, falling back to clean ReportLab PDF: {e}")

    # 2. Generate standard clean PDF with ReportLab
    doc = SimpleDocTemplate(
        out_path,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#111111"),
    )
    desc_style = ParagraphStyle(
        "DocDesc",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#737373"),
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#999999"),
    )
    label_style = ParagraphStyle(
        "FieldLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#333333"),
    )
    val_style = ParagraphStyle(
        "FieldValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111111"),
    )

    story = []

    # Title & Metadata (HTML escaped for ReportLab Paragraph safety)
    safe_title = html.escape(form_title or "Form Submission")
    story.append(Paragraph(safe_title, title_style))
    if form_description:
        safe_desc = html.escape(form_description)
        story.append(Spacer(1, 4))
        story.append(Paragraph(safe_desc, desc_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Official Submission ID: #{submission_id} • AI Voice Form Assistant", meta_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E5E5"), spaceAfter=14))

    # Table of responses
    table_data = [[
        Paragraph("<b>Field Name</b>", label_style),
        Paragraph("<b>Submitted Value</b>", label_style),
    ]]

    for f in fields_schema:
        fname = f.get("name")
        flabel = f.get("label", fname)
        val = response_data.get(fname, "")
        if isinstance(val, bool):
            display_val = "Yes / Confirmed" if val else "No / Declined"
        elif val is None or str(val).strip() == "":
            display_val = "—"
        else:
            display_val = str(val)

        safe_flabel = html.escape(str(flabel))
        safe_display_val = html.escape(display_val)
        table_data.append([
            Paragraph(safe_flabel, label_style),
            Paragraph(safe_display_val, val_style),
        ])

    col_widths = [2.5 * inch, 4.5 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F7F7F7")),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E5E5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]))

    story.append(t)
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E5E5"), spaceAfter=8))
    story.append(Paragraph("This document was generated automatically by the AI Voice Form Assistant upon verified user confirmation.", meta_style))

    doc.build(story)
    logger.info(f"Generated completed PDF at {out_path}")
    return out_path


# ==============================================================================
# PDF PERSONAL INFORMATION EXTRACTION & PUBLISHED-FORM MAPPING SERVICE
# ==============================================================================

MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12
}


def normalize_document_text(text: str) -> str:
    """
    Normalizes extracted PDF text without losing critical dates, numbers,
    names, email addresses, or alphanumeric identifiers.
    """
    if not text:
        return ""
    # Replace carriage returns and weird unicode whitespace
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[\u200b\u200c\u200d\uFEFF]", "", cleaned)  # zero-width chars
    cleaned = re.sub(r"[ \t]+", " ", cleaned)  # collapse horizontal whitespace
    # Clean up excessive newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Strip non-printable control characters except newline and tab
    cleaned = "".join(ch for ch in cleaned if ch in ("\n", "\t") or ch.isprintable())
    return cleaned.strip()


def parse_and_normalize_date(date_str: str) -> Optional[str]:
    """
    Normalizes various date strings into ISO format YYYY-MM-DD.
    Returns None if the string cannot be reliably parsed.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    d = date_str.strip().strip(",.;")

    # 1. YYYY-MM-DD or YYYY/MM/DD
    m1 = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", d)
    if m1:
        y, m, day = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= day <= 31:
            return f"{y:04d}-{m:02d}-{day:02d}"

    # 2. DD-MM-YYYY or DD/MM/YYYY
    m2 = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", d)
    if m2:
        day, m, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= day <= 31:
            return f"{y:04d}-{m:02d}-{day:02d}"

    # 3. Textual months: "15th August 1998", "August 15, 1998", "15 Aug 1998"
    m3 = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(\d{4})", d)
    if m3:
        day = int(m3.group(1))
        month_name = m3.group(2).lower()
        y = int(m3.group(3))
        if month_name in MONTH_MAP and 1 <= day <= 31 and 1900 <= y <= 2100:
            return f"{y:04d}-{MONTH_MAP[month_name]:02d}-{day:02d}"

    m4 = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})", d)
    if m4:
        month_name = m4.group(1).lower()
        day = int(m4.group(2))
        y = int(m4.group(3))
        if month_name in MONTH_MAP and 1 <= day <= 31 and 1900 <= y <= 2100:
            return f"{y:04d}-{MONTH_MAP[month_name]:02d}-{day:02d}"

    return None


def extract_personal_info_rule_based(text: str, form_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic rule-based extractor for personal information.
    Used for offline Demo Mode, test suites, or as a reliable fallback when AI is unavailable.
    Detects ambiguity and multiple matches, flagging them in needs_review.
    """
    extracted: Dict[str, Any] = {}
    confidence: Dict[str, float] = {}
    evidence: Dict[str, str] = {}
    needs_review: Dict[str, str] = {}

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Global regex pattern matchers
    # 1. Emails
    email_matches = list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)))
    # 2. Phone numbers (10 digits or formatted with country code)
    phone_matches = list(set(re.findall(r"(?:(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})", text)))
    phone_clean = []
    for p in phone_matches:
        digits = re.sub(r"\D", "", p)
        if 10 <= len(digits) <= 13:
            phone_clean.append(p.strip())
    phone_clean = list(set(phone_clean))

    for field in form_fields:
        fname = field.get("name", "").lower()
        flabel = field.get("label", "").lower()
        ftype = field.get("type", "text")
        foptions = field.get("options") or []
        is_id = field.get("is_identifier", False) or is_identifier_field(field)
        is_name = is_name_field(field)

        # ----------------- EMAIL FIELD -----------------
        if ftype == "email" or "email" in fname or "email" in flabel:
            if len(email_matches) == 1:
                extracted[field["name"]] = email_matches[0]
                confidence[field["name"]] = 0.98
                evidence[field["name"]] = f"Found email: {email_matches[0]}"
            elif len(email_matches) > 1:
                needs_review[field["name"]] = f"Multiple email addresses detected ({', '.join(email_matches[:2])}). Please select the primary email."

        # ----------------- PHONE / CONTACT NUMBER -----------------
        elif "phone" in fname or "mobile" in fname or "contact" in fname:
            if len(phone_clean) == 1:
                extracted[field["name"]] = phone_clean[0]
                confidence[field["name"]] = 0.95
                evidence[field["name"]] = f"Found phone number: {phone_clean[0]}"
            elif len(phone_clean) > 1:
                needs_review[field["name"]] = f"Multiple phone numbers detected in document ({', '.join(phone_clean[:2])}). Please verify your primary contact."

        # ----------------- DATE / DATE OF BIRTH -----------------
        elif ftype == "date" or "dob" in fname or "birth" in fname:
            dob_pattern = re.search(
                r"(?:date\s+of\s+birth|dob|birth\s*date|born\s*on|born)[\s:]+([^\n,]+)",
                text,
                re.IGNORECASE
            )
            parsed_date = None
            if dob_pattern:
                raw_d = dob_pattern.group(1).strip()
                parsed_date = parse_and_normalize_date(raw_d)
                if parsed_date:
                    extracted[field["name"]] = parsed_date
                    confidence[field["name"]] = 0.95
                    evidence[field["name"]] = f"Found date of birth from '{raw_d}'"
                else:
                    needs_review[field["name"]] = f"Date of birth '{raw_d}' found but could not be parsed into YYYY-MM-DD. Please confirm."
            else:
                # Look for standalone dates in document
                date_candidates = re.findall(r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})\b", text)
                if len(date_candidates) == 1:
                    norm = parse_and_normalize_date(date_candidates[0])
                    if norm:
                        extracted[field["name"]] = norm
                        confidence[field["name"]] = 0.85
                        evidence[field["name"]] = f"Found date: {norm}"
                elif len(date_candidates) > 1:
                    needs_review[field["name"]] = f"Multiple dates found in document ({', '.join(date_candidates[:2])}). Please verify."

        # ----------------- PERSON NAME -----------------
        elif is_name:
            # Check explicit name labels: "Name: John Doe", "Full Name: John Doe", "Applicant Name: John Doe"
            name_pattern = re.search(
                r"(?:full\s+name|candidate\s+name|applicant\s+name|student\s+name|name)[\s:]+([A-Za-z\s.'-]+)",
                text,
                re.IGNORECASE
            )
            candidate_name = None
            if name_pattern:
                raw_n = name_pattern.group(1).split("\n")[0].strip()
                # Stop at other label keywords
                raw_n = re.split(r"(?:email|phone|dob|date|address|dept|reg)", raw_n, flags=re.IGNORECASE)[0].strip()
                if is_valid_name(raw_n):
                    candidate_name = raw_n

            # If no labeled name, check top 3 lines of document for a personal name
            if not candidate_name and lines:
                for line in lines[:4]:
                    clean_line = re.sub(r"^(?:curriculum\s+vitae|resume|biodata|profile)\s*", "", line, flags=re.IGNORECASE).strip()
                    if is_valid_name(clean_line) and len(clean_line.split()) in (2, 3, 4):
                        candidate_name = clean_line
                        break

            if candidate_name:
                extracted[field["name"]] = candidate_name.title()
                confidence[field["name"]] = 0.95
                evidence[field["name"]] = f"Extracted name: {candidate_name.title()}"

        # ----------------- IDENTIFIER (Register No, Roll No, Student ID) -----------------
        elif is_id:
            id_pattern = re.search(
                r"(?:register\s*no|register\s*number|reg\s*no|roll\s*no|roll\s*number|student\s*id|id\s*number|employee\s*id)[\s:]*([A-Za-z0-9_-]+)",
                text,
                re.IGNORECASE
            )
            if id_pattern:
                id_val = id_pattern.group(1).strip()
                extracted[field["name"]] = id_val
                confidence[field["name"]] = 0.95
                evidence[field["name"]] = f"Found identifier: {id_val}"

        # ----------------- DROPDOWN / SELECT / RADIO -----------------
        elif ftype in ("select", "radio") and foptions:
            matched_opts = []
            for opt in foptions:
                opt_clean = opt.strip()
                # Check exact option or acronym/word match
                opt_lower = opt_clean.lower()
                # e.g. "Computer Science & Engineering" -> "computer science" or "cse"
                acronym = "".join(w[0] for w in re.split(r"[\s&,-]+", opt_clean) if w)
                pattern = rf"\b{re.escape(opt_lower)}\b"
                if re.search(pattern, text, re.IGNORECASE):
                    matched_opts.append(opt_clean)
                elif len(acronym) >= 2 and re.search(rf"\b{re.escape(acronym)}\b", text, re.IGNORECASE):
                    matched_opts.append(opt_clean)
                elif "male" in opt_lower and not ("female" in opt_lower) and re.search(r"\b(?:gender|sex)[\s:]*male\b", text, re.IGNORECASE):
                    matched_opts.append(opt_clean)
                elif "female" in opt_lower and re.search(r"\b(?:gender|sex)[\s:]*female\b", text, re.IGNORECASE):
                    matched_opts.append(opt_clean)

            # Deduplicate matched options
            matched_opts = list(set(matched_opts))
            if len(matched_opts) == 1:
                extracted[field["name"]] = matched_opts[0]
                confidence[field["name"]] = 0.92
                evidence[field["name"]] = f"Matched allowed option: '{matched_opts[0]}'"
            elif len(matched_opts) > 1:
                needs_review[field["name"]] = f"Multiple possible options detected in document: {', '.join(matched_opts)}. Please pick the correct option."

        # ----------------- ADDRESS / LOCATION / CITY -----------------
        elif "address" in fname or "address" in flabel:
            addr_match = re.search(
                r"(?:residential\s+address|permanent\s+address|address)[\s:]+([^\n]+(?:\n[^\n]+)?)",
                text,
                re.IGNORECASE
            )
            if addr_match:
                addr_val = re.sub(r"\s+", " ", addr_match.group(1)).strip()
                extracted[field["name"]] = addr_val[:150]
                confidence[field["name"]] = 0.90
                evidence[field["name"]] = f"Found address: {addr_val[:50]}..."

        elif "city" in fname or "city" in flabel:
            city_match = re.search(r"(?:city|location|town)[\s:]+([A-Za-z\s]+)", text, re.IGNORECASE)
            if city_match:
                city_val = city_match.group(1).split("\n")[0].strip()
                extracted[field["name"]] = city_val.title()
                confidence[field["name"]] = 0.90
                evidence[field["name"]] = f"Found city: {city_val.title()}"

        # ----------------- CHECKBOX -----------------
        elif ftype == "checkbox":
            if any(w in text.lower() for w in ["confirm", "declare", "agree", "certified that", "true to the best"]):
                extracted[field["name"]] = True
                confidence[field["name"]] = 0.90
                evidence[field["name"]] = "Declaration/confirmation statement found in document"

        # ----------------- EDUCATION / DEGREE / INSTITUTION / SKILLS -----------------
        elif any(k in fname or k in flabel for k in ["degree", "qualification", "education"]):
            deg_match = re.search(r"(?:degree|qualification|education)[\s:]+([^\n]+)", text, re.IGNORECASE)
            if deg_match:
                deg_val = deg_match.group(1).strip()
                extracted[field["name"]] = deg_val
                confidence[field["name"]] = 0.90
                evidence[field["name"]] = f"Found qualification: {deg_val}"

        elif any(k in fname or k in flabel for k in ["college", "university", "institution", "school"]):
            inst_match = re.search(r"(?:college|university|institute|school)[\s:]+([^\n]+)", text, re.IGNORECASE)
            if inst_match:
                inst_val = inst_match.group(1).strip()
                extracted[field["name"]] = inst_val
                confidence[field["name"]] = 0.90
                evidence[field["name"]] = f"Found institution: {inst_val}"

        elif any(k in fname or k in flabel for k in ["skills", "skill"]):
            skill_match = re.search(r"(?:technical\s+skills|skills)[\s:]+([^\n]+)", text, re.IGNORECASE)
            if skill_match:
                skill_val = skill_match.group(1).strip()
                extracted[field["name"]] = skill_val
                confidence[field["name"]] = 0.88
                evidence[field["name"]] = f"Found skills: {skill_val[:50]}..."

    return {
        "extracted_fields": extracted,
        "confidence_scores": confidence,
        "source_evidence": evidence,
        "needs_review": needs_review,
    }


def extract_and_map_pdf_personal_info(
    file_bytes: bytes,
    filename: str,
    form_schema: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extracts personal information from an uploaded PDF and maps it strictly
    to the authorized field definitions of the selected published form.

    Enforces:
    - PDF structure & magic byte verification (%PDF-)
    - Rejection of encrypted / password-protected PDFs with clear message
    - Hybrid extraction: Digital text parsing with fallback to Groq Vision OCR for scanned pages
    - Text normalization preserving dates, numbers, and identifiers
    - AI-powered structured field mapping using Groq LLM (or deterministic demo mode)
    - Ambiguity flagging (multiple conflicting candidates marked for review)
    - Missing-field identification for required and optional fields
    - Strict validation against authorized form schema
    """
    if not file_bytes or len(file_bytes) == 0:
        raise ValueError("Uploaded PDF document is empty (0 bytes).")

    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF file structure. File content does not match a valid PDF document.")

    # 1. Analyze PDF pages & extract selectable text
    analysis = analyze_pdf_pages(file_bytes)
    total_pages = analysis["total_pages"]
    digital_pages = analysis["digital_pages"]
    scanned_pages = analysis["scanned_pages"]
    raw_text = analysis["full_text"]

    strategy = "digital_text"

    # 2. Check if scanned pages require OCR
    if (len(digital_pages) == 0 or len(scanned_pages) > 0) and scanned_pages:
        if ai_provider.is_groq_configured():
            try:
                logger.info(f"Rendering {len(scanned_pages)} scanned page(s) for Vision OCR extraction...")
                scanned_images = [render_pdf_page_to_image(file_bytes, p) for p in scanned_pages]
                # Extract text using Groq Vision
                vision_schema = ai_provider.extract_form_from_images(scanned_images, filename, scanned_pages)
                vision_text_snippets = []
                for f in vision_schema.fields:
                    val_str = f" {f.extracted_value}" if f.extracted_value else ""
                    vision_text_snippets.append(f"{f.label}: {val_str}")
                if vision_text_snippets:
                    raw_text = (raw_text + "\n\n" + "\n".join(vision_text_snippets)).strip()
                strategy = "groq_vision" if len(digital_pages) == 0 else "hybrid"
            except Exception as ocr_err:
                logger.warning(f"Vision OCR on scanned PDF pages failed: {ocr_err}")

    normalized_text = normalize_document_text(raw_text)

    # 3. Check for empty extractable text
    if not normalized_text or len(normalized_text.strip()) < 10:
        # Check if there are AcroForm fields
        if analysis.get("acro_fields"):
            acro_text_lines = []
            for af in analysis["acro_fields"]:
                if af.get("value"):
                    acro_text_lines.append(f"{af['name']}: {af['value']}")
            normalized_text = "\n".join(acro_text_lines)
            strategy = "acroform"

    if not normalized_text or len(normalized_text.strip()) < 10:
        raise ValueError(
            "The uploaded PDF contains no readable text or recognizable personal information. "
            "Please ensure the PDF is not blank or corrupted."
        )

    form_fields = form_schema.get("fields", [])
    if not form_fields:
        raise ValueError("Selected form has no field definitions to map information to.")

    # 4. Extract personal details using AI provider or rule-based fallback
    ai_result = None
    use_live_ai = ai_provider.is_groq_configured() and not settings.AI_DEMO_MODE

    if use_live_ai:
        try:
            logger.info(f"Extracting personal information for form fields via Groq AI ({settings.GROQ_MODEL})...")
            ai_result = ai_provider.extract_personal_info_for_form(
                document_text=normalized_text,
                form_fields=form_fields,
                filename=filename,
            )
        except AIProviderError as ai_err:
            logger.warning(f"Live AI extraction failed ({ai_err.message}), falling back to deterministic extractor.")
        except Exception as e:
            logger.warning(f"Unexpected error in live AI extraction ({e}), falling back to deterministic extractor.")

    if not ai_result or not ai_result.get("extracted_fields"):
        # Fallback to rule-based extractor
        rule_result = extract_personal_info_rule_based(normalized_text, form_fields)
        if not ai_result:
            ai_result = rule_result
            if not use_live_ai:
                strategy = "demo_mode" if settings.AI_DEMO_MODE else "digital_text"
        else:
            # Merge rule-based matches if AI missed obvious fields like email or phone
            for k, v in rule_result["extracted_fields"].items():
                if k not in ai_result["extracted_fields"]:
                    ai_result["extracted_fields"][k] = v
                    ai_result["confidence_scores"][k] = rule_result["confidence_scores"].get(k, 0.9)
                    ai_result["source_evidence"][k] = rule_result["source_evidence"].get(k, "Rule-based pattern")
            for k, rev in rule_result["needs_review"].items():
                if k not in ai_result["needs_review"] and k not in ai_result["extracted_fields"]:
                    ai_result["needs_review"][k] = rev

    raw_extracted = ai_result.get("extracted_fields") or {}
    confidence_scores = ai_result.get("confidence_scores") or {}
    source_evidence = ai_result.get("source_evidence") or {}
    needs_review = ai_result.get("needs_review") or {}

    # 5. Schema validation, type compatibility, and constraints enforcement
    fields_by_name = {f["name"]: f for f in form_fields}
    valid_extracted: Dict[str, Any] = {}

    for name, val in raw_extracted.items():
        if name not in fields_by_name:
            # Drop hallucinated or unrequested fields
            continue

        field_def = fields_by_name[name]
        ftype = field_def.get("type", "text")
        foptions = field_def.get("options") or []
        flabel = field_def.get("label", name)

        if val is None or str(val).strip() == "":
            continue

        # Type-specific validation
        if ftype == "email":
            sval = str(val).strip()
            if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", sval):
                valid_extracted[name] = sval
            else:
                needs_review[name] = f"Extracted value '{sval}' is not a valid email address. Please review."

        elif ftype == "date":
            norm_date = parse_and_normalize_date(str(val))
            if norm_date:
                valid_extracted[name] = norm_date
            else:
                needs_review[name] = f"Date value '{val}' could not be normalized to YYYY-MM-DD. Please review."

        elif ftype == "number" and not is_identifier_field(field_def):
            try:
                num_val = float(str(val).strip())
                if num_val.is_integer():
                    valid_extracted[name] = int(num_val)
                else:
                    valid_extracted[name] = num_val
            except ValueError:
                needs_review[name] = f"Expected numeric value for '{flabel}', but received '{val}'."

        elif ftype in ("select", "radio") and foptions:
            sval = str(val).strip()
            # Exact or case-insensitive match
            matched_opt = None
            for opt in foptions:
                if sval.lower() == opt.lower():
                    matched_opt = opt
                    break
            if not matched_opt:
                # Substring or acronym match
                for opt in foptions:
                    if opt.lower() in sval.lower() or sval.lower() in opt.lower():
                        matched_opt = opt
                        break

            if matched_opt:
                valid_extracted[name] = matched_opt
            else:
                needs_review[name] = (
                    f"Extracted '{sval}' for '{flabel}', but it does not match allowed options: "
                    f"{', '.join(foptions[:3])}."
                )

        elif ftype == "checkbox":
            if isinstance(val, bool):
                valid_extracted[name] = val
            elif str(val).lower() in ("true", "1", "yes", "confirmed"):
                valid_extracted[name] = True
            else:
                valid_extracted[name] = False

        else:
            # Text / textarea
            valid_extracted[name] = str(val).strip()

    # 6. Compute missing fields
    missing_required: List[str] = []
    all_missing: List[str] = []

    for field in form_fields:
        fname = field["name"]
        is_req = field.get("required", False)
        val = valid_extracted.get(fname)
        is_empty = (val is None or str(val).strip() == "" or (isinstance(val, list) and len(val) == 0))

        if is_empty:
            all_missing.append(fname)
            if is_req:
                missing_required.append(fname)

    total_matched = len(valid_extracted)
    total_fields = len(form_fields)
    msg = (
        f"Extracted {total_matched} field(s) from '{filename}'. "
        f"{len(missing_required)} required field(s) remain incomplete."
        if missing_required else
        f"Extracted all required fields from '{filename}' successfully."
    )

    return {
        "extracted_fields": valid_extracted,
        "confidence_scores": confidence_scores,
        "source_evidence": source_evidence,
        "needs_review": needs_review,
        "missing_required_fields": missing_required,
        "all_missing_fields": all_missing,
        "strategy": strategy,
        "pages_processed": total_pages,
        "message": msg,
    }
