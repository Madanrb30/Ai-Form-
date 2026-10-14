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

            conn.commit()
        except Exception as e:
            logger.warning(f"Column check or migration notice: {e}")

    # Seed default user only in non-production environments when explicitly enabled
    from app.core.config import settings
    if settings.SEED_DEMO_USER:
        db = SessionLocal()
        try:
            default_email = "madan@example.com"
            existing = db.query(User).filter(User.email == default_email).first()
            if not existing:
                default_user = User(
                    email=default_email,
                    hashed_password=get_password_hash("password123"),
                    full_name="Madan RB",
                    role="Product Lead",
                    avatar="MR",
                )
                db.add(default_user)
                db.commit()
                logger.info("Default seed user 'madan@example.com' created for local development.")
        except Exception as e:
            logger.warning(f"User seed notice: {e}")
        finally:
            db.close()

    logger.info("Database tables initialized successfully without deleting existing data.")



if __name__ == "__main__":
    init_db()
