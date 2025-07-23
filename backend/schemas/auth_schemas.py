from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Microsoft OAuth Schemas
class MicrosoftAuthUrl(BaseModel):
    """Response with Microsoft login URL"""
    auth_url: str
    state: str  # CSRF protection

class MicrosoftCallback(BaseModel):
    """Microsoft OAuth callback data"""
    code: str
    state: str
    session_state: Optional[str] = None

class MicrosoftUser(BaseModel):
    """User data from Microsoft"""
    microsoft_id: str = Field(..., description="Microsoft oid")
    email: EmailStr
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    tenant_id: str

# Application User Schemas
class UserBase(BaseModel):
    """Base user information"""
    email: EmailStr
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None

class UserResponse(UserBase):
    """User response with all fields"""
    id: int
    microsoft_id: str
    tenant_id: str
    is_active: bool
    is_superuser: bool
    roles: List[str] = []
    last_login: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserMe(UserResponse):
    """Current user with additional info"""
    login_count: int
    preferences: Dict[str, Any] = {}

class UserUpdate(BaseModel):
    """Fields users can update about themselves"""
    # Users can't change their Microsoft data
    preferences: Optional[Dict[str, Any]] = None

class UserAdminUpdate(BaseModel):
    """Fields admins can update"""
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    roles: Optional[List[str]] = None

# Token Schemas
class Token(BaseModel):
    """Application token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse

class TokenData(BaseModel):
    """Data stored in token"""
    user_id: int
    email: str
    session_id: str

# Session Schemas
class SessionInfo(BaseModel):
    """Active session information"""
    session_id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime

class SessionList(BaseModel):
    """List of user's active sessions"""
    sessions: List[SessionInfo]
    current_session_id: str

# Error Schemas
class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    details: Optional[str] = None
    code: Optional[str] = None

# Admin Schemas
class UserListResponse(BaseModel):
    """Paginated user list"""
    users: List[UserResponse]
    total: int
    page: int
    page_size: int
    
class UserFilters(BaseModel):
    """Filters for user search"""
    email: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[List[str]] = None
