from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

# local imports from main
from backend.models import auth_models as models
from backend.schemas import auth_schemas as schemas
from backend.api import auth

# Specific local imports
from backend.database import get_db # currently for testing purposes, will migrate later on 



router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", response_model=schemas.UserResponse)
async def register(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user."""
    # Check if username exists
    db_user = db.query(models.User).filter(
        models.User.username == user.username
    ).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    # Check if email exists
    db_user = db.query(models.User).filter(
        models.User.email == user.email
    ).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login", response_model=schemas.Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login and receive access and refresh tokens."""
    # Authenticate user
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()
    
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create tokens
    access_token = auth.create_access_token(
        data={"sub": user.username}
    )
    refresh_token = auth.create_refresh_token(
        data={"sub": user.username}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=schemas.Token)
async def refresh_token(
    token_data: schemas.TokenRefresh,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token."""
    username = auth.verify_token(token_data.refresh_token, "refresh")
    
    # Verify user still exists and is active
    user = db.query(models.User).filter(
        models.User.username == username
    ).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user"
        )
    
    # Create new tokens
    access_token = auth.create_access_token(
        data={"sub": user.username}
    )
    refresh_token = auth.create_refresh_token(
        data={"sub": user.username}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_info(
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Get current user information."""
    return current_user

@router.post("/logout")
async def logout(
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Logout the current user."""
    # In a production app, you might want to:
    # 1. Blacklist the token
    # 2. Clear refresh token from database
    # 3. Log the logout event
    return {"message": "Successfully logged out"}