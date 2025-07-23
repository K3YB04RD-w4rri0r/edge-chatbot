from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
from datetime import datetime

from schemas.item_schemas import Item, ItemCreate, ItemUpdate  
from db import items_db, current_id   

router = APIRouter()

"""
router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}}
)
"""

# CRUD endpoints for items
@router.get("/items", response_model=List[Item])
async def get_items(skip: int = 0, limit: int = 100):
    """Get all items with pagination"""
    items = list(items_db.values())
    return items[skip : skip + limit]

@router.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    """Get a specific item by ID"""
    if item_id not in items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    return items_db[item_id]

@router.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
async def create_item(item: ItemCreate):
    """Create a new item"""
    global current_id
    
    # Create new item
    new_item = Item(
        id=current_id,
        name=item.name,
        description=item.description,
        price=item.price,
        tax=item.tax,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # Store in database
    items_db[current_id] = new_item
    current_id += 1
    
    return new_item

@router.put("/items/{item_id}", response_model=Item)
async def update_item(item_id: int, item_update: ItemUpdate):
    """Update an existing item"""
    if item_id not in items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    
    # Get existing item
    existing_item = items_db[item_id]
    
    # Update only provided fields
    update_data = item_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing_item, field, value)
    
    # Update timestamp
    existing_item.updated_at = datetime.now()
    
    return existing_item

@router.delete("/items/{item_id}")
async def delete_item(item_id: int):
    """Delete an item"""
    if item_id not in items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    
    del items_db[item_id]
    return {"message": f"Item {item_id} deleted successfully"}

# Example of a more complex endpoint with query parameters
@router.get("/items/search/", response_model=List[Item])
async def search_items(
    q: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
):
    """Search items with filters"""
    results = []
    
    for item in items_db.values():
        # Apply filters
        if q and q.lower() not in item.name.lower() and (not item.description or q.lower() not in item.description.lower()):
            continue
        if min_price and item.price < min_price:
            continue
        if max_price and item.price > max_price:
            continue
        
        results.append(item)
    
    return results