from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
import logging


from backend.models.users_model import User
from backend.models.conversations_model import Conversation

from backend.schemas.conversation_schemas import ConversationStatus


logger = logging.getLogger(__name__)
UTC = timezone.utc


async def get_or_create_user(db: AsyncSession, user_data: dict) -> User:
    """Get existing user or create new one from Microsoft AD data."""
    result = await db.execute(select(User).filter(User.id == user_data["id"]))
    user = result.scalar_one_or_none()
    
    if not user:
        email = user_data.get("mail") or user_data.get("userPrincipalName")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email not found in Azure AD data"
            )
        
        user = User(
            id=user_data["id"],
            email=email,
            display_name=user_data.get("displayName"),
            given_name=user_data.get("givenName"),
            surname=user_data.get("surname"),
            job_title=user_data.get("jobTitle"),
            department=user_data.get("department"),
            last_login=datetime.now(UTC)
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"Created new user record for AD user: {user.email}")

    else:
        user.last_login = datetime.now(UTC)
        await db.commit()
        await db.refresh(user)
    
    return user

async def verify_conversation_ownership(
    db: AsyncSession, 
    conversation_id: int, 
    user_id: str,
    load_relations: bool = True
) -> Conversation:
    """Get conversation and verify it belongs to the user."""
    query = select(Conversation)
    
    if load_relations:
        query = query.options(
            selectinload(Conversation.messages),
            selectinload(Conversation.attachments)
        )
    
    result = await db.execute(
        query.filter(and_(
            Conversation.id == conversation_id,
            Conversation.owner_id == user_id,
            Conversation.status != ConversationStatus.deleted.value
        ))
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return conversation
