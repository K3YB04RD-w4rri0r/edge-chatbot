from fastapi import APIRouter
from datetime import datetime
from config import settings


router = APIRouter()

# Root endpoint
@router.get("/")
async def root():
    """Welcome endpoint"""
    return {"message": "Welcome Edge's Internal Tool !", "docs": "/docs"}

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "environment": settings.environment,
        "version": settings.app_version
    }
