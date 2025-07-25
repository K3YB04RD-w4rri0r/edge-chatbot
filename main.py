from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import asyncio
import redis
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from shared_variables import redis_client,limiter
from backend.databases.conversations_database import test_db_connection
from config import get_settings

from backend.routes.auth_routes import router as auth_router 
from backend.routes.item_routes import router as items_router


import logging
from datetime import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
UTC = timezone.utc






#################################################
#####           Monitoring
#################################################

# Background task for monitoring Redis connection
async def monitor_redis_health():
    """Monitor Redis connection health"""
    while True:
        try:
            redis_client.ping()
            await asyncio.sleep(30)  # Check every 30 seconds
        except redis.ConnectionError:
            logger.error("Lost connection to Redis!")
            # In production, you might want to trigger alerts here
            await asyncio.sleep(5)  # Retry more frequently when disconnected
        except Exception as e:
            logger.error(f"Redis health check error: {e}")
            await asyncio.sleep(30)

# Background task for monitoring Database connection
async def monitor_database_health():
    """Monitor database connection health"""
    while True:
        try:
            
            if not test_db_connection():
                logger.error("Database connection check failed!")
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Database health check error: {e}")
            await asyncio.sleep(60)



# Lifespan event to monitor the health of all our different services
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    
    # Test database connection on startup
    logger.info("Testing database connection...")
    if test_db_connection():
        logger.info("Database connection successful")
    else:
        logger.warning("Database connection failed - some features may be unavailable")
    
    # Start monitoring tasks
    redis_monitor_task = asyncio.create_task(monitor_redis_health())
    db_monitor_task = asyncio.create_task(monitor_database_health())
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    redis_monitor_task.cancel()
    db_monitor_task.cancel()
    try:
        await redis_monitor_task
        await db_monitor_task
    except asyncio.CancelledError:
        pass





#################################################
#####       FastAPI app Initialization
#################################################

app = FastAPI(title="Microsoft Login API", lifespan=lifespan)
# Plus the Routes
app.include_router(auth_router)
app.include_router(items_router)

# Attach limiter to app state (required for the decorators to work)
app.state.limiter = limiter
# Rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


#########################################################
####    Health Route (placed here for best practices)
#########################################################
@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Enhanced health check endpoint for Azure Cache for Redis"""
    health_status = {
        "status": "OK",
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": settings.environment,
    }
    # Check Redis connection
    try:
        # Basic ping with timeout
        redis_client.ping()
        
        # Get Redis info
        info = redis_client.info()
        server_info = redis_client.info("server")
        
        # Azure Cache specific info
        health_status["redis"] = {
            "connected": True,
            "host": settings.redis_host or "from_url",
            "ssl": settings.redis_ssl or ("rediss://" in (settings.redis_url or "")),
            "version": info.get("redis_version", "unknown"),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "maxmemory_human": info.get("maxmemory_human", "unlimited"),
            "evicted_keys": info.get("evicted_keys", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
        }
        

        
        # Calculate hit rate
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        if hits + misses > 0:
            health_status["redis"]["hit_rate_percent"] = round((hits / (hits + misses)) * 100, 2)
        
        # Check if Azure Cache
        if "redis.cache.windows.net" in (settings.redis_host or settings.redis_url or ""):
            health_status["redis"]["provider"] = "Azure Cache for Redis"
            health_status["redis"]["azure_sku"] = server_info.get("redis_mode", "Basic")      
    except redis.ConnectionError as e:
        health_status["status"] = "unhealthy"
        health_status["redis"] = {
            "connected": False,
            "error": str(e),
            "error_type": "connection_error"
        }
        return JSONResponse(status_code=503, content=health_status)
    except redis.TimeoutError as e:
        health_status["status"] = "degraded"
        health_status["redis"] = {
            "connected": True,
            "error": "Redis responding slowly",
            "error_type": "timeout"
        }
        return JSONResponse(status_code=200, content=health_status)
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["redis"] = {
            "connected": False,
            "error": str(e),
            "error_type": "unknown"
        }
        return JSONResponse(status_code=503, content=health_status)
    
    # Check Database
    try:
        db_connected = test_db_connection()
        health_status["database"] = {
            "connected": db_connected,
            "type": settings.db_type,
            "host": settings.db_host,
            "database": settings.db_name,
        }
        
        if not db_connected:
            health_status["status"] = "degraded"
            health_status["database"]["error"] = "Connection test failed"      
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["database"] = {
            "connected": False,
            "error": str(e),
            "error_type": "unknown"
        }
    


    # Appropriate status code
    if health_status["status"] == "unhealthy":
        return JSONResponse(status_code=503, content=health_status)
    elif health_status["status"] == "degraded":
        return JSONResponse(status_code=200, content=health_status)

    return health_status




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.log_level.lower()
    )