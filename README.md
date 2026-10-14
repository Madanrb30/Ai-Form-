# VoxForm — AI Voice-Assisted Dynamic Form Assistant

VoxForm is an enterprise-hardened, full-stack application designed to generate, fill, and process dynamic web forms using natural-language instructions, voice dialogue, and document extraction.

Built with a monochrome black-and-white minimalist aesthetic, strict schema validation, Groq cloud AI integration, hybrid document ingestion (digital PDFs, interactive AcroForms, and Vision OCR), audio speech-to-text, and secure SQLite persistence.

---

## System Architecture

```
                          ┌─────────────────────────────┐
                          │   React 19 + Vite Frontend  │
                          │   - Dynamic Form Renderer   │
                          │   - Web Speech & Cloud Mic  │
                          │   - Monochrome Minimalist UI│
                          │   - Draft Autosave & Sync   │
                          └──────────────┬──────────────┘
                                         │ REST API (Bearer JWT / Query Token)
                                         ▼
                          ┌─────────────────────────────┐
                          │       FastAPI Backend       │
                          │   - Strict Pydantic v2      │
                          │   - Access Control & Auth   │
                          │   - Rate-Limited Endpoints  │
                          │   - Hybrid Doc Extractor    │
                          │   - ReportLab PDF Engine    │
                          └──────┬───────────────┬──────┘
                                 │               │
                     Live Cloud  │               │ SQLite with PRAGMA Foreign Keys
                                 ▼               ▼
                      ┌────────────────────┐  ┌─────────────────────┐
                      │   Groq Cloud API   │  │   SQLite Database   │
                      │  - Qwen 3.8-27b    │  │  - Users & Forms    │
                      │  - Whisper Turbo   │  │  - Submissions      │
                      │  - (or Demo Mode)  │  │  - Drafts & Sessions │
                      └────────────────────┘  └─────────────────────┘
```

---

## Technology Stack

- **Frontend:**
  - React 19 (`react`, `react-dom`)
  - Vite 8
  - Tailwind CSS v4 (`@tailwindcss/vite`)
  - Lucide Icons (`lucide-react`)
  - Web Speech API + Whisper Cloud Audio Recording
- **Backend:**
  - Python 3.10+
  - FastAPI & Uvicorn
  - Pydantic v2 & Pydantic-Settings
  - SQLAlchemy 2.0 (with SQLite PRAGMA Foreign Keys)
  - PyJWT & Passlib (Bcrypt)
  - ReportLab & PyPDFium2 / PDFMiner
  - Pillow (PIL)
- **AI & Cloud Engine:**
  - **Groq Cloud API** (Default models: `llama-3.3-70b-versatile`, `qwen/qwen3.8-27b`, `whisper-large-v3-turbo`)
  - Deterministic Offline Demo Mode (fallback for local development and testing)
- **Automated Testing & Security:**
  - Pytest + FastAPI TestClient + HTTPX (68 automated backend tests)
  - Vitest (7 frontend unit & integration tests)
  - NPM Audit (0 vulnerabilities)

---

## Core Features & Workflow

1. **Natural-Language Form Generation:**
   - Prompt-driven schema synthesis via Groq cloud LLMs.
   - Generates 8 standard field types: `text`, `email`, `number`, `date`, `textarea`, `select`, `checkbox`, `radio`.
   - Strict server-side schema verification preventing invalid or duplicate fields.

2. **Hybrid Document Ingestion & Extraction:**
   - **Interactive AcroForms:** Directly extracts native PDF form widgets and fields.
   - **Digital PDFs:** Parses structured text blocks with layout-aware heuristics.
   - **Scanned Images & Forms:** Uses Groq Vision OCR to read scanned registration cards and receipts.

3. **Multi-Turn Conversational Form Filling:**
   - Stateful dialog sessions tracking filled vs. missing required fields.
   - Schema-aware slot mapping (identifies names, dates, phone numbers, and select options).
   - Validates choices against allowed select/radio values and prompts users for invalid spoken options.
   - Preserves string identifiers (register numbers, phone numbers) with leading zeros.

4. **Speech-to-Text Transcription:**
   - Live microphone capture supporting WebM, WAV, MP3, M4A, OGG, and FLAC.
   - Transcribed via Groq Cloud Whisper (`whisper-large-v3-turbo`).

5. **Draft Autosave & Sync:**
   - Periodic background saving per user/form.
   - Isolated draft storage preventing cross-user data overwrite.

6. **Automated Submission & PDF Export:**
   - Server-side submission validation verifying required fields and type constraints.
   - Generates downloadable completed PDF documents using ReportLab.
   - Authenticated PDF download endpoints supporting both Bearer headers and query tokens.

---

## Security Model & Hardening

- **JWT Secret Enforcement:** Hardcoded secrets removed. In `ENVIRONMENT=production`, a cryptographically strong `JWT_SECRET_KEY` (minimum 32 characters) is strictly enforced at application boot.
- **Fail-Safe Authorization:** Anonymous token degradation is eliminated; malformed or expired tokens immediately return `401 Unauthorized`.
- **Resource Isolation & Ownership:** Users cannot read, modify, or delete other users' private forms, drafts, conversational sessions, submissions, or generated PDFs.
- **Rate Limiting:** Sliding-window login brute-force protection (10 attempts / 5 minutes) returning `429 Too Many Requests`.
- **Upload Protection:** 10MB size limits, MIME & extension whitelisting, file content inspection, randomized server-controlled filenames, path-traversal prevention, and automatic cleanup of temporary files on processing errors.
- **Error Shielding:** Internal database errors and raw stack traces are masked from clients; debug information is logged securely server-side.
- **CORS Safeguards:** Origins are configurable via JSON array; wildcards (`*`) combined with credentials are strictly forbidden.

---

## Prerequisites

- **Node.js:** v18+ (v24 tested)
- **Python:** v3.10+
- **Groq Cloud API Key:** Obtain from [Groq Console](https://console.groq.com/keys) (optional if running in Demo Mode).

---

## Installation & Setup

### 1. Clone & Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Windows Command Prompt:
.\venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Backend Environment

Copy `backend/.env.example` to `backend/.env`:

```bash
cp .env.example .env
```

Edit `backend/.env` with your settings:
```env
PROJECT_NAME="AI Voice Form Assistant"
ENVIRONMENT="development"
DATABASE_URL="sqlite:///./app.db"
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]

# Groq Cloud AI Configuration
GROQ_API_KEY="gsk_your_groq_api_key_here"
GROQ_MODEL="qwen/qwen3.8-27b"
GROQ_VISION_MODEL="qwen/qwen3.8-27b"
GROQ_TRANSCRIPTION_MODEL="whisper-large-v3-turbo"
AI_PROVIDER="groq"
AI_DEMO_MODE=false
ALLOW_PRODUCTION_DEMO_MODE=false

# Security & JWT
JWT_SECRET_KEY="generate-a-secure-random-32-char-secret"
ACCESS_TOKEN_EXPIRE_MINUTES=10080
SEED_DEMO_USER=false

# Server
HOST="127.0.0.1"
PORT=8090
LOG_LEVEL="INFO"
```

### 3. Setup Frontend

```bash
cd ../frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
```

`frontend/.env`:
```env
VITE_API_BASE_URL="http://127.0.0.1:8090/api"
```

---

## Running the Application Locally

### 1. Start Backend Server
```bash
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8090
```
- API Base URL: `http://127.0.0.1:8090`
- API Documentation (Swagger): `http://127.0.0.1:8090/docs` (disabled in production)
- Health Check: `http://127.0.0.1:8090/api/health`

### 2. Start Frontend Dev Server
In a separate terminal:
```bash
cd frontend
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## Running Automated Tests

### 1. Backend Pytest Suite
```bash
cd backend
.\venv\Scripts\pytest.exe
```
Executes all 68 automated unit, integration, authentication, and security hardening tests.

### 2. Backend End-to-End Verification Check
```bash
cd backend
.\venv\Scripts\python.exe verify_e2e.py
```
Performs a 10-step full-lifecycle integration test covering live AI form synthesis, voice mapping, hybrid document parsing, Whisper transcription, conversation session flow, draft autosave, submission validation, PDF generation, and SQLite database persistence across application restarts.

### 3. Frontend Vitest Suite
```bash
cd frontend
npm test
```
Executes 7 frontend integration tests verifying API failure handling, network error states, and storage behaviors.

### 4. Frontend Production Build & Audit
```bash
cd frontend
npm run build
npm audit
```

---

## Production Deployment Checklist

1. **Environment Mode:** Set `ENVIRONMENT="production"` in `backend/.env`.
2. **Secrets:** Generate a 64-character random secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Set `JWT_SECRET_KEY` with this value. Do not share or commit this key.
3. **CORS:** Restrict `CORS_ORIGINS` to the exact public domain of your frontend (e.g. `["https://app.yourdomain.com"]`).
4. **Groq Credentials:** Provide a valid `GROQ_API_KEY`. In production, `AI_DEMO_MODE` is disabled by default to prevent serving synthetic forms.
5. **Database:** SQLite is suitable for single-instance deployments with local persistent disks. If scaling horizontally across multiple web nodes, configure `DATABASE_URL` with a managed PostgreSQL connection URI (`postgresql://...`).
6. **Reverse Proxy:** Run Uvicorn behind Nginx or Caddy with TLS (HTTPS) termination, HTTP/2, and client upload limit headers (`client_max_body_size 15M;`).
7. **Storage:** Ensure `backend/uploads/` is backed by persistent volume storage with appropriate read/write file permissions.

---

## License

This project is licensed under the MIT License.
