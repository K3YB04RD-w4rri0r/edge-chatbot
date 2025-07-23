from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from backend.database import Base

class User(Base):
    """User model for Microsoft authentication only"""
    __tablename__ = "users"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    microsoft_id = Column(String(255), unique=True, nullable=False, index=True)  # 'oid' from Microsoft
    
    # Profile information from Microsoft
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    first_name = Column(String(255))
    last_name = Column(String(255))
    
    # Optional Microsoft profile data
    job_title = Column(String(255))
    department = Column(String(255))
    office_location = Column(String(255))
    
    # Organization info
    tenant_id = Column(String(255), nullable=False)  # Microsoft tenant ID
    tenant_name = Column(String(255))  # Your organization name
    
    # Application-specific fields
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    # You can add custom roles/permissions
    roles = Column(JSON, default=list)  # e.g., ["admin", "editor", "viewer"]
    
    # Tracking
    last_login = Column(DateTime(timezone=True))
    login_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Optional: Store user preferences
    preferences = Column(JSON, default=dict)  # e.g., {"theme": "dark", "language": "en"}
    
    def __repr__(self):
        return f"<User(email={self.email}, name={self.full_name})>"
    
    @property
    def display_name(self):
        """Return a display name for the UI"""
        return self.full_name or self.email.split('@')[0]
    
    @property
    def is_authenticated(self):
        """Required for some Flask/FastAPI extensions"""
        return True
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role"""
        return role in (self.roles or [])
    
    def add_role(self, role: str):
        """Add a role to the user"""
        if self.roles is None:
            self.roles = []
        if role not in self.roles:
            self.roles = self.roles + [role]  # SQLAlchemy JSON update pattern
    
    def remove_role(self, role: str):
        """Remove a role from the user"""
        if self.roles and role in self.roles:
            self.roles = [r for r in self.roles if r != role]


class UserSession(Base):
    """Track active user sessions"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    
    # Session data
    ip_address = Column(String(45))  # Supports IPv6
    user_agent = Column(Text)
    
    # Tokens (encrypted in production!)
    access_token = Column(Text)  # Your app's token, not Microsoft's
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed = Column(DateTime(timezone=True), default=func.now())
    
    # Optional: Track what the user is doing
    last_activity = Column(String(255))  # e.g., "viewed_dashboard", "edited_item_5"
    
    @property
    def is_expired(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def is_active(self):
        return not self.is_expired
