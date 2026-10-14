# VoxForm — AI Voice-Assisted Dynamic Form Builder

A modern, full-stack web application that allows users to generate dynamic web forms using natural-language instructions and fill them manually or through voice assistance.

Built with a monochrome black-and-white aesthetic, strict schema validation, offline Demo Mode fallback, and persistent SQLite storage.

---

## Architecture Overview

```
                          ┌─────────────────────────────┐
                          │   React 19 + Vite Frontend  │
                          │   - Dynamic Form Renderer   │
                          │   - Web Speech Assistant    │
                          │   - Tailwind CSS v4 (B&W)   │
                          └──────────────┬──────────────┘
                                         │ REST API
                                         ▼
                          ┌─────────────────────────────┐
                          │       FastAPI Backend       │
                          │   - Pydantic v2 Schemas     │
                          │   - AI Generation Service   │
                          │   - Voice Slot Extraction   │
                          └──────┬───────────────┬──────┘
                                 │               │
                     (If configured)             │ SQLAlchemy 2.0
                                 ▼               ▼
                      ┌────────────────────┐  ┌─────────────────────┐
                      │ Google Gemini API  │  │ SQLite Database     │
                      │ (or Demo Mode)     │  │ (forms & submissions│
                      └────────────────────┘  └─────────────────────┘
```

---

## Technology Stack

- **Frontend:**
  - React 19 (`react`, `react-dom`)
  - Vite 8
  - Tailwind CSS v4 (`@tailwindcss/vite`)
  - Lucide Icons (`lucide-react`)
  - Browser Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)
- **Backend:**
  - Python 3.10+
  - FastAPI
  - Uvicorn
  - Pydantic v2 & Pydantic-Settings
  - SQLAlchemy 2.0
  - SQLite (Local persistence)
  - Google Generative AI (Gemini Flash)
- **Testing & Quality Assurance:**
  - Pytest + FastAPI TestClient + HTTPX
  - Vitest + Oxlint

---

## Features

1. **Natural-Language Form Generation:**
   - Prompt-based dynamic form schema generation.
   - Works with live Google Gemini API or deterministic offline Demo Mode.
   - Generates 8 supported field types: `text`, `email`, `number`, `date`, `textarea`, `select`, `checkbox`, `radio`.
2. **Dynamic Form Rendering:**
   - Accessible input controls with required indicators (`*`).
   - Real-time client-side format & mandatory field checks.
   - Clean black-and-white minimalist design with zero visual clutter.
3. **Voice-Assisted Form Completion:**
   - Integrated browser Web Speech recognition with recording state pulses.
   - Schema-aware slot-filling engine mapping phrases to form fields (e.g., *"My name is Madan and my department is Artificial Intelligence & Data Science"*).
   - Review proposed changes with an instant diff before applying.
   - Full manual fallback for browsers without microphone or speech API support.
4. **Reliable Submissions & History:**
   - Server-side re-validation against database schemas.
   - Stored in SQLite with relational integrity and cascade rules.
   - Submissions history viewer with timestamps and structured data cards.

---

## Prerequisites

- **Node.js:** v18+ (v24 tested)
- **Python:** v3.10+
- **Browser:** Chrome, Edge, Safari, or Chromium-based browsers for Web Speech API (Firefox supported with manual input fallback).

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
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Backend Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `backend/.env` as needed:
```env
PROJECT_NAME="AI Voice Form Builder"
DATABASE_URL="sqlite:///./app.db"
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]

# Optional: Set Gemini API key for live AI generation.
# If left empty, the application runs automatically in offline Demo Mode.
GEMINI_API_KEY=""
GEMINI_MODEL="gemini-1.5-flash"
```

### 3. Setup Frontend

```bash
cd ../frontend

# Install dependencies
npm install

# Verify configuration
cp .env.example .env
```

`frontend/.env` contents:
```env
VITE_API_BASE_URL="http://127.0.0.1:8000/api"
```

---

## Running the Application

### 1. Start Backend Server
```bash
cd backend
.\venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- API Base: `http://127.0.0.1:8000`
- Interactive API Docs (Swagger): `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/api/health`

### 2. Start Frontend Dev Server
In a separate terminal:
```bash
cd frontend
npm run dev
```
Open your browser at: `http://localhost:5173`

---

## Running Automated Tests

### Backend Test Suite (Pytest)
```bash
cd backend
.\venv\Scripts\pytest.exe
```
Runs 14 automated unit, integration, security, and reliability tests covering CRUD, AI generation, voice mapping, and input validation.

### Backend End-to-End Persistence Check
```bash
cd backend
.\venv\Scripts\python.exe verify_e2e.py
```
Validates real SQLite database persistence and data retention across simulated application restarts.

### Frontend Test Suite (Vitest)
```bash
cd frontend
npm test
```
Runs frontend unit tests for API error handling and connection failure states.

### Frontend Linting & Production Build
```bash
cd frontend
npm run lint
npm run build
```

---

## Demo Mode vs Live AI Mode

| Feature | Demo Mode (Default) | Live Gemini AI Mode |
|---|---|---|
| **API Key Required** | No (Works 100% Offline) | Yes (`GEMINI_API_KEY` in `backend/.env`) |
| **Generation Strategy** | Deterministic keyword extraction + archetypes | Google Gemini 1.5 Flash API |
| **Field Types Supported** | All 8 Types | All 8 Types |
| **Status Indicator** | Badged `AI: Demo Mode` | Badged `AI: Gemini Active` |

---

## Troubleshooting

- **Microphone Permission Denied:**
  Ensure browser microphone permissions are enabled for `http://localhost:5173`. Alternatively, use the *Map Spoken Text* simulation box directly in the UI.
- **Backend Connection Error:**
  Verify that Uvicorn is active on `http://127.0.0.1:8000` and CORS includes `http://localhost:5173`.
- **Database Location:**
  The SQLite database is located at `backend/app.db`. Existing tables and data are preserved across restarts.
