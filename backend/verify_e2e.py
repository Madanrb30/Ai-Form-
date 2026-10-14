"""
End-to-end verification script for real database persistence,
form generation, submission lifecycle, and restart resilience.
"""
import os
import sys
import io
import wave
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

# Ensure backend root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.db.init_db import init_db
from app.main import app

def run_e2e_verification():
    print("--- 1. Initializing Database ---")
    init_db()
    
    with TestClient(app) as client:
        print("--- 2. Health Check ---")
        health = client.get("/api/health")
        assert health.status_code == 200
        print(f"Health Response: {health.json()}")

        print("--- 3. Form Generation (Demo Mode) ---")
        gen_res = client.post(
            "/api/forms/generate",
            json={"prompt": "Create a student registration form containing full name, register number, department, email address, phone number, date of birth, and gender."}
        )
        assert gen_res.status_code == 200
        gen_data = gen_res.json()
        print(f"Generated Schema Title: {gen_data['schema_data']['title']}")
        print(f"Fields Count: {len(gen_data['schema_data']['fields'])}")

        print("--- 4. Persisting Form into Database ---")
        save_res = client.post(
            "/api/forms",
            json={
                "title": gen_data["schema_data"]["title"],
                "description": gen_data["schema_data"].get("description"),
                "schema_json": gen_data["schema_data"]
            }
        )
        assert save_res.status_code == 201
        form_id = save_res.json()["id"]
        print(f"Form saved with ID: {form_id}")

        print("--- 5. Voice Mapping Test ---")
        voice_res = client.post(
            f"/api/forms/{form_id}/voice-map",
            json={"transcript": "My name is Madan and my department is Artificial Intelligence & Data Science and my email is madan@test.com"}
        )
        assert voice_res.status_code == 200
        mapped = voice_res.json()["mapped_fields"]
        print(f"Voice Mapped Fields: {mapped}")
        assert "full_name" in mapped
        print("--- 6. Hybrid Document Extraction (Digital PDF, AcroForm & Groq Vision OCR) ---")
        # 6a. Digital PDF
        dig_buf = io.BytesIO()
        c = canvas.Canvas(dig_buf, pagesize=letter)
        c.drawString(100, 750, "Student Admission Form")
        c.drawString(100, 720, "Full Name: Johnathan Doe")
        c.drawString(100, 690, "Email Address: john@example.com")
        c.save()
        dig_res = client.post(
            "/api/forms/upload-document",
            files={"file": ("admission.pdf", dig_buf.getvalue(), "application/pdf")}
        )
        assert dig_res.status_code == 200
        print(f"Digital PDF Extraction: strategy={dig_res.json()['extraction_strategy']}, fields={dig_res.json()['detected_fields_count']}")

        # 6b. Interactive AcroForm
        acro_buf = io.BytesIO()
        c2 = canvas.Canvas(acro_buf, pagesize=letter)
        c2.drawString(100, 750, "Interactive Tax Form")
        tax_form = c2.acroForm
        tax_form.textfield(name="taxpayer_name", tooltip="Name", x=100, y=700, width=200, height=20)
        c2.save()
        acro_res = client.post(
            "/api/forms/upload-document",
            files={"file": ("tax_form.pdf", acro_buf.getvalue(), "application/pdf")}
        )
        assert acro_res.status_code == 200
        print(f"AcroForm Extraction: strategy={acro_res.json()['extraction_strategy']}, fields={acro_res.json()['detected_fields_count']}")

        # 6c. Live Groq Vision OCR Image
        img = Image.new("RGB", (400, 250), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "PATIENT REGISTRATION", fill="black")
        draw.text((20, 60), "Patient Name: ________________", fill="black")
        draw.text((20, 110), "Age: _________________________", fill="black")
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        try:
            vision_res = client.post(
                "/api/forms/upload-document",
                files={"file": ("patient_card.png", img_buf.getvalue(), "image/png")}
            )
            if vision_res.status_code == 200:
                print(f"Live Groq Vision OCR: strategy={vision_res.json()['extraction_strategy']}, fields={vision_res.json()['detected_fields_count']}, title='{vision_res.json()['schema_data']['title']}'")
            else:
                print(f"Groq Vision Response ({vision_res.status_code}): {vision_res.json()}")
        except Exception as e:
            print(f"Groq Vision note: {e}")

        print("--- 7. Cloud Whisper Speech-to-Text Transcription ---")
        empty_res = client.post(
            "/api/voice/transcribe",
            files={"file": ("empty.wav", b"", "audio/wav")}
        )
        assert empty_res.status_code == 400
        print(f"Empty audio validation: {empty_res.json()['detail']}")

        invalid_res = client.post(
            "/api/voice/transcribe",
            files={"file": ("script.sh", b"echo hi", "text/plain")}
        )
        assert invalid_res.status_code == 400
        print(f"Invalid extension validation: {invalid_res.json()['detail']}")

        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 8000)
        wav_bytes = wav_buf.getvalue()

        try:
            whisper_res = client.post(
                "/api/voice/transcribe",
                files={"file": ("sample.wav", wav_bytes, "audio/wav")},
                data={"language": "en"}
            )
            if whisper_res.status_code == 200:
                whisper_data = whisper_res.json()
                print(f"Live Groq Whisper Result: '{whisper_data['text']}' (Model: {whisper_data['model']})")
            else:
                print(f"Groq Whisper Status ({whisper_res.status_code}): {whisper_res.json()}")
        except Exception as e:
            print(f"Groq Whisper Request note: {e}")

        print("--- 7. Stateful Conversational Turn & Missing Field Guidance ---")
        conv_res = client.post(
            f"/api/forms/{form_id}/conversation",
            json={
                "transcript": "My full name is Madan and my department is Artificial Intelligence",
                "current_values": {}
            }
        )
        assert conv_res.status_code == 200
        conv_data = conv_res.json()
        print(f"Conversation Session ID: {conv_data['session_id']}")
        print(f"Assistant Spoken Response: {conv_data['assistant_response']}")
        print(f"Missing Required Fields: {len(conv_data['missing_fields'])}")
        assert conv_data["updated_values"].get("full_name") == "Madan"

        print("--- 7. Autosave Draft Workflow ---")
        draft_save = client.post(
            f"/api/forms/{form_id}/draft",
            json={"values_json": {"full_name": "Madan", "department": "AI & DS"}}
        )
        assert draft_save.status_code == 200
        print("Draft saved successfully")

        draft_get = client.get(f"/api/forms/{form_id}/draft")
        assert draft_get.status_code == 200
        assert draft_get.json()["values_json"]["full_name"] == "Madan"
        print("Draft retrieved successfully")

        print("--- 8. Form Submission ---")
        sub_payload = {
            "full_name": "Madan",
            "register_number": "REG-2026-99",
            "department": "Artificial Intelligence & Data Science",
            "email": "madan@university.edu",
            "phone_number": "+1 555-0199",
            "date_of_birth": "2000-08-15",
            "gender": "Male"
        }
        sub_res = client.post(
            f"/api/forms/{form_id}/submissions",
            json={"response_json": sub_payload}
        )
        assert sub_res.status_code == 201
        sub_id = sub_res.json()["id"]
        print(f"Submission recorded with ID: {sub_id}")

        print("--- 9. Retrieve Submissions & Export PDF ---")
        get_subs = client.get(f"/api/forms/{form_id}/submissions")
        assert get_subs.status_code == 200
        subs_list = get_subs.json()
        assert len(subs_list) >= 1
        print(f"Retrieved {len(subs_list)} submission(s)")

        pdf_res = client.get(f"/api/forms/{form_id}/submissions/{sub_id}/pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF")
        print(f"PDF generated successfully ({len(pdf_res.content)} bytes)")

    print("--- 10. Simulating Application Restart & Persistence Verification ---")
    # Fresh client instance simulating a restart
    with TestClient(app) as client_after_restart:
        re_form = client_after_restart.get(f"/api/forms/{form_id}")
        assert re_form.status_code == 200
        print(f"Persisted Form Verified: {re_form.json()['title']} (ID {form_id})")

        re_subs = client_after_restart.get(f"/api/forms/{form_id}/submissions")
        assert re_subs.status_code == 200
        print(f"Persisted Submissions Verified: Found {len(re_subs.json())} recorded responses.")

    print("\n>>> ALL E2E WORKFLOW CHECKS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_e2e_verification()
