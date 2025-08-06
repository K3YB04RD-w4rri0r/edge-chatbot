from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime

from models.messages_model import MessageRole

# Message schemas
class MessageBase(BaseModel):
    """Base message schema"""
    role: MessageRole = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., min_length=1, description="Message content")
    parent_message_id: Optional[int] = Field(None, description="Parent message ID for threading") # (which is not implemented)

class MessageCreate(MessageBase):
    """Schema for creating a new message"""
    conversation_id: Optional[int] = Field(None, description="Conversation ID (set by route)")
    active_attachment_uuids: Optional[List[str]] = Field(
        default=None, 
        description="UUIDs of attachments to include in AI context"
    )
    
    @field_validator('active_attachment_uuids')
    def validate_uuids(cls, v):
        if v is not None:
            # Ensures all UUIDs are valid format
            import re
            uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
            for uuid in v:
                if not uuid_pattern.match(uuid):
                    raise ValueError(f'Invalid UUID format: {uuid}')
        return v

class MessageUpdate(BaseModel):
    """Schema for updating a message"""
    content: Optional[str] = Field(None, min_length=1, description="Updated message content")
    @field_validator('content')
    def content_not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError('Message content cannot be empty')
        return v.strip() if v else v

class MessageResponse(MessageBase):
    """Schema for message responses"""
    id: int
    conversation_id: int
    token_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    edited_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

class ChatResponse(BaseModel):
    user_message: MessageResponse
    assistant_reply: MessageResponse
    error: Optional[str] = None


# unused in the frontend, could be used to lookup old code/a message if functionality gets implemented
# Message list responses
class MessageListResponse(BaseModel):
    """Schema for paginated message list responses"""
    messages: List[MessageResponse]
    conversation_id: int
    total: int = Field(..., description="Total number of messages (before pagination)")
    skip: int = Field(..., description="Number of messages skipped")
    limit: int = Field(..., description="Maximum messages per page")
    
    @property
    def pages(self) -> int:
        """Calculate total number of pages"""
        return (self.total + self.limit - 1) // self.limit if self.limit > 0 else 0
    
    @property
    def current_page(self) -> int:
        """Calculate current page number (1-based)"""
        return (self.skip // self.limit) + 1 if self.limit > 0 else 1
