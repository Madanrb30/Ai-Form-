# Secure Initial Super Administrator Provisioning Guide

## Overview

VoxForm enforces strict Role-Based Access Control (RBAC) across three roles: `USER`, `ADMIN`, and `SUPER_ADMIN`.
- **Public Registration (`/api/auth/register`)** is strictly restricted to provisioning `USER` accounts.
- **Administrative Endpoints (`/api/admin/...`)** require `ADMIN` or `SUPER_ADMIN` privileges.
- **Role Governance Endpoints (`/api/admin/users/{id}/role`)** are exclusively restricted to `SUPER_ADMIN`.

To solve the chicken-and-egg problem of establishing the initial Super Administrator without exposing privilege escalation vulnerabilities, a **secure, one-time administrative bootstrap mechanism** is implemented.

---

## Security Guarantees & Constraints

1. **One-Time Execution Only:** If any active `SUPER_ADMIN` account exists, all bootstrap pathways are permanently locked (returns HTTP 409 Conflict).
2. **Explicit Server-Side Secret Required:** Bootstrap requires a cryptographically strong secret key (`BOOTSTRAP_SECRET_KEY`, minimum 32 characters in production). If unset, the bootstrap endpoint is completely disabled (returns HTTP 403 Forbidden).
3. **No Silent User Promotion:** Bootstrap rejects requests targeting existing registered email addresses. It will never silently elevate privileges or overwrite passwords of existing accounts.
4. **Strong Password Enforcement:** Enforces minimum 8-character and maximum 128-character password limits, hashed using Bcrypt with application-standard salt rounds.
5. **Transactional & Concurrency Safe:** Uses database write transactions and in-process mutual exclusion locks (`threading.Lock`) to prevent race conditions during concurrent bootstrap requests.
6. **Immutable Audit Logging:** Every bootstrap attempt (successful, unauthorized, or rejected) is recorded in the `audit_logs` table.

---

## Setup Procedures

### Prerequisites: Generate Server-Side Secret

Generate a cryptographically secure random string (at least 32 characters):

```bash
# Linux / macOS / Git Bash
openssl rand -hex 32

# Windows PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

Add this secret to your backend environment (`backend/.env`):
```env
BOOTSTRAP_SECRET_KEY="c89f30e998a46b8969315998a28f117c374972cbb09d3b8417c8cf4b3e69188a"
```

---

### Method 1: Console / CLI Provisioning (Recommended)

The CLI tool executes directly on the server console and supports both interactive and non-interactive workflows.

#### A. Interactive Console Prompt (Zero Secrets on Disk)
```bash
cd backend
.\venv\Scripts\python.exe -m app.scripts.bootstrap_super_admin
```
The script will prompt for:
1. `Server BOOTSTRAP_SECRET_KEY`: Enter the key configured in `.env`.
2. `Super Admin Email`: Enter the desired administrator email (e.g., `admin@yourdomain.com`).
3. `Super Admin Password`: Enter a strong password (input hidden).
4. `Confirm Super Admin Password`: Re-enter password.
5. `Full Name`: Enter administrator name (e.g., `System Administrator`).

#### B. Non-Interactive Environment Variables
For automated deployments (Docker, CI/CD, Terraform):
```bash
# Set temporary environment variables
export BOOTSTRAP_SECRET_KEY="c89f30e998a46b8969315998a28f117c374972cbb09d3b8417c8cf4b3e69188a"
export BOOTSTRAP_SUPER_ADMIN_EMAIL="admin@yourdomain.com"
export BOOTSTRAP_SUPER_ADMIN_PASSWORD="StrongPassword123!"
export BOOTSTRAP_SUPER_ADMIN_NAME="System Administrator"

# Run provisioning
cd backend
python -m app.scripts.bootstrap_super_admin
```

---

### Method 2: Secret-Protected Administrative API Endpoint

For remote server initialization where direct SSH or console access is restricted:

#### Endpoint Details
* **Method:** `POST`
* **Path:** `/api/admin/bootstrap`
* **Header:** `X-Bootstrap-Key: <BOOTSTRAP_SECRET_KEY>`
* **Content-Type:** `application/json`

#### Request Payload
```json
{
  "email": "admin@yourdomain.com",
  "password": "StrongPassword123!",
  "full_name": "Primary Super Administrator"
}
```

#### Example cURL Request
```bash
curl -X POST "http://127.0.0.1:8090/api/admin/bootstrap" \
  -H "Content-Type: application/json" \
  -H "X-Bootstrap-Key: c89f30e998a46b8969315998a28f117c374972cbb09d3b8417c8cf4b3e69188a" \
  -d '{
    "email": "admin@yourdomain.com",
    "password": "StrongPassword123!",
    "full_name": "Primary Super Administrator"
  }'
```

#### Response (HTTP 201 Created)
```json
{
  "message": "Initial Super Administrator provisioned successfully. Please unset or remove BOOTSTRAP_SECRET_KEY from server environment.",
  "user": {
    "id": 1,
    "email": "admin@yourdomain.com",
    "full_name": "Primary Super Administrator",
    "role": "SUPER_ADMIN",
    "title": "System Owner",
    "avatar": "PS",
    "is_active": true,
    "created_at": "2026-10-14T10:00:00Z"
  }
}
```

---

### Method 3: Automated Application Startup Bootstrap

To automatically provision the initial Super Admin when the database initializes:

1. Configure in `backend/.env`:
   ```env
   BOOTSTRAP_SECRET_KEY="c89f30e998a46b8969315998a28f117c374972cbb09d3b8417c8cf4b3e69188a"
   BOOTSTRAP_SUPER_ADMIN_EMAIL="admin@yourdomain.com"
   BOOTSTRAP_SUPER_ADMIN_PASSWORD="StrongPassword123!"
   BOOTSTRAP_SUPER_ADMIN_NAME="System Administrator"
   ```
2. Start the backend:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
   ```
3. `init_db()` detects that no `SUPER_ADMIN` exists and provisions the account transactionally.

---

## Post-Provisioning Security Protocol (Mandatory)

Once the initial Super Administrator account is verified:

1. **Test Login:**
   Log in to the web interface at `http://localhost:5173/login` using the new Super Admin credentials. Verify access to the **Super Admin Dashboard** at `http://localhost:5173/super-admin`.
2. **Remove Bootstrap Secrets:**
   Delete or unset the bootstrap variables from your server environment / `backend/.env` file:
   ```env
   # Remove or comment out:
   # BOOTSTRAP_SECRET_KEY=""
   # BOOTSTRAP_SUPER_ADMIN_EMAIL=""
   # BOOTSTRAP_SUPER_ADMIN_PASSWORD=""
   # BOOTSTRAP_SUPER_ADMIN_NAME=""
   ```
3. **Verify Bootstrap Lock:**
   Attempt a bootstrap request via API or CLI:
   - With secret removed: Returns `403 Forbidden` (`Administrative bootstrap is disabled. BOOTSTRAP_SECRET_KEY is not configured on the server.`).
   - If secret is retained: Returns `409 Conflict` (`A Super Administrator already exists. One-time administrative bootstrap is permanently disabled.`).

---

## Automated Verification & Test Coverage

The bootstrap implementation is covered by automated unit and integration tests in `backend/tests/test_bootstrap.py`:

```bash
cd backend
.\venv\Scripts\pytest tests/test_bootstrap.py -v
```

All 15 test scenarios pass with 100% success:
- `test_has_active_super_admin_returns_false_when_none`
- `test_has_active_super_admin_returns_true_when_active_exists`
- `test_has_active_super_admin_returns_false_if_suspended`
- `test_successful_initial_super_admin_provisioning_via_service`
- `test_successful_initial_super_admin_provisioning_via_api`
- `test_bootstrap_via_body_key`
- `test_repeat_bootstrap_attempt_rejected`
- `test_bootstrap_missing_or_invalid_secret_rejected`
- `test_bootstrap_disabled_when_secret_unset`
- `test_bootstrap_with_existing_user_rejected`
- `test_bootstrap_weak_password_rejected`
- `test_concurrent_bootstrap_attempts_only_one_succeeds`
- `test_cli_bootstrap_success`
- `test_cli_bootstrap_repeat_fails`
- `test_cli_bootstrap_missing_key_fails`
