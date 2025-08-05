from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


from backend.models.conversations_model import ModelChoice
from backend.models.messages_model import MessageRole

from backend.schemas.conversation_schemas import ConversationStatus



class PaginationParams(BaseModel):
    """Reusable pagination parameters"""
    skip: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(100, ge=1, le=1000, description="Maximum items to return")

class BulkOperationResponse(BaseModel):
    """Response for bulk operations"""
    message: str
    processed_count: int
    success_count: int
    error_count: int = 0
    errors: Optional[List[dict]] = None

class SearchParams(BaseModel):
    """Search parameters"""
    query: str = Field(..., min_length=1, description="Search query")
    fields: List[str] = Field(["conversation_title", "content"], description="Fields to search in")
    status: Optional[ConversationStatus] = None
    model_choice: Optional[ModelChoice] = None
    message_role: Optional[MessageRole] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None



# the next two functions are redundant because archiving is basically the same as soft deleting but 
# could use the archive to keep chats more that 15 days though 
class BulkArchiveRequest(BaseModel):
    conversation_ids: List[int]

class BulkDeleteRequest(BaseModel):
    conversation_ids: List[int]
