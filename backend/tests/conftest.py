import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.session import Base, get_db
from app.main import app
from app.core.config import settings
from app.models.user import User
from app.core.security import get_password_hash, create_access_token
from sqlalchemy import event

# Configure test environment
settings.ENVIRONMENT = "testing"
settings.AI_DEMO_MODE = True

# Shared in-memory SQLite with StaticPool for test isolation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def set_test_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_user(db_session):
    user = User(
        email="test_owner@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Test Owner",
        role="USER",
        avatar="TO",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(auth_user):
    token = create_access_token(auth_user.id, role=auth_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_user(db_session):
    user = User(
        email="admin_owner@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Admin Owner",
        role="ADMIN",
        avatar="AO",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_headers(admin_user):
    token = create_access_token(admin_user.id, role=admin_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def regular_user(auth_user):
    return auth_user


@pytest.fixture(scope="function")
def user_headers(auth_headers):
    return auth_headers

