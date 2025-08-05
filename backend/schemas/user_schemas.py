from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

# User schemas
class UserBase(BaseModel):
    """Base user schema"""
    email: str
    display_name: Optional[str]
    given_name: Optional[str]
    surname: Optional[str]
    job_title: Optional[str]
    department: Optional[str]


class UserResponse(UserBase):
    """Schema for user responses"""
    id: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
    conversations_count: Optional[int] = Field(None, description="Total number of user's conversations")
    active_conversations: Optional[int] = Field(None, description="Number of active conversations")
    archived_conversations: Optional[int] = Field(None, description="Number of archived conversations")
    
    model_config = ConfigDict(from_attributes=True)