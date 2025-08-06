from fastapi import APIRouter, Request, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select, update, case
from datetime import timezone
import logging
from typing import List

from shared_variables import limiter, settings
from services.misc import get_current_user
from services.ai_querying import get_ai_response

from databases.conversations_database import get_db
from databases.file_storage_database import file_service, storage_backend

from models.conversations_model import Conversation
from models.messages_model import Message, MessageRole
from models.attachments_model import Attachment, AttachmentStatus, AttachmentActivityStatus, AttachmentType
from schemas.user_schemas import UserResponse
from schemas.conversation_schemas import (
    ConversationCreate,
    FullConversationResponse,
    ConversationStatus
)
from schemas.message_schemas import MessageCreate, MessageResponse, ChatResponse

from routes.route_helpers import get_or_create_user, verify_conversation_ownership

logger = logging.getLogger(__name__)
UTC = timezone.utc
router = APIRouter(prefix="/api", tags=["conversations"])



# ==================== User Route ===========================
@router.get("/user/profile", response_model=UserResponse)
@limiter.limit("100/minute")
async def get_user_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get user profile with statistics."""
    user = await get_or_create_user(db, current_user)
    
    # Get conversation statistics
    stats_query = select(
        func.count(Conversation.id).label('total'),
        func.count(Conversation.id).filter(
            Conversation.status == ConversationStatus.active.value
        ).label('active'),
        func.count(Conversation.id).filter(
            Conversation.status == ConversationStatus.archived.value
        ).label('archived')
    ).filter(
        Conversation.owner_id == user.id,
        Conversation.status != ConversationStatus.deleted.value
    )
    
    stats_result = await db.execute(stats_query)
    stats = stats_result.first()
    
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        given_name=user.given_name,
        surname=user.surname,
        job_title=user.job_title,
        department=user.department,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
        conversations_count=stats.total if stats else 0,
        active_conversations=stats.active if stats else 0,
        archived_conversations=stats.archived if stats else 0
    )

# ==================== Conversation Routes ====================

@router.post("/conversations", response_model=FullConversationResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("50/minute")
async def create_conversation(
    request: Request,
    conversation_data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new conversation."""
    user = await get_or_create_user(db, current_user)
    
    # Create conversation
    conversation = Conversation(
        conversation_title=conversation_data.conversation_title,
        model_choice=conversation_data.model_choice.value,
        model_instructions=conversation_data.model_instructions.value,
        owner_id=user.id
    )
    
    db.add(conversation)
    await db.flush()
    
    # Adds initial message if provided
    if conversation_data.initial_message:
        message = Message(
            conversation_id=conversation.id,
            role=conversation_data.initial_message.role.value,
            content=conversation_data.initial_message.content,
            parent_message_id=conversation_data.initial_message.parent_message_id
        )
        db.add(message)
    
    await db.commit()
    await db.refresh(conversation)
    
    logger.info(f"User {user.email} created conversation {conversation.id}")
    
    return FullConversationResponse.model_validate(conversation)

@router.get("/conversations", response_model=List[FullConversationResponse])
@limiter.limit("100/minute")
async def list_conversations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="Number of conversations to skip"),
    limit: int = Query(100, ge=1, le=100, description="Number of conversations to return"),
    include_archived: bool = Query(False, description="Include archived conversations")
):
    """List all conversations for the current user."""
    user = await get_or_create_user(db, current_user)
    
    # Build query
    query = select(Conversation).filter(
        Conversation.owner_id == user.id,
        Conversation.status != ConversationStatus.deleted.value
    )
    
    if not include_archived:
        query = query.filter(Conversation.status == ConversationStatus.active.value)
    
    # Order by last accessed or created date
    query = query.order_by(
        Conversation.accessed_at.desc().nullsfirst(),
        Conversation.created_at.desc()
    ).offset(skip).limit(limit)
    
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    return [FullConversationResponse.model_validate(conv) for conv in conversations]

@router.get("/conversations/{conversation_id}", response_model = FullConversationResponse)
@limiter.limit("100/minute")
async def get_conversation(
    conversation_id: int,
    request = Request, 
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),

):
    user = await get_or_create_user(db, current_user)
    conversation = await verify_conversation_ownership(db, conversation_id, user.id)    
    
    conversation.update_accessed_time()
    await db.commit()
    await db.refresh(conversation)


    return FullConversationResponse.model_validate(conversation)



## ==========================Message Routes =======================

# ==================== Message Creation with Selective Attachments ====================
"""
This route handles message creation with selective attachment context. I imagine the frontend to maintain
toggle states for all conversation attachments locally in the browser, and only sends the UUIDs of attachments 
that should be included in the AI context. The backend fetches only the specified attachments, retrieves their 
content or generates presigned URLs, and includes them in the AI prompt context.
"""
@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
@limiter.limit("100/minute")
async def create_message(
    conversation_id: int,
    request: Request,
    message_data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new message in a conversation with direct file upload to AI providers.
    Files are uploaded directly to OpenAI/Gemini without manual parsing.
    """
    user = await get_or_create_user(db, current_user)
    conversation = await verify_conversation_ownership(db, conversation_id, user.id)
    
    # Update conversation access time
    conversation.update_accessed_time()
    
    # Create user message
    user_message = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER.value,
        content=message_data.content,
        parent_message_id=message_data.parent_message_id
    )
    db.add(user_message)
    await db.flush()  # Get ID without committing
    
    try:
        # Fetch active attachments
        active_attachments = []
        if message_data.active_attachment_uuids:
            result = await db.execute(
                select(Attachment)
                .filter(
                    and_(
                        Attachment.uuid.in_(message_data.active_attachment_uuids),
                        Attachment.conversation_id == conversation_id,
                        Attachment.status == AttachmentStatus.UPLOADED.value
                    )
                )
            )
            active_attachments = result.scalars().all()
            
            # Log missing attachments
            found_uuids = {att.uuid for att in active_attachments}
            requested_uuids = set(message_data.active_attachment_uuids)
            if found_uuids != requested_uuids:
                missing = requested_uuids - found_uuids
                logger.warning(f"Missing attachments: {missing}")
        
        # Prepare attachments for AI (just fetch raw file content)
        attachment_contexts = []
        for attachment in active_attachments:
            try:
                # Simple approach of getting the file bytes
                file_buffer = await storage_backend.retrieve(attachment.storage_path)
                attachment_contexts.append({
                    "uuid": attachment.uuid,
                    "filename": attachment.filename,
                    "type": attachment.attachment_type.value,
                    "content_type": attachment.content_type,
                    "file_size": attachment.file_size,
                    "file_content": file_buffer.read()  # Raw bytes for AI upload
                })
                file_buffer.close()
                
            except Exception as e:
                logger.error(f"Failed to retrieve attachment {attachment.uuid}: {e}")
                # Continue with other attachments
        
        # Get recent messages for context
        result = await db.execute(
            select(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        recent_messages = result.scalars().all()
        recent_messages = list(reversed(recent_messages))
        
        # Generate AI response with direct file uploads
        from services.ai_querying import get_ai_response
        
        ai_response_content = await get_ai_response(
            conversation=conversation,
            messages=recent_messages,
            new_message=message_data.content,
            active_attachments=attachment_contexts,
            model_choice=conversation.model_choice,
            model_instructions=conversation.model_instructions
        )
        
        # Create assistant message
        assistant_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT.value,
            content=ai_response_content,
            parent_message_id=user_message.id
        )
        db.add(assistant_message)
        
        # Optionally update attachment activity status
        if hasattr(settings, 'persist_attachment_preferences') and settings.persist_attachment_preferences:
            if message_data.active_attachment_uuids:
                await db.execute(
                    update(Attachment)
                    .where(
                        and_(
                            Attachment.conversation_id == conversation_id,
                            Attachment.status == AttachmentStatus.UPLOADED.value
                        )
                    )
                    .values(
                        activity_status=case(
                            (Attachment.uuid.in_(message_data.active_attachment_uuids), 
                             AttachmentActivityStatus.ACTIVE.value),
                            else_=AttachmentActivityStatus.INACTIVE.value
                        )
                    )
                )
        
        await db.commit()
        await db.refresh(user_message)
        await db.refresh(assistant_message)
        
        return ChatResponse(
            user_message=MessageResponse.model_validate(user_message),
            assistant_reply=MessageResponse.model_validate(assistant_message),
            error=None
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to generate AI response: {e}")
        
        # Still save the user message even if AI fails
        await db.commit()
        await db.refresh(user_message)
        
        return ChatResponse(
            user_message=MessageResponse.model_validate(user_message),
            assistant_reply=None,
            error=f"Failed to generate AI response: {str(e)}"
        )