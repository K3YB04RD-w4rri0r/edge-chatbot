from fastapi import APIRouter, Request, HTTPException, Depends, Response
from typing import Optional
from jose import jwt
import httpx
from datetime import datetime, timedelta, timezone
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import uuid
from slowapi.util import get_remote_address


from shared_variables import (redis_client,limiter,msal_app)
from backend.services.auth import create_access_token, get_refresh_token, store_refresh_token, delete_refresh_token, get_state, delete_state, revoke_access_token, store_state
from backend.services.misc import get_current_user

from config import get_settings
import logging
from datetime import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
UTC = timezone.utc


router = APIRouter(prefix = "/api/debug")

@router.get("/refresh-token-status")
@limiter.limit("10/minute")
async def debug_refresh_token_status(request: Request, current_user: dict = Depends(get_current_user)):
    """Debug endpoint to check refresh token status"""
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")
    
    user_id = current_user.get("id")
    has_refresh_token = bool(get_refresh_token(user_id))
    
    # Get TTL for the refresh token
    ttl = None
    if has_refresh_token:
        key = f"refresh_token:{user_id}"
        ttl = redis_client.ttl(key)
    
    return {
        "user_id": user_id,
        "has_refresh_token": has_refresh_token,
        "ttl_seconds": ttl,
        "message": "Refresh token available" if has_refresh_token else "No refresh token stored"
    }


@router.get("/rate-limit-status")
@limiter.limit("10/minute")
async def rate_limit_status(request: Request):
    """Check current rate limit status"""
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")
    
    return {
        "message": "Check response headers for rate limit info",
        "headers": {
            "X-RateLimit-Limit": "Requests allowed in window",
            "X-RateLimit-Remaining": "Requests remaining",
            "X-RateLimit-Reset": "Unix timestamp when limit resets"
        }
    }

@router.get("/redis-stats")
@limiter.limit("10/minute")
async def redis_stats(request: Request, current_user: dict = Depends(get_current_user)):
    """Get Redis statistics (development only)"""
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")
    
    try:
        info = redis_client.info()
        memory_info = redis_client.info("memory")
        
        return {
            "server": {
                "redis_version": info.get("redis_version"),
                "uptime_seconds": info.get("uptime_in_seconds"),
                "connected_clients": info.get("connected_clients"),
            },
            "memory": {
                "used_memory_human": memory_info.get("used_memory_human"),
                "used_memory_peak_human": memory_info.get("used_memory_peak_human"),
                "total_system_memory_human": memory_info.get("total_system_memory_human"),
            },
            "stats": {
                "total_connections_received": info.get("total_connections_received"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")

@router.get("/azure-redis-info")
@limiter.limit("10/minute")
async def azure_redis_info(request: Request, current_user: dict = Depends(get_current_user)):
    """Get Azure Cache for Redis specific information"""
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")
    
    try:
        info = redis_client.info()
        replication = redis_client.info("replication")
        clients = redis_client.info("clients")
        memory = redis_client.info("memory")
        stats = redis_client.info("stats")
        
        return {
            "azure_cache_info": {
                "server": {
                    "redis_version": info.get("redis_version"),
                    "redis_mode": info.get("redis_mode", "standalone"),
                    "tcp_port": info.get("tcp_port"),
                    "uptime_in_days": info.get("uptime_in_days"),
                },
                "replication": {
                    "role": replication.get("role"),
                    "connected_slaves": replication.get("connected_slaves", 0),
                },
                "clients": {
                    "connected_clients": clients.get("connected_clients"),
                    "blocked_clients": clients.get("blocked_clients"),
                    "max_clients": clients.get("maxclients", "unlimited"),
                },
                "memory": {
                    "used_memory_human": memory.get("used_memory_human"),
                    "used_memory_peak_human": memory.get("used_memory_peak_human"),
                    "maxmemory_human": memory.get("maxmemory_human", "unlimited"),
                    "mem_fragmentation_ratio": memory.get("mem_fragmentation_ratio"),
                    "evicted_keys": stats.get("evicted_keys", 0),
                },
                "performance": {
                    "instantaneous_ops_per_sec": stats.get("instantaneous_ops_per_sec"),
                    "total_commands_processed": stats.get("total_commands_processed"),
                    "total_connections_received": stats.get("total_connections_received"),
                    "rejected_connections": stats.get("rejected_connections", 0),
                    "expired_keys": stats.get("expired_keys", 0),
                },
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")
    
@router.get("/enums")
async def get_available_enums():
    """Debug route to see available enum values"""
    from backend.models.conversations_model import ModelChoice, ModelInstructions
    from backend.models.attachments_model import AttachmentStatus,AttachmentType,AttachmentActivityStatus
    from backend.models.messages_model import MessageRole
    return {
        "model_choices": [choice.value for choice in ModelChoice],
        "model_instructions": [instruction.value for instruction in ModelInstructions],
        "attachment_statuses": [status.value for status in AttachmentStatus],
        "attachment_activity_statuses": [activity_status.value for activity_status in AttachmentActivityStatus],
        "attachment_types": [attachment_type.value for attachment_type in AttachmentType],
        "message_roles": [roles.value for roles in MessageRole],
    }