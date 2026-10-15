from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    AuthTokenResponse,
)
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    check_login_rate_limit,
    record_login_attempt,
    clear_login_attempts,
)
from app.api.deps import get_current_user_required

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower()
    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # Compute initials
    name = (req.full_name or email_clean.split("@")[0]).strip()
    words = name.split()
    initials = (words[0][0] + words[1][0]).upper() if len(words) > 1 else name[:2].upper()

    user = User(
        email=email_clean,
        hashed_password=get_password_hash(req.password),
        full_name=name,
        role="USER",
        avatar=initials or "U",
        is_active=True,
        token_version=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, role=user.role, token_version=user.token_version)
    return AuthTokenResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthTokenResponse)
def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower()

    if not check_login_rate_limit(email_clean):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 5 minutes before trying again."
        )

    user = db.query(User).filter(User.email == email_clean).first()
    if not user or not verify_password(req.password, user.hashed_password):
        record_login_attempt(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact an administrator."
        )

    clear_login_attempts(email_clean)
    token = create_access_token(user.id, role=user.role, token_version=user.token_version)
    return AuthTokenResponse(token=token, user=UserResponse.model_validate(user))



@router.get("/me", response_model=UserResponse)
def get_current_profile(current_user: User = Depends(get_current_user_required)):
    return UserResponse.model_validate(current_user)
