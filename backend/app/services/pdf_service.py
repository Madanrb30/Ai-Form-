import os
import io
import html
import logging
from typing import Tuple, List, Dict, Any, Optional
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from app.core.config import settings
from app.schemas.form import FormSchemaDefinition, FormFieldSchema
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
        total_pages = len(reader.pages)
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
    submission_id: int,
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
