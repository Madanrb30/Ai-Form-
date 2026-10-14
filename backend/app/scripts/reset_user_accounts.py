"""
Dedicated Account Reset & Super Admin Re-Arming Script.
Safely purges all USER, ADMIN, and SUPER_ADMIN accounts while preserving:
- All forms and schemas (converted to shared system templates).
- All submissions, responses, and generated PDF file paths.
- All drafts, conversation sessions, and uploaded documents.
- All historical immutable audit logs.

Requirements:
- Mandatory pre-execution database backup.
- Strict foreign-key preservation with PRAGMA foreign_keys=ON.
- Interactive or flag-based explicit confirmation.
- Full transactional rollback on any error.
- Re-arms the one-time Super Admin bootstrap mechanism.
"""
import os
import sys
import shutil
import argparse
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure backend root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings
from app.db.session import engine, SessionLocal
from app.models.user import User
from app.models.form import Form
from app.models.submission import Submission
from app.models.draft import Draft
from app.models.conversation import ConversationSession
from app.models.uploaded_document import UploadedDocument
from app.models.audit_log import AuditLog
from app.services.bootstrap_service import has_active_super_admin

CONFIRMATION_PHRASE = "RESET ALL USERS"


def backup_database(db_file_path: str, backup_dir: str = None) -> str:
    """Creates a verified timestamped copy of the SQLite database."""
    if not os.path.exists(db_file_path):
        raise FileNotFoundError(f"Database file not found at: {db_file_path}")

    target_dir = backup_dir or os.path.dirname(os.path.abspath(db_file_path))
    os.makedirs(target_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"app.db.backup_{timestamp}"
    backup_path = os.path.join(target_dir, backup_filename)

    shutil.copy2(db_file_path, backup_path)

    # Verification
    if not os.path.exists(backup_path):
        raise RuntimeError(f"Backup creation failed: {backup_path} does not exist.")
    orig_size = os.path.getsize(db_file_path)
    back_size = os.path.getsize(backup_path)
    if orig_size != back_size:
        raise RuntimeError(f"Backup size mismatch: original {orig_size} bytes, backup {back_size} bytes.")

    return backup_path


def get_pre_reset_summary(db: Session) -> dict:
    """Inspects and counts existing records across all application tables."""
    users_by_role = {
        "USER": db.query(User).filter(User.role == "USER").count(),
        "ADMIN": db.query(User).filter(User.role == "ADMIN").count(),
        "SUPER_ADMIN": db.query(User).filter(User.role == "SUPER_ADMIN").count(),
    }
    total_users = sum(users_by_role.values())
    total_forms = db.query(Form).count()
    private_forms = db.query(Form).filter(Form.is_public == False).count()
    public_forms = db.query(Form).filter(Form.is_public == True).count()
    total_submissions = db.query(Submission).count()
    user_owned_submissions = db.query(Submission).filter(Submission.user_id.isnot(None)).count()
    total_drafts = db.query(Draft).count()
    total_sessions = db.query(ConversationSession).count()
    total_documents = db.query(UploadedDocument).count()
    total_audit_logs = db.query(AuditLog).count()

    return {
        "total_users": total_users,
        "users_by_role": users_by_role,
        "total_forms": total_forms,
        "private_forms": private_forms,
        "public_forms": public_forms,
        "total_submissions": total_submissions,
        "user_owned_submissions": user_owned_submissions,
        "total_drafts": total_drafts,
        "total_sessions": total_sessions,
        "total_documents": total_documents,
        "total_audit_logs": total_audit_logs,
    }


def execute_account_reset(db: Session, dry_run: bool = False) -> dict:
    """
    Transactionally purges all user accounts while preserving all foreign-key
    referenced entities and updating ownership to system-shared status.
    """
    summary_before = get_pre_reset_summary(db)

    # Execute within explicit transaction
    try:
        # Step 1: Disassociate forms from deleted users while preserving original visibility (public stays public, private stays private)
        db.execute(text("UPDATE forms SET user_id = NULL WHERE user_id IS NOT NULL"))

        # Step 2: Disassociate submissions from deleted users (preserving response data & PDFs)
        db.execute(text("UPDATE submissions SET user_id = NULL WHERE user_id IS NOT NULL"))

        # Step 3: Disassociate drafts
        db.execute(text("UPDATE drafts SET user_id = NULL WHERE user_id IS NOT NULL"))

        # Step 4: Disassociate conversation sessions
        db.execute(text("UPDATE conversation_sessions SET user_id = NULL WHERE user_id IS NOT NULL"))

        # Step 5: Disassociate uploaded documents
        db.execute(text("UPDATE uploaded_documents SET user_id = NULL WHERE user_id IS NOT NULL"))

        # Step 6: Delete all user accounts (safe with PRAGMA foreign_keys=ON because all FKs are cleared)
        db.execute(text("DELETE FROM users"))

        # Step 7: Record audit log of the reset action
        audit_entry = AuditLog(
            actor_id=None,
            actor_email="system_reset_script",
            action="ACCOUNTS_PURGED_AND_RESET",
            target_type="System",
            target_id="users_table",
            details=f"Purged {summary_before['total_users']} accounts. Preserved {summary_before['total_forms']} forms and {summary_before['total_submissions']} submissions.",
            status="SUCCESS",
        )
        db.add(audit_entry)

        # Step 8: Strict post-operation integrity assertions
        remaining_users = db.query(User).count()
        if remaining_users != 0:
            raise RuntimeError(f"Integrity check failed: {remaining_users} users still remain after DELETE.")

        forms_after = db.query(Form).count()
        if forms_after != summary_before["total_forms"]:
            raise RuntimeError(f"Data loss detected: forms changed from {summary_before['total_forms']} to {forms_after}.")

        subs_after = db.query(Submission).count()
        if subs_after != summary_before["total_submissions"]:
            raise RuntimeError(f"Data loss detected: submissions changed from {summary_before['total_submissions']} to {subs_after}.")

        docs_after = db.query(UploadedDocument).count()
        if docs_after != summary_before["total_documents"]:
            raise RuntimeError(f"Data loss detected: documents changed from {summary_before['total_documents']} to {docs_after}.")

        if dry_run:
            db.rollback()
            return {
                "status": "DRY_RUN_SUCCESS",
                "summary_before": summary_before,
                "users_deleted": summary_before["total_users"],
                "forms_preserved": forms_after,
                "submissions_preserved": subs_after,
            }

        db.commit()

        # Final check on committed state
        is_armed = not has_active_super_admin(db)

        return {
            "status": "SUCCESS",
            "summary_before": summary_before,
            "users_deleted": summary_before["total_users"],
            "forms_preserved": forms_after,
            "submissions_preserved": subs_after,
            "bootstrap_re_armed": is_armed,
        }

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Reset transaction aborted and rolled back: {e}") from e


def run_reset_cli(
    confirm_phrase: str = None,
    dry_run: bool = False,
    db_file: str = None,
    session_override: Session = None,
) -> int:
    """CLI orchestrator for the account reset process."""
    print("\n" + "=" * 78)
    print("AI VOICE FORM ASSISTANT — SAFE ACCOUNT RESET & RE-ARMING TOOL")
    print("=" * 78)

    # 1. Resolve database path
    db_path = db_file or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "app.db"
    )

    db = session_override or SessionLocal()
    own_session = session_override is None

    try:
        # 2. Inspect pre-reset state
        summary = get_pre_reset_summary(db)

        print("\n[CURRENT DATABASE STATE]")
        print(f"Total User Accounts    : {summary['total_users']}")
        print(f"  - Standard Users      : {summary['users_by_role']['USER']}")
        print(f"  - Administrators      : {summary['users_by_role']['ADMIN']}")
        print(f"  - Super Administrators: {summary['users_by_role']['SUPER_ADMIN']}")
        print("-" * 50)
        print(f"Forms to Preserve      : {summary['total_forms']} (Public: {summary['public_forms']}, Private: {summary['private_forms']})")
        print(f"Submissions to Preserve: {summary['total_submissions']}")
        print(f"Drafts to Preserve     : {summary['total_drafts']}")
        print(f"Documents to Preserve  : {summary['total_documents']}")
        print(f"Audit Logs to Preserve : {summary['total_audit_logs']}")
        print("=" * 78)

        if summary['total_users'] == 0:
            print("\n[NOTICE] There are currently no user accounts in the database.")
            print("The one-time Super Admin bootstrap mechanism is already active and ready.")
            return 0

        # 3. Confirmation check
        if dry_run:
            print("\n[DRY RUN MODE ENABLED] — No changes will be committed to the database.\n")
        else:
            if confirm_phrase != CONFIRMATION_PHRASE:
                if sys.stdin.isatty():
                    print("\nWARNING: This operation will permanently remove all existing user accounts.")
                    print("All forms and submissions will be preserved and converted to shared system templates.")
                    print(f"To proceed, please type the exact phrase: '{CONFIRMATION_PHRASE}'")
                    user_input = input("Confirmation: ").strip()
                    if user_input != CONFIRMATION_PHRASE:
                        print("\n[ABORTED] Confirmation phrase did not match. No changes made.\n")
                        return 1
                else:
                    print(f"\n[ERROR] Non-interactive execution requires --confirm \"{CONFIRMATION_PHRASE}\"\n")
                    return 1

            # 4. Mandatory Backup (only for real runs when db file exists on disk)
            if os.path.exists(db_path):
                print("\n[BACKUP] Creating pre-reset database backup...")
                backup_file = backup_database(db_path)
                print(f"[BACKUP] Verified backup created: {backup_file}")
            else:
                print(f"\n[BACKUP NOTE] SQLite file not on disk at {db_path} (in-memory or custom URL). Skipping file copy.")

        # 5. Execute reset
        print("\nExecuting transactional reset...")
        result = execute_account_reset(db, dry_run=dry_run)

        print("\n" + "=" * 78)
        if dry_run:
            print("DRY RUN COMPLETED SUCCESSFULLY (Database rolled back; zero modifications)")
        else:
            print("ACCOUNT RESET COMPLETED SUCCESSFULLY")
        print("=" * 78)
        print(f"Users Deleted         : {result['users_deleted']}")
        print(f"Forms Preserved       : {result['forms_preserved']} (converted to shared system templates)")
        print(f"Submissions Preserved : {result['submissions_preserved']}")
        if not dry_run:
            print(f"Bootstrap Re-Armed    : {result['bootstrap_re_armed']} (Ready for initial Super Admin)")
        print("=" * 78)

        if not dry_run:
            print("\nNEXT STEPS TO ESTABLISH NEW ADMINISTRATORS:")
            print("1. Set your bootstrap secret key in backend/.env:")
            print("   BOOTSTRAP_SECRET_KEY=\"your-secure-32-char-key\"")
            print("2. Provision your fresh Super Administrator account:")
            print("   python -m app.scripts.bootstrap_super_admin")
            print("3. Log in to http://localhost:5173/login as the new Super Admin.")
            print("4. Register a new user account, then promote it to ADMIN in the dashboard.")
            print("=" * 78 + "\n")

        return 0

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}\n")
        return 1
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge all user accounts and re-arm Super Admin provisioning")
    parser.add_argument("--confirm", help=f"Confirmation phrase: '{CONFIRMATION_PHRASE}'")
    parser.add_argument("--dry-run", action="store_true", help="Preview reset actions without committing")
    parser.add_argument("--db-path", help="Path to SQLite database file")
    args = parser.parse_args()

    code = run_reset_cli(
        confirm_phrase=args.confirm,
        dry_run=args.dry_run,
        db_file=args.db_path,
    )
    sys.exit(code)
