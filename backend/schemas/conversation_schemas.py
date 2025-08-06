from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

from models.conversations_model import ModelChoice, ModelInstructions

from schemas.attachment_schemas import AttachmentResponse
from schemas.message_schemas import MessageCreate, MessageResponse



class ConversationStatus(str, Enum):
    """Valid conversation status values"""
    active = "active"
    archived = "archived"
    deleted = "deleted"

# Conversation schemas
class ConversationBase(BaseModel):
    """Base conversation schema"""
    conversation_title: str = Field(..., min_length=1, max_length=255, description="Conversation Title")
    model_choice: ModelChoice = Field(ModelChoice.GPT_4_1_NANO, description="The model to use for the conversation")
    model_instructions: ModelInstructions = Field(ModelInstructions.GENERAL_ASSISTANT, description="The model instructions to use")

class ConversationCreate(ConversationBase):
    """Schema for creating a new conversation"""
    initial_message: Optional[MessageCreate] = Field(None, description="Initial message for the conversation")
    
    @field_validator('conversation_title')
    def title_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

class ConversationUpdate(BaseModel):
    """Schema for updating a conversation"""
    conversation_title: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[ConversationStatus] = None
    model_choice: Optional[ModelChoice] = None
    model_instructions: Optional[ModelInstructions] = None
    
    @field_validator('conversation_title')
    def title_not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError('Conversation Title cannot be empty')
        return v.strip() if v else v
    
    model_config = ConfigDict(from_attributes=True)

class FullConversationResponse(ConversationBase):
    """Schema for conversation responses"""
    id: int
    owner_id: str
    status: ConversationStatus
    token_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    accessed_at: Optional[datetime]
    
    # Include messages and attachments in response (useful for the initial conversation loading. Uses specific just messages and just Attachments for faster chatbot querying)
    messages: Optional[List[MessageResponse]] = Field(None, description="Messages in the conversation")
    attachments: Optional[List[AttachmentResponse]] = Field(None, description="Attachments in the conversation")

    model_config = ConfigDict(from_attributes=True)


# unused in the frontend
class ConversationSummaryResponse(BaseModel):
    """Schema for conversation list responses (without messages or attachments)"""
    id: int
    owner_id: str
    conversation_title: str
    status: ConversationStatus
    model_choice: ModelChoice
    model_instructions: ModelInstructions
    token_count: Optional[int]
    message_count: Optional[int] = Field(None, description="Number of messages in conversation")
    last_message_at: Optional[datetime] = Field(None, description="Timestamp of last message")
    created_at: datetime
    updated_at: datetime
    accessed_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

# unused in the frontend
class ConversationWithMessagesResponse(ConversationBase):
    """Schema for conversation responses (without attachments)"""
    id: int
    owner_id: str
    status: ConversationStatus
    token_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    accessed_at: Optional[datetime]
    
    messages: Optional[List[MessageResponse]] = Field(None, description="Messages in the conversation")
    model_config = ConfigDict(from_attributes=True)

# unused in the frontend
class ConversationWithAttachmentsResponse(ConversationBase):
    """Schema for conversation responses"""
    id: int
    owner_id: str
    status: ConversationStatus
    token_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    accessed_at: Optional[datetime]
    
    # Include messages and not attachments in response
    attachments: Optional[List[AttachmentResponse]] = Field(None, description="Attachments in the conversation")

    model_config = ConfigDict(from_attributes=True)

# unused in the frontend 
# In the event you guys eventually want to be able to lookup your own conversations
class ConversationListResponse(BaseModel):
    """Schema for paginated conversation list responses"""
    conversations: List[ConversationSummaryResponse]
    total: int = Field(..., description="Total number of conversations (before pagination)")
    skip: int = Field(..., description="Number of conversations skipped")
    limit: int = Field(..., description="Maximum conversations per page")
    
    @property
    def pages(self) -> int:
        """Calculate total number of pages"""
        return (self.total + self.limit - 1) // self.limit if self.limit > 0 else 0
    
    @property
    def current_page(self) -> int:
        """Calculate current page number (1-based)"""
        return (self.skip // self.limit) + 1 if self.limit > 0 else 1

