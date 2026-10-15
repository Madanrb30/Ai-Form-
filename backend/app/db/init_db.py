from sqlalchemy import text
from app.db.session import engine, Base, SessionLocal
import app.models  # Ensure models are loaded
from app.models.user import User
from app.core.security import get_password_hash
from app.core.logging import logger


def init_db():
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)

    # Safe column migrations for SQLite without dropping tables
    with engine.connect() as conn:
        try:
            # Check forms columns
            res = conn.execute(text("PRAGMA table_info(forms)"))
            cols = [row[1] for row in res.fetchall()]
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE forms ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                logger.info("Added user_id column to forms table.")
            if "is_public" not in cols:
                conn.execute(text("ALTER TABLE forms ADD COLUMN is_public BOOLEAN DEFAULT 1 NOT NULL"))
                logger.info("Added is_public column to forms table.")
            if "source_type" not in cols:
                conn.execute(text("ALTER TABLE forms ADD COLUMN source_type VARCHAR(50) DEFAULT 'manual'"))
                logger.info("Added source_type column to forms table.")
            if "original_document_path" not in cols:
                conn.execute(text("ALTER TABLE forms ADD COLUMN original_document_path VARCHAR(500)"))
                logger.info("Added original_document_path column to forms table.")

            # Check submissions columns
            res = conn.execute(text("PRAGMA table_info(submissions)"))
            sub_cols = [row[1] for row in res.fetchall()]
            if "user_id" not in sub_cols:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                logger.info("Added user_id column to submissions table.")
            if "generated_pdf_path" not in sub_cols:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN generated_pdf_path VARCHAR(500)"))
                logger.info("Added generated_pdf_path column to submissions table.")

            # Check drafts columns
            res = conn.execute(text("PRAGMA table_info(drafts)"))
            draft_cols = [row[1] for row in res.fetchall()]
            if "session_id" not in draft_cols:
                conn.execute(text("ALTER TABLE drafts ADD COLUMN session_id VARCHAR(100)"))
                logger.info("Added session_id column to drafts table.")

            # Check users columns for RBAC
            res = conn.execute(text("PRAGMA table_info(users)"))
            user_cols = [row[1] for row in res.fetchall()]
            if "title" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN title VARCHAR(100)"))
                logger.info("Added title column to users table.")
            if "is_active" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL"))
                logger.info("Added is_active column to users table.")
            if "token_version" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1 NOT NULL"))
                logger.info("Added token_version column to users table.")

            # Safe backward-compatibility migration for existing user roles:
            # Normalize legacy job titles (e.g. "Product Lead", "Manager", "Engineer") to title, and set role to USER
            conn.execute(text("""
                UPDATE users
                SET title = role
                WHERE title IS NULL AND role NOT IN ('USER', 'ADMIN', 'SUPER_ADMIN')
            """))
            conn.execute(text("""
                UPDATE users
                SET role = 'USER'
                WHERE role NOT IN ('USER', 'ADMIN', 'SUPER_ADMIN')
            """))

            conn.commit()
        except Exception as e:
            logger.warning(f"Column check or migration notice: {e}")

    # Seed default user only in non-production environments when explicitly enabled
    from app.core.config import settings
    if settings.SEED_DEMO_USER and settings.ENVIRONMENT.lower() != "production":
        db = SessionLocal()
        try:
            default_email = "madan@example.com"
            existing = db.query(User).filter(User.email == default_email).first()
            if not existing:
                default_user = User(
                    email=default_email,
                    hashed_password=get_password_hash("password123"),
                    full_name="Madan RB",
                    role="USER",
                    title="Product Lead",
                    avatar="MR",
                )
                db.add(default_user)
                db.commit()
                logger.info("Default seed user 'madan@example.com' created for local development.")
        except Exception as e:
            logger.warning(f"User seed notice: {e}")
        finally:
            db.close()

    # Initial Super Admin bootstrap on startup if configured in environment and no active super admin exists
    if settings.BOOTSTRAP_SECRET_KEY and settings.BOOTSTRAP_SUPER_ADMIN_EMAIL and settings.BOOTSTRAP_SUPER_ADMIN_PASSWORD:
        db = SessionLocal()
        try:
            from app.services.bootstrap_service import has_active_super_admin, provision_super_admin
            if not has_active_super_admin(db):
                provision_super_admin(
                    db=db,
                    email=settings.BOOTSTRAP_SUPER_ADMIN_EMAIL,
                    password=settings.BOOTSTRAP_SUPER_ADMIN_PASSWORD,
                    full_name=settings.BOOTSTRAP_SUPER_ADMIN_NAME or "Super Administrator",
                    bootstrap_key=settings.BOOTSTRAP_SECRET_KEY,
                    method="env_init_db",
                )
                logger.info(
                    f"Super Admin '{settings.BOOTSTRAP_SUPER_ADMIN_EMAIL}' provisioned during initialization. "
                    "Please unset BOOTSTRAP_SUPER_ADMIN_PASSWORD and BOOTSTRAP_SECRET_KEY from environment."
                )
        except Exception as e:
            logger.warning(f"Bootstrap initialization notice: {e}")
        finally:
            db.close()

    logger.info("Database tables initialized successfully without deleting existing data.")



if __name__ == "__main__":
    init_db()
