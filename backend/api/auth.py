# auth.py - Microsoft Authentication
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import httpx
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.models.auth_models import User, UserSession
from backend.database import get_db
from config import settings


# Security scheme for FastAPI docs
security = HTTPBearer()

# Microsoft OAuth endpoints
MICROSOFT_OAUTH_AUTHORIZE = f"{settings.microsoft_authority_url}/oauth2/v2.0/authorize"
MICROSOFT_OAUTH_TOKEN = f"{settings.microsoft_authority_url}/oauth2/v2.0/token"


class MicrosoftAuth:
    """Handle Microsoft OAuth flow"""
    
    @staticmethod
    def get_auth_url(state: str) -> str:
        """Generate Microsoft login URL"""
        params = {
            "client_id": settings.microsoft_client_id,
            "response_type": "code",
            "redirect_uri": settings.redirect_uri,
            "response_mode": "query",
            "scope": " ".join(settings.microsoft_scopes),
            "state": state,  # CSRF protection
            "prompt": "select_account",  # Force account selection
        }
        return f"{MICROSOFT_OAUTH_AUTHORIZE}?{urlencode(params)}"
    
    @staticmethod
    async def exchange_code_for_token(code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens"""
        data = {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "code": code,
            "redirect_uri": settings.redirect_uri,
            "grant_type": "authorization_code",
            "scope": " ".join(settings.microsoft_scopes),
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                MICROSOFT_OAUTH_TOKEN,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange code: {response.text}"
                )
            
            return response.json()
    
    @staticmethod
    def decode_id_token(id_token: str) -> Dict[str, Any]:
        """Decode Microsoft ID token (without validation for now)"""
        # In production, you should validate the token signature
        # For now, we'll just decode it
        try:
            # Decode without verification (Microsoft handles the verification)
            claims = jwt.get_unverified_claims(id_token)
            return claims
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid ID token: {str(e)}"
            )


class SessionManager:
    """Manage user sessions"""
    
    @staticmethod
    def create_session_token(user_id: int, session_id: str) -> str:
        """Create a session token"""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_lifetime_hours)
        
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
        }
        
        return jwt.encode(payload, settings.session_secret_key, algorithm=settings.algorithm)
    
    @staticmethod
    def verify_session_token(token: str) -> Dict[str, Any]:
        """Verify and decode session token"""
        try:
            payload = jwt.decode(
                token, 
                settings.session_secret_key, 
                algorithms=[settings.algorithm]
            )
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @staticmethod
    async def create_user_session(
        db: Session,
        user_id: int,
        request: Request
    ) -> UserSession:
        """Create a new user session"""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_lifetime_hours)
        
        # Get request info
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]  # Limit length
        
        # Check max sessions
        existing_sessions = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.expires_at > datetime.now(timezone.utc)
        ).count()
        
        if existing_sessions >= settings.max_sessions_per_user:
            # Remove oldest session
            oldest = db.query(UserSession).filter(
                UserSession.user_id == user_id
            ).order_by(UserSession.created_at).first()
            if oldest:
                db.delete(oldest)
        
        # Create new session
        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        
        return session
    
    @staticmethod
    def cleanup_expired_sessions(db: Session):
        """Remove expired sessions"""
        db.query(UserSession).filter(
            UserSession.expires_at < datetime.now(timezone.utc)
        ).delete()
        db.commit()


# Dependency functions
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from session token"""
    token = credentials.credentials
    
    # Verify token
    try:
        payload = SessionManager.verify_session_token(token)
    except HTTPException:
        raise
    
    # Get session
    session = db.query(UserSession).filter(
        UserSession.session_id == payload["session_id"],
        UserSession.user_id == payload["user_id"],
        UserSession.expires_at > datetime.now(timezone.utc)
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last accessed
    session.last_accessed = datetime.now(timezone.utc)
    db.commit()
    
    # Get user
    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure the current user is active"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Ensure the current user is an admin"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def require_roles(*roles: str):
    """Dependency to require specific roles"""
    async def role_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        user_roles = current_user.roles or []
        if not any(role in user_roles for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {', '.join(roles)}"
            )
        return current_user
    return role_checker
