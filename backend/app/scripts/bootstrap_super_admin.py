"""
Interactive and Non-Interactive CLI Tool for Super Admin Provisioning.
Usage:
  # Non-interactive (Environment Variables):
  export BOOTSTRAP_SECRET_KEY="your-secure-32-char-bootstrap-key"
  export BOOTSTRAP_SUPER_ADMIN_EMAIL="admin@yourdomain.com"
  export BOOTSTRAP_SUPER_ADMIN_PASSWORD="StrongPassword123!"
  export BOOTSTRAP_SUPER_ADMIN_NAME="Primary Administrator"
  python -m app.scripts.bootstrap_super_admin

  # Interactive (Console Prompt):
  python -m app.scripts.bootstrap_super_admin
"""
import os
import sys
import getpass
import argparse

# Ensure backend root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.bootstrap_service import (
    has_active_super_admin,
    provision_super_admin,
    BootstrapError,
)


def run_cli_bootstrap(
    email: str = None,
    password: str = None,
    full_name: str = None,
    bootstrap_key: str = None,
    db_session: SessionLocal = None,
) -> int:
    own_session = db_session is None
    db = db_session if db_session is not None else SessionLocal()
    try:
        if has_active_super_admin(db):
            print("\n[ERROR] An active Super Administrator already exists.")
            print("One-time administrative bootstrap is permanently disabled.\n")
            return 1

        # 1. Resolve bootstrap secret key
        resolved_key = (
            bootstrap_key
            or os.getenv("BOOTSTRAP_SECRET_KEY")
            or settings.BOOTSTRAP_SECRET_KEY
        )
        if not resolved_key and sys.stdin.isatty():
            resolved_key = getpass.getpass("Enter Server BOOTSTRAP_SECRET_KEY: ").strip()

        if not resolved_key:
            print("\n[ERROR] BOOTSTRAP_SECRET_KEY must be provided via argument, environment, or prompt.\n")
            return 1

        # 2. Resolve email
        resolved_email = (
            email
            or os.getenv("BOOTSTRAP_SUPER_ADMIN_EMAIL")
            or settings.BOOTSTRAP_SUPER_ADMIN_EMAIL
        )
        if not resolved_email and sys.stdin.isatty():
            resolved_email = input("Enter Super Admin Email: ").strip()

        if not resolved_email:
            print("\n[ERROR] Super Admin email address is required.\n")
            return 1

        # 3. Resolve password
        resolved_password = (
            password
            or os.getenv("BOOTSTRAP_SUPER_ADMIN_PASSWORD")
            or settings.BOOTSTRAP_SUPER_ADMIN_PASSWORD
        )
        if not resolved_password and sys.stdin.isatty():
            resolved_password = getpass.getpass("Enter Super Admin Password (min 8 chars): ")
            confirm_pwd = getpass.getpass("Confirm Super Admin Password: ")
            if resolved_password != confirm_pwd:
                print("\n[ERROR] Passwords do not match.\n")
                return 1

        if not resolved_password:
            print("\n[ERROR] Super Admin password is required.\n")
            return 1

        # 4. Resolve name
        resolved_name = (
            full_name
            or os.getenv("BOOTSTRAP_SUPER_ADMIN_NAME")
            or settings.BOOTSTRAP_SUPER_ADMIN_NAME
            or "Super Administrator"
        )
        if not resolved_name and sys.stdin.isatty():
            resolved_name = input("Enter Full Name [Super Administrator]: ").strip() or "Super Administrator"

        # 5. Provision transactionally
        print("\nProvisioning initial Super Administrator...")
        user = provision_super_admin(
            db=db,
            email=resolved_email,
            password=resolved_password,
            full_name=resolved_name,
            bootstrap_key=resolved_key,
            method="cli",
        )

        print("\n" + "=" * 70)
        print("SUCCESS: Initial Super Administrator Provisioned Successfully!")
        print("=" * 70)
        print(f"User ID   : {user.id}")
        print(f"Email     : {user.email}")
        print(f"Full Name : {user.full_name}")
        print(f"Role      : {user.role}")
        print("=" * 70)
        print("NEXT STEPS:")
        print("1. Log in to the application at http://localhost:5173/login.")
        print("2. Remove or unset BOOTSTRAP_SECRET_KEY, BOOTSTRAP_SUPER_ADMIN_EMAIL,")
        print("   and BOOTSTRAP_SUPER_ADMIN_PASSWORD from your environment / .env file.")
        print("=" * 70 + "\n")
        return 0

    except BootstrapError as e:
        print(f"\n[BOOTSTRAP FAILED] {e}\n")
        return 1
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}\n")
        return 1
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-time Super Admin Bootstrap CLI")
    parser.add_argument("--email", help="Super Admin Email")
    parser.add_argument("--password", help="Super Admin Password")
    parser.add_argument("--name", help="Super Admin Full Name")
    parser.add_argument("--key", help="Server BOOTSTRAP_SECRET_KEY")
    args = parser.parse_args()

    exit_code = run_cli_bootstrap(
        email=args.email,
        password=args.password,
        full_name=args.name,
        bootstrap_key=args.key,
    )
    sys.exit(exit_code)
