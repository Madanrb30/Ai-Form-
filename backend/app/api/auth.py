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
)
from app.api.deps import get_current_user_required

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email.strip().lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # Compute initials
    name = (req.full_name or req.email.split("@")[0]).strip()
    words = name.split()
    initials = (words[0][0] + words[1][0]).upper() if len(words) > 1 else name[:2].upper()

    user = User(
        email=req.email.strip().lower(),
        hashed_password=get_password_hash(req.password),
        full_name=name,
        role="User",
        avatar=initials or "U",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return AuthTokenResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthTokenResponse)
def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.strip().lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    token = create_access_token(user.id)
    return AuthTokenResponse(token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def get_current_profile(current_user: User = Depends(get_current_user_required)):
    return UserResponse.model_validate(current_user)
