from pydantic import BaseModel, EmailStr, StringConstraints
from typing import Optional, Annotated

class UserBase(BaseModel):
    username: Annotated[str, StringConstraints(min_length=3, max_length=50)]
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: Annotated[str, StringConstraints(min_length=8, max_length=100)]

class UserInDB(UserBase):
    id: int
    is_active: bool = True
    is_superuser: bool = False
    
    class Config:
        from_attributes = True

class UserResponse(UserBase):
    id: int
    is_active: bool
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefresh(BaseModel):
    refresh_token: str

class LoginRequest(BaseModel):
    username: str
    password: str