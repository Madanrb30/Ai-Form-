import io
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.models.form import Form
from app.models.submission import Submission
from app.models.user import User


def sanitize_for_excel(val: Any) -> Any:
    """
    Prevent spreadsheet formula injection (CWE-1236).
    If a string value begins with '=', '+', '-', '@', '\t', or '\r',
    prepend a single quote (') so spreadsheet applications interpret it
    as literal text rather than executable formula/macro.
    Native numbers and booleans are preserved safely.
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, (dict, list)):
        import json
        s = json.dumps(val, ensure_ascii=False)
    else:
        s = str(val)

    # Check for leading formula injection characters
    stripped = s.lstrip()
    if stripped and stripped[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s


def generate_submissions_excel(
    form: Form,
    submissions: List[Submission],
    user_map: Dict[int, User],
    current_user: User,
) -> io.BytesIO:
    """
    Generate a professional multi-worksheet XLSX workbook for form submissions.
    
    Worksheets:
    1. 'Submission Summary'
       - Submission ID
       - Respondent Name
       - Respondent Email
       - Submission Date
       - Status
    
    2. 'Response Details'
       - Submission ID
       - Field Identifier
       - Field Label
       - Field Value
    
    Formatting:
    - Bold headers with dark background (#111111) and white text matching B&W theme
    - Freeze panes below headers ('A2')
    - Auto-filter enabled on both sheets
    - Auto-adjusted column widths
    - Proper date formatting
    - Full Unicode preservation (e.g. Tamil text)
    - Spreadsheet formula injection protection
    """
    wb = Workbook()

    # Sheet 1: Submission Summary
    ws_summary = wb.active
    ws_summary.title = "Submission Summary"

    # Sheet 2: Response Details
    ws_details = wb.create_sheet(title="Response Details")

    # Styling definitions matching minimalist black-and-white theme
    header_fill = PatternFill(start_color="111111", end_color="111111", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    data_font = Font(name="Calibri", size=10, color="111111")
    data_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=False)

    thin_side = Side(border_style="thin", color="E5E5E5")
    cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # Sheet 1 Headers
    summary_headers = [
        "Submission ID",
        "Respondent Name",
        "Respondent Email",
        "Submission Date",
        "Status",
    ]
    ws_summary.append(summary_headers)
    ws_summary.row_dimensions[1].height = 26

    for col_idx in range(1, len(summary_headers) + 1):
        cell = ws_summary.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = cell_border

    ws_summary.freeze_panes = "A2"

    # Sheet 2 Headers
    details_headers = [
        "Submission ID",
        "Field Identifier",
        "Field Label",
        "Field Value",
    ]
    ws_details.append(details_headers)
    ws_details.row_dimensions[1].height = 26

    for col_idx in range(1, len(details_headers) + 1):
        cell = ws_details.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = cell_border

    ws_details.freeze_panes = "A2"

    # Schema field mappings
    fields_list = (form.schema_json or {}).get("fields", [])
    label_map = {}
    for f in fields_list:
        if isinstance(f, dict) and "name" in f:
            label_map[f["name"]] = f.get("label", f["name"])

    is_admin = current_user.role in ["ADMIN", "SUPER_ADMIN"]
    is_owner = form.user_id is not None and form.user_id == current_user.id
    can_view_all_respondents = is_admin or is_owner

    # Populate rows
    for sub in submissions:
        # Determine respondent info based on role & ownership permissions
        if sub.user_id:
            sub_user = user_map.get(sub.user_id)
            if can_view_all_respondents or sub.user_id == current_user.id:
                resp_name = sub_user.full_name if (sub_user and sub_user.full_name) else f"User #{sub.user_id}"
                resp_email = sub_user.email if sub_user else "—"
            else:
                resp_name = "Confidential User"
                resp_email = "—"
        else:
            resp_name = "Guest / Anonymous"
            resp_email = "N/A"

        date_str = (
            sub.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            if isinstance(sub.created_at, datetime)
            else str(sub.created_at)
        )
        status_str = "Completed"

        # Sheet 1: Append summary row
        summary_row = [
            sub.id,
            sanitize_for_excel(resp_name),
            sanitize_for_excel(resp_email),
            date_str,
            status_str,
        ]
        ws_summary.append(summary_row)
        curr_sum_row = ws_summary.max_row
        ws_summary.row_dimensions[curr_sum_row].height = 20
        for col_idx in range(1, len(summary_row) + 1):
            c = ws_summary.cell(row=curr_sum_row, column=col_idx)
            c.font = data_font
            c.alignment = center_align if col_idx in (1, 4, 5) else data_align
            c.border = cell_border

        # Sheet 2: Append response details rows
        resp_data = sub.response_json or {}
        handled_keys = set()
        for f in fields_list:
            if isinstance(f, dict) and "name" in f:
                k = f["name"]
                handled_keys.add(k)
                raw_v = resp_data.get(k, "")
                f_label = f.get("label", k)

                detail_row = [
                    sub.id,
                    sanitize_for_excel(k),
                    sanitize_for_excel(f_label),
                    sanitize_for_excel(raw_v),
                ]
                ws_details.append(detail_row)
                curr_det_row = ws_details.max_row
                ws_details.row_dimensions[curr_det_row].height = 20
                for c_idx in range(1, len(detail_row) + 1):
                    c = ws_details.cell(row=curr_det_row, column=c_idx)
                    c.font = data_font
                    c.alignment = center_align if c_idx == 1 else data_align
                    c.border = cell_border

        # Include any extra keys not in schema
        for k, raw_v in resp_data.items():
            if k not in handled_keys:
                detail_row = [
                    sub.id,
                    sanitize_for_excel(k),
                    sanitize_for_excel(k.replace("_", " ").title()),
                    sanitize_for_excel(raw_v),
                ]
                ws_details.append(detail_row)
                curr_det_row = ws_details.max_row
                ws_details.row_dimensions[curr_det_row].height = 20
                for c_idx in range(1, len(detail_row) + 1):
                    c = ws_details.cell(row=curr_det_row, column=c_idx)
                    c.font = data_font
                    c.alignment = center_align if c_idx == 1 else data_align
                    c.border = cell_border

    # Empty state handling
    if len(submissions) == 0:
        empty_row_summary = ["", "No submissions found matching criteria.", "", "", ""]
        ws_summary.append(empty_row_summary)
        r1 = ws_summary.max_row
        for c_idx in range(1, 6):
            c = ws_summary.cell(row=r1, column=c_idx)
            c.font = Font(name="Calibri", size=10, italic=True, color="737373")
            c.border = cell_border

        empty_row_details = ["", "No response details available.", "", ""]
        ws_details.append(empty_row_details)
        r2 = ws_details.max_row
        for c_idx in range(1, 5):
            c = ws_details.cell(row=r2, column=c_idx)
            c.font = Font(name="Calibri", size=10, italic=True, color="737373")
            c.border = cell_border

    # Auto-filter configuration
    ws_summary.auto_filter.ref = f"A1:E{max(ws_summary.max_row, 1)}"
    ws_details.auto_filter.ref = f"A1:D{max(ws_details.max_row, 1)}"

    # Auto-adjust column widths
    for ws in (ws_summary, ws_details):
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(min(max_len + 4, 60), 14)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
