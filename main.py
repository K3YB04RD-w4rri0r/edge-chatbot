from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn

from backend.database import init_db, cleanup_expired_sessions
from config import settings, validate_config

# routes 
from backend.routes.item_routes import router as items_router
from backend.routes.auth_routes import router as auth_router
from backend.routes.other_routes import router as other_router


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    # Startup
    print("🚀 Starting Internal Edge Tool...")
    
    # Validate configuration
    try:
        validate_config()
        print("✓ Configuration validated")
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        raise
    
    # Initialize database
    init_db()
    
    # Clean up expired sessions on startup
    cleanup_expired_sessions()
    
    print(f"✓ Application started successfully!")
    print(f"  Environment: {settings.environment}")
    print(f"  Database: {settings.database_url}")
    print(f"  Microsoft Auth: Configured")
    print(f"  API Docs: http://localhost:{settings.port}{settings.docs_url or '/docs'}")
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")
    # Add any cleanup code here


# Create the FastAPI instance
app = FastAPI(
    title=settings.app_name,
    description="Internal tool Edge - Microsoft Authentication",
    version=settings.app_version,
    openapi_url=settings.openapi_url,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    debug=settings.debug,
    lifespan=lifespan
)

# Configure CORS with settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Include routers
app.include_router(auth_router)  # Auth routes first
app.include_router(items_router)
app.include_router(other_router)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with application info"""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "authentication": "Microsoft OAuth 2.0",
        "docs": settings.docs_url,
        "health": "ok"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    # You could add database connectivity checks here
    return {
        "status": "healthy",
        "environment": settings.environment,
        "authentication": "microsoft"
    }

# Global exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions"""
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    """Handle internal server errors"""
    # Log the error in production
    if settings.is_production:
        # Log to your logging service
        pass
    else:
        print(f"Internal error: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred" if settings.is_production else str(exc)
        }
    )

# Add request ID middleware for tracking
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID for tracking"""
    import uuid
    request_id = str(uuid.uuid4())
    
    # You could log: [request_id] {method} {url}
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        workers=settings.workers if not settings.reload else 1,
        log_level=settings.log_level.lower()
    )
