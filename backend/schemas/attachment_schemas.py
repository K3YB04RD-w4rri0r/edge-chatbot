from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

from backend.models.attachments_model import AttachmentStatus, AttachmentActivityStatus, AttachmentType
from shared_variables import settings


class AttachmentMetadata(BaseModel):
    """Metadata for different attachment types"""
    # For images
    width: Optional[int] = None
    height: Optional[int] = None
    
    # For documents
    page_count: Optional[int] = None
    
    # Additional custom metadata
    extra: Optional[Dict[str, Any]] = None

class AttachmentBase(BaseModel):
    """Base attachment schema"""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)
    file_size: int = Field(..., gt=0, description="File size in bytes")

class AttachmentUploadRequest(BaseModel):
    """Schema for initiating file upload"""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)
    file_size: int = Field(..., gt=0, le=settings.max_file_size, description="File size in bytes (max 100MB)")
    
    @field_validator('content_type')
    def validate_content_type(cls, v):
        # Add your allowed Attachment types
        ALLOWED_TYPES = settings.allowed_content_types
        if v not in ALLOWED_TYPES:
            raise ValueError(f'Content type {v} is not allowed')
        return v

class AttachmentUploadResponse(BaseModel):
    """Response after initiating upload"""
    attachment_id: int
    uuid: str
    upload_url: Optional[str] = Field(None, description="Presigned URL for upload (if using direct upload)")
    upload_method: str = Field("api", description="Upload method: 'api' or 'direct'")
    expires_at: Optional[datetime] = Field(None, description="Upload URL expiration")

class AttachmentResponse(AttachmentBase):
    """Schema for attachment responses"""
    id: int
    uuid: str
    uploader_id: str
    original_filename: str
    attachment_type: AttachmentType
    status: AttachmentStatus
    activity_status: AttachmentActivityStatus
    extra_metadata: Optional[AttachmentMetadata]
    virus_scanned: bool

    created_at: datetime
    updated_at: datetime
    
    # Download URL (generated dynamically)
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None  # For images but currently doesn't work
    
    model_config = ConfigDict(from_attributes=True)


# Unused 
class AttachmentCompleteUpload(BaseModel):
    """Schema for completing file upload"""
    file_hash: Optional[str] = Field(None, description="SHA-256 hash of the file")
    extra_metadata: Optional[AttachmentMetadata] = None

class AttachmentActivityUpdate(BaseModel):
    uuid: str
    activity_status: AttachmentActivityStatus

class BatchAttachmentActivityUpdate(BaseModel):
    updates: List[AttachmentActivityUpdate]
    
    @field_validator('updates')
    def validate_not_empty(cls, v):
        if not v:
            raise ValueError('Updates list cannot be empty')
        return v
