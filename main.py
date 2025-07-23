from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime
import uvicorn


from backend.database import engine, Base

from config import settings, validate_config

# routes 
from backend.routes.item_routes import router as items_router
from backend.routes.auth_routes import router as auth_router

# Validate configuration on startup
validate_config()

# Create tables before creating the app
print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("Database tables created!")

# Create FastAPI instance
app = FastAPI(
    title=settings.app_name,
    description="Internal tool Edge",
    version=settings.app_version,
    openapi_url=settings.openapi_url,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    debug=settings.debug
)

# router setup
app.include_router(items_router)
app.include_router(auth_router)

# Configure CORS with settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)



# Example of custom exception handler
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return {"error": str(exc)}, 400



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        workers=settings.workers if not settings.reload else 1,
        log_level=settings.log_level.lower()
    )