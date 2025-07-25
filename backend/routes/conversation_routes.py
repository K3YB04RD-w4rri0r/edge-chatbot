from fastapi import APIRouter, Request, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional
from datetime import datetime, timezone

from backend.databases.conversations_database import get_db
from backend.models.conversations_model import Item, User
from backend.schemas.conversation_schemas import (
    ItemCreate, ItemUpdate, ItemResponse, ItemListResponse,
    UserResponse, PaginationParams
)
from backend.utils.misc import get_current_user
from shared_variables import limiter

import logging

logger = logging.getLogger(__name__)
UTC = timezone.utc

router = APIRouter(prefix="/api", tags=["items"])

# Helper function to ensure user exists in database
async def ensure_user_exists(db: Session, user_data: dict) -> User:
    """
    Ensure user from Microsoft AD exists in our database
    """
    user = db.query(User).filter(User.id == user_data["id"]).first()
    
    if not user:
        # Create user from Microsoft AD data
        user = User(
            id=user_data["id"],
            email=user_data.get("mail") or user_data.get("userPrincipalName"),
            display_name=user_data.get("displayName"),
            given_name=user_data.get("givenName"),
            surname=user_data.get("surname"),
            job_title=user_data.get("jobTitle"),
            department=user_data.get("department"),
            last_login=datetime.now(UTC)
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {user.email}")
    else:
        # Update last login
        user.last_login = datetime.now(UTC)
        db.commit()
    
    return user

# Get all items for authenticated user
@router.get("/items", response_model=ItemListResponse)
@limiter.limit("100/minute")
async def get_items(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, pattern="^(active|archived|deleted)$"),
    search: Optional[str] = Query(None, description="Search in title and description")
):
    """
    Get all items for the authenticated user with pagination and filtering
    """
    # Ensure user exists
    user = await ensure_user_exists(db, current_user)
    
    # Base query
    query = db.query(Item).filter(Item.owner_id == user.id)
    
    # Apply filters
    if status:
        query = query.filter(Item.status == status)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Item.title.ilike(search_term),
                Item.description.ilike(search_term)
            )
        )
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    items = query.order_by(Item.created_at.desc()).offset(skip).limit(limit).all()
    
    return ItemListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )

# Get single item
@router.get("/items/{item_id}", response_model=ItemResponse)
@limiter.limit("100/minute")
async def get_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific item by ID (only if owned by user)
    """
    user = await ensure_user_exists(db, current_user)
    
    item = db.query(Item).filter(
        and_(Item.id == item_id, Item.owner_id == user.id)
    ).first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    return item

# Create item
@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("50/minute")
async def create_item(
    request: Request,
    item_data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new item for the authenticated user
    """
    user = await ensure_user_exists(db, current_user)
    
    # Create new item
    item = Item(
        **item_data.model_dump(),
        owner_id=user.id
    )
    
    db.add(item)
    db.commit()
    db.refresh(item)
    
    logger.info(f"User {user.email} created item {item.id}")
    
    return item

# Update item
@router.put("/items/{item_id}", response_model=ItemResponse)
@limiter.limit("50/minute")
async def update_item(
    request: Request,
    item_id: int,
    item_update: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an item (only if owned by user)
    """
    user = await ensure_user_exists(db, current_user)
    
    # Get item
    item = db.query(Item).filter(
        and_(Item.id == item_id, Item.owner_id == user.id)
    ).first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    # Update fields
    update_data = item_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    
    logger.info(f"User {user.email} updated item {item.id}")
    
    return item

# Delete item
@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("50/minute")
async def delete_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    soft_delete: bool = Query(True, description="Soft delete (mark as deleted) vs hard delete")
):
    """
    Delete an item (only if owned by user)
    """
    user = await ensure_user_exists(db, current_user)
    
    # Get item
    item = db.query(Item).filter(
        and_(Item.id == item_id, Item.owner_id == user.id)
    ).first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    if soft_delete:
        # Soft delete - just mark as deleted
        item.status = "deleted"
        db.commit()
        logger.info(f"User {user.email} soft deleted item {item.id}")
    else:
        # Hard delete - remove from database
        db.delete(item)
        db.commit()
        logger.info(f"User {user.email} hard deleted item {item.id}")
    
    return None

# Get user profile with stats
@router.get("/user/profile", response_model=UserResponse)
@limiter.limit("100/minute")
async def get_user_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get user profile with statistics
    """
    user = await ensure_user_exists(db, current_user)
    
    # Get item count
    items_count = db.query(func.count(Item.id)).filter(
        Item.owner_id == user.id,
        Item.status != "deleted"
    ).scalar()
    
    # Convert to response model with stats
    user_dict = user.__dict__.copy()
    user_dict["items_count"] = items_count
    
    return UserResponse(**user_dict)

# Bulk operations example
@router.post("/items/bulk-archive", response_model=dict)
@limiter.limit("10/minute")
async def bulk_archive_items(
    request: Request,
    item_ids: List[int],
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Archive multiple items at once
    """
    user = await ensure_user_exists(db, current_user)
    
    # Update items owned by user
    updated_count = db.query(Item).filter(
        and_(
            Item.id.in_(item_ids),
            Item.owner_id == user.id,
            Item.status == "active"
        )
    ).update(
        {"status": "archived", "updated_at": datetime.now(UTC)},
        synchronize_session=False
    )
    
    db.commit()
    
    logger.info(f"User {user.email} archived {updated_count} items")
    
    return {
        "message": f"Successfully archived {updated_count} items",
        "archived_count": updated_count
    }