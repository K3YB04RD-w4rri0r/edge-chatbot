# auth_routes.py - Microsoft OAuth Routes
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.models.auth_models import User, UserSession
from backend.schemas import auth_schemas as schemas
from backend.api.auth import (
    MicrosoftAuth, 
    SessionManager, 
    get_current_user, 
    get_current_active_user,
    get_admin_user
)
from backend.database import get_db
from config import settings


router = APIRouter(prefix="/auth", tags=["authentication"])

# Store state tokens temporarily (in production, use Redis or database)
# This is for CSRF protection during OAuth flow
auth_states = {}


@router.get("/microsoft/login", response_model=schemas.MicrosoftAuthUrl)
async def microsoft_login():
    """
    Get Microsoft login URL
    
    This initiates the OAuth flow by returning the URL where users
    should be redirected to login with Microsoft.
    """
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state temporarily (expires in 10 minutes)
    auth_states[state] = {
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc).timestamp() + 600  # 10 minutes
    }
    
    # Clean up old states
    current_time = datetime.now(timezone.utc).timestamp()
    auth_states_copy = auth_states.copy()
    for key, value in auth_states_copy.items():
        if value["expires_at"] < current_time:
            del auth_states[key]
    
    auth_url = MicrosoftAuth.get_auth_url(state)
    
    return {
        "auth_url": auth_url,
        "state": state
    }


@router.get("/microsoft/callback")
async def microsoft_callback(
    code: str,
    state: str,
    session_state: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Handle Microsoft OAuth callback
    
    Microsoft redirects here after user login. We exchange the code
    for tokens and create/update the user account.
    """
    # Verify state token
    if state not in auth_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token"
        )
    
    # Remove used state
    del auth_states[state]
    
    try:
        # Exchange code for tokens
        token_data = await MicrosoftAuth.exchange_code_for_token(code)
        
        # Decode ID token to get user info
        id_token = token_data.get("id_token")
        if not id_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No ID token received"
            )
        
        user_info = MicrosoftAuth.decode_id_token(id_token)
        
        # Extract user data
        microsoft_id = user_info.get("oid")  # Object ID is the unique identifier
        email = user_info.get("email") or user_info.get("preferred_username")
        full_name = user_info.get("name", "")
        first_name = user_info.get("given_name", "")
        last_name = user_info.get("family_name", "")
        tenant_id = user_info.get("tid", "")
        
        if not microsoft_id or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required user information from Microsoft"
            )
        
        # Check if user exists
        user = db.query(User).filter(User.microsoft_id == microsoft_id).first()
        
        if not user:
            # Check by email (for migration scenarios)
            user = db.query(User).filter(User.email == email).first()
            
            if user:
                # Update existing user with Microsoft ID
                user.microsoft_id = microsoft_id
                user.tenant_id = tenant_id
            else:
                # Create new user
                user = User(
                    microsoft_id=microsoft_id,
                    email=email,
                    full_name=full_name,
                    first_name=first_name,
                    last_name=last_name,
                    tenant_id=tenant_id,
                    is_active=True,
                    is_superuser=False,  # Set manually for first admin
                    roles=["user"],  # Default role
                )
                db.add(user)
        
        # Update user info from Microsoft (in case it changed)
        user.full_name = full_name
        user.first_name = first_name
        user.last_name = last_name
        user.last_login = datetime.now(timezone.utc)
        user.login_count = (user.login_count or 0) + 1
        
        db.commit()
        db.refresh(user)
        
        # Create session
        session = await SessionManager.create_user_session(db, user.id, request)
        session_token = SessionManager.create_session_token(user.id, session.session_id)
        
        # Redirect to frontend with token
        # In production, you might want to use a more secure method
        redirect_url = f"{settings.post_login_redirect_url}?token={session_token}"
        return RedirectResponse(url=redirect_url)
        
    except HTTPException:
        raise
    except Exception as e:
        # Log the error in production
        print(f"OAuth callback error: {str(e)}")
        
        # Redirect to frontend with error
        error_url = f"{settings.frontend_url}/login?error=auth_failed"
        return RedirectResponse(url=error_url)


@router.post("/token/from-callback", response_model=schemas.Token)
async def exchange_callback_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Exchange callback token for API token
    
    Alternative to URL-based token passing. Frontend can call this
    after receiving the token from the callback redirect.
    """
    try:
        # Verify the token
        payload = SessionManager.verify_session_token(token)
        
        # Get user
        user = db.query(User).filter(User.id == payload["user_id"]).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.session_lifetime_hours * 3600,
            "user": user
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


@router.get("/me", response_model=schemas.UserMe)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user information"""
    return current_user


@router.get("/sessions", response_model=schemas.SessionList)
async def get_user_sessions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all active sessions for the current user"""
    sessions = db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.expires_at > datetime.now(timezone.utc)
    ).order_by(UserSession.created_at.desc()).all()
    
    # Get current session ID from token
    # This would need to be passed from the auth dependency
    
    return {
        "sessions": sessions,
        "current_session_id": ""  # Set from current request
    }


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Logout the current user
    
    This invalidates the current session. For full Microsoft logout,
    users should be redirected to Microsoft's logout endpoint.
    """
    # Get current session from token (this would need to be enhanced)
    # For now, we'll just clear all user sessions
    db.query(UserSession).filter(
        UserSession.user_id == current_user.id
    ).delete()
    db.commit()
    
    # Optional: Redirect to Microsoft logout
    # This will log them out of Microsoft too
    # logout_url = f"{settings.microsoft_authority_url}/oauth2/v2.0/logout"
    # post_logout_url = settings.post_logout_redirect_url
    # return RedirectResponse(f"{logout_url}?post_logout_redirect_uri={post_logout_url}")
    
    return {"message": "Successfully logged out"}


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Revoke a specific session"""
    session = db.query(UserSession).filter(
        UserSession.session_id == session_id,
        UserSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    db.delete(session)
    db.commit()
    
    return {"message": "Session revoked"}


# Admin endpoints
@router.get("/users", response_model=schemas.UserListResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    query = db.query(User)
    
    # Apply filters
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    if search:
        query = query.filter(
            db.or_(
                User.email.contains(search),
                User.full_name.contains(search),
                User.department.contains(search)
            )
        )
    
    # Pagination
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "users": users,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.patch("/users/{user_id}", response_model=schemas.UserResponse)
async def update_user(
    user_id: int,
    update_data: schemas.UserAdminUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    return user


@router.post("/make-admin/{user_id}")
async def make_user_admin(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Make a user an admin (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_superuser = True
    user.add_role("admin")
    
    db.commit()
    
    return {"message": f"User {user.email} is now an admin"}
