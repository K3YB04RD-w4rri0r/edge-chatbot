from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# User Schemas
class UserBase(BaseModel):
    email: str
    display_name: Optional[str] = None
    given_name: Optional[str] = None
    surname: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None

class UserCreate(UserBase):
    id: str  # Microsoft AD ID

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    given_name: Optional[str] = None
    surname: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None

class UserInDB(UserBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)

class UserResponse(UserInDB):
    items_count: Optional[int] = 0

# Item Schemas
class ItemBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    tags: Optional[str] = None

class ItemCreate(ItemBase):
    pass

class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|archived|deleted)$")
    tags: Optional[str] = None

class ItemInDB(ItemBase):
    id: int
    owner_id: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class ItemResponse(ItemInDB):
    owner: Optional[UserBase] = None

# List Response Schemas
class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(100, ge=1, le=1000)

class ItemListResponse(BaseModel):
    items: List[ItemResponse]
    total: int
    skip: int
    limit: int

# Category Schemas (example of additional model)
class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)