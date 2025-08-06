from fastapi import APIRouter, Request, HTTPException, Depends, Query, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select
from starlette.responses import RedirectResponse
from typing import List
from datetime import datetime, timezone, timedelta
import logging
import io


from shared_variables import limiter, settings
from services.misc import get_current_user

from databases.conversations_database import get_db
from databases.file_storage_database import storage_backend, file_service, AzureFileStorage

from models.conversations_model import Conversation
from models.attachments_model import Attachment, AttachmentStatus, AttachmentActivityStatus, AttachmentType

from schemas.attachment_schemas import (
    AttachmentUploadRequest,
    AttachmentUploadResponse,
    AttachmentResponse,
    BatchAttachmentActivityUpdate
)

from routes.route_helpers import get_or_create_user, verify_conversation_ownership

logger = logging.getLogger(__name__)
UTC = timezone.utc
router = APIRouter(prefix="/api", tags=["conversations"])

# ==================== Attachment Routes ====================

@router.post("/conversations/{conversation_id}/attachments/initiate", response_model=AttachmentUploadResponse)
@limiter.limit("30/minute")
async def initiate_attachment_upload(
    conversation_id: int,
    request: Request,
    upload_request: AttachmentUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Initiate file upload process. Creates attachment record and returns upload details.
    
    For direct upload (S3/Azure), returns a presigned URL.
    For API upload, returns the attachment ID for the subsequent upload endpoint.
    """
    user = await get_or_create_user(db, current_user)
    conversation = await verify_conversation_ownership(db, conversation_id, user.id, load_relations=False)
    
    # Validate file size
    if upload_request.file_size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size} bytes"
        )
    
    # Check conversation attachment limits
    attachment_count = await db.scalar(
        select(func.count(Attachment.id))
        .filter(
            Attachment.conversation_id == conversation_id,
            Attachment.status != AttachmentStatus.DELETED.value
        )
    )
    
    if attachment_count >= settings.max_attachments_per_conversation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.max_attachments_per_conversation} attachments per conversation"
        )
    
    # Create attachment record
    attachment = Attachment(
        conversation_id=conversation_id,
        uploader_id=user.id,
        filename=upload_request.filename,
        original_filename=upload_request.filename,
        content_type=upload_request.content_type,
        file_size=upload_request.file_size,
        attachment_type=file_service.classify_attachment_type(
            upload_request.content_type, 
            upload_request.filename
        ),
        status=AttachmentStatus.PENDING.value,
        file_hash="pending"  # Will be updated after upload
    )
    
    # Generate storage path
    attachment.storage_path = file_service.generate_storage_path(
        user_id=user.id,
        conversation_id=conversation_id,
        filename=upload_request.filename
    )
    
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    
    # Prepare response based on storage backend
    response = AttachmentUploadResponse(
        attachment_id=attachment.id,
        uuid=attachment.uuid,
        upload_method="api"  # Default to API upload
    )
    
    # If using cloud storage, generate presigned URL for direct upload
    if isinstance(storage_backend, AzureFileStorage):
        try:
            presigned_url = await storage_backend.generate_presigned_url(
                attachment.storage_path,
                expires_in=settings.upload_url_expiry  # e.g., 3600 seconds
            )
            response.upload_url = presigned_url
            response.upload_method = "direct"
            response.expires_at = datetime.now(UTC) + timedelta(seconds=settings.upload_url_expiry)
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            # Fall back to API upload method
    
    logger.info(f"User {user.email} initiated upload for attachment {attachment.uuid}")
    return response


@router.post("/conversations/{conversation_id}/attachments/{attachment_uuid}/upload")
@limiter.limit("20/minute")
async def upload_attachment_content(
    conversation_id: int,
    attachment_uuid: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload file content via API (for small files or when direct upload not available).
    
    This endpoint is used when:
    - Storage backend doesn't support presigned URLs
    - File is small enough for API upload
    - Direct upload failed and falling back to API
    """
    user = await get_or_create_user(db, current_user)
    
    # Get attachment and verify ownership
    result = await db.execute(
        select(Attachment)
        .join(Conversation)
        .filter(
            and_(
                Attachment.uuid == attachment_uuid,
                Attachment.conversation_id == conversation_id,
                Conversation.owner_id == user.id,
                Attachment.status == AttachmentStatus.PENDING.value
            )
        )
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found or already uploaded"
        )
    
    # Validate file size matches
    content = await file.read()
    if len(content) != attachment.file_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size mismatch. Expected {attachment.file_size}, got {len(content)}"
        )
    
    # Reset file position
    await file.seek(0)
    
    try:
        # Calculate file hash
        file_buffer = io.BytesIO(content)
        file_hash = file_service.calculate_file_hash(file_buffer)
        
        # Check for duplicate files in same conversation
        duplicate = await db.scalar(
            select(Attachment)
            .filter(
                and_(
                    Attachment.conversation_id == conversation_id,
                    Attachment.file_hash == file_hash,
                    Attachment.id != attachment.id,
                    Attachment.status == AttachmentStatus.UPLOADED.value
                )
            )
        )
        
        if duplicate:
            # Delete the pending attachment and return error
            await db.delete(attachment)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This file already exists in the conversation as '{duplicate.filename}'"
            )
        
        # Detect actual content type
        detected_type = file_service.detect_content_type(file_buffer)
        if detected_type != attachment.content_type:
            logger.warning(
                f"Content type mismatch for {attachment.uuid}: "
                f"declared {attachment.content_type}, detected {detected_type}"
            )
            # Update to detected type for security
            attachment.content_type = detected_type
            attachment.attachment_type = file_service.classify_attachment_type(
                detected_type,
                attachment.filename
            )
        
        # Store file
        file_buffer.seek(0)
        storage_path = await storage_backend.store(file_buffer, attachment.storage_path)
        
        # Update attachment record
        attachment.file_hash = file_hash
        attachment.status = AttachmentStatus.UPLOADED.value
        attachment.virus_scanned = False  # Queue for virus scanning
        
        # Extract metadata for specific file types
        if attachment.attachment_type == AttachmentType.IMAGE:
            try:
                from PIL import Image
                file_buffer.seek(0)
                with Image.open(file_buffer) as img:
                    attachment.extra_metadata = {
                        "width": img.width,
                        "height": img.height,
                        "format": img.format,
                        "mode": img.mode
                    }
            except Exception as e:
                logger.error(f"Failed to extract image metadata: {e}")
        
        await db.commit()
        await db.refresh(attachment)
        
        # Queue for virus scanning (if enabled)
        if settings.enable_virus_scanning:
            # background_tasks.add_task(scan_attachment_for_viruses, attachment.id)
            pass
        
        logger.info(f"Successfully uploaded attachment {attachment.uuid}")
        
        return AttachmentResponse.model_validate(attachment)
        
    except HTTPException:
        raise
    except Exception as e:
        # Clean up on failure
        attachment.status = AttachmentStatus.FAILED.value
        await db.commit()
        
        logger.error(f"Failed to upload attachment {attachment.uuid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file"
        )


@router.get("/conversations/{conversation_id}/attachments", response_model=List[AttachmentResponse])
@limiter.limit("100/minute")
async def list_conversation_attachments(
    conversation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    include_deleted: bool = Query(False, description="Include soft-deleted attachments")
):
    """
    List all attachments for a conversation.
    
    Returns attachments ordered by creation date (newest first).
    """
    user = await get_or_create_user(db, current_user)
    conversation = await verify_conversation_ownership(db, conversation_id, user.id, load_relations=False)
    
    # Build query
    query = select(Attachment).filter(Attachment.conversation_id == conversation_id)
    
    if not include_deleted:
        query = query.filter(Attachment.status != AttachmentStatus.DELETED.value)
    
    query = query.order_by(Attachment.created_at.desc())
    
    result = await db.execute(query)
    attachments = result.scalars().all()
    
    # Generate download URLs for uploaded attachments
    response_attachments = []
    for attachment in attachments:
        att_response = AttachmentResponse.model_validate(attachment)
        
        # Generate download URL if file is uploaded
        if attachment.status == AttachmentStatus.UPLOADED.value:
            att_response.download_url = f"/api/conversations/{conversation_id}/attachments/{attachment.uuid}/download"
            
            # Generate thumbnail URL for images (if thumbnail service is implemented)
            if attachment.attachment_type == AttachmentType.IMAGE:
                att_response.thumbnail_url = f"/api/conversations/{conversation_id}/attachments/{attachment.uuid}/thumbnail"
        
        response_attachments.append(att_response)
    
    return response_attachments


@router.get("/conversations/{conversation_id}/attachments/{attachment_uuid}/download")
@limiter.limit("60/minute")
async def download_attachment(
    conversation_id: int,
    attachment_uuid: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    disposition: str = Query("inline", regex="^(inline|attachment)$")
):
    """
    Download or view an attachment.
    
    Args:
        disposition: 'inline' to view in browser, 'attachment' to force download
    """
    user = await get_or_create_user(db, current_user)
    
    # Get attachment with ownership verification
    result = await db.execute(
        select(Attachment)
        .join(Conversation)
        .filter(
            and_(
                Attachment.uuid == attachment_uuid,
                Attachment.conversation_id == conversation_id,
                Conversation.owner_id == user.id,
                Attachment.status == AttachmentStatus.UPLOADED.value
            )
        )
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found"
        )
    
    try:
        # For cloud storage, redirect to presigned URL
        if isinstance(storage_backend, AzureFileStorage):
            download_url = await storage_backend.generate_presigned_url(
                attachment.storage_path,
                expires_in=3600  # 1 hour
            )
            return RedirectResponse(url=download_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        
        
    except Exception as e:
        logger.error(f"Failed to download attachment {attachment.uuid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file"
        )


@router.delete("/conversations/{conversation_id}/attachments/{attachment_uuid}")
@limiter.limit("30/minute")
async def delete_attachment(
    conversation_id: int,
    attachment_uuid: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    permanent: bool = Query(False, description="Permanently delete the file")
):
    """
    Delete an attachment (soft delete by default).
    
    Args:
        permanent: If True, permanently deletes file from storage
    """
    user = await get_or_create_user(db, current_user)
    
    # Get attachment with ownership verification
    result = await db.execute(
        select(Attachment)
        .join(Conversation)
        .filter(
            and_(
                Attachment.uuid == attachment_uuid,
                Attachment.conversation_id == conversation_id,
                Conversation.owner_id == user.id,
                Attachment.status != AttachmentStatus.DELETED.value
            )
        )
    )
    attachment = result.scalar_one_or_none()
    
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found"
        )
    
    if permanent:
        # Permanently delete from storage
        try:
            if attachment.status == AttachmentStatus.UPLOADED.value:
                await storage_backend.delete(attachment.storage_path)
        except Exception as e:
            logger.error(f"Failed to delete file from storage: {e}")
        
        # Delete from database
        await db.delete(attachment)
        logger.info(f"Permanently deleted attachment {attachment.uuid}")
    else:
        # Soft delete
        attachment.soft_delete()
        logger.info(f"Soft deleted attachment {attachment.uuid}")
    
    await db.commit()
    
    return {"detail": "Attachment deleted successfully"}


@router.put("/conversations/{conversation_id}/attachments/batch-activity")
@limiter.limit("60/minute")
async def update_attachment_activity_status(
    conversation_id: int,
    request: Request,
    batch_update: BatchAttachmentActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Batch update attachment activity status (for saving toggle preferences).
    
    Request body example:
    {
        "updates": [
            {"uuid": "uuid-123", "activity_status": "active"},
            {"uuid": "uuid-456", "activity_status": "inactive"}
        ]
    }
    """
    user = await get_or_create_user(db, current_user)
    conversation = await verify_conversation_ownership(db, conversation_id, user.id, load_relations=False)
    
    # Validate update data
    valid_statuses = {AttachmentActivityStatus.ACTIVE.value, AttachmentActivityStatus.INACTIVE.value}
    uuid_to_status = {}
    
    for update in batch_update.updates:
        if "uuid" not in update or "activity_status" not in update:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each update must have 'uuid' and 'activity_status'"
            )
        
        if update["activity_status"] not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid activity_status: {update['activity_status']}"
            )
        
        uuid_to_status[update["uuid"]] = update["activity_status"]
    
    # Update attachments
    result = await db.execute(
        select(Attachment)
        .filter(
            and_(
                Attachment.conversation_id == conversation_id,
                Attachment.uuid.in_(list(uuid_to_status.keys())),
                Attachment.status == AttachmentStatus.UPLOADED.value
            )
        )
    )
    attachments = result.scalars().all()
    
    updated_count = 0
    for attachment in attachments:
        if attachment.uuid in uuid_to_status:
            attachment.activity_status = uuid_to_status[attachment.uuid]
            updated_count += 1
    
    await db.commit()
    
    return {
        "detail": f"Updated {updated_count} attachment(s)",
        "updated": updated_count,
        "requested": len(batch_update.updates)
    }