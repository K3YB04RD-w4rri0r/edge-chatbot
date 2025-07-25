from fastapi import APIRouter, Request, HTTPException, Depends, Response
from typing import Optional
from jose import jwt
import httpx
from datetime import datetime, timedelta, timezone
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import uuid
from slowapi.util import get_remote_address


from shared_variables import (redis_client,limiter,msal_app)
from backend.utils.auth import create_access_token, get_refresh_token, store_refresh_token, delete_refresh_token, get_state, delete_state, revoke_access_token, store_state
from backend.utils.misc import get_current_user

from config import get_settings
import logging
from datetime import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()
UTC = timezone.utc


router = APIRouter()



@router.get("/auth/microsoft")
@limiter.limit("10/minute")
async def login(request: Request):
    """Initiate Microsoft OAuth login"""
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    
    # Store state with additional metadata
    store_state(state, {
        "timestamp": datetime.now(UTC).isoformat(),
        "ip": get_remote_address(request),
        "user_agent": request.headers.get("user-agent", "unknown")
    })
    
    # Get authorization URL
    auth_url = msal_app.get_authorization_request_url(
        scopes=["User.Read", "email"],
        state=state,
        redirect_uri=settings.redirect_uri,
        prompt="select_account"  # Always show account selection
    )
    
    logger.info(f"Initiating login with state: {state}")
    return RedirectResponse(url=auth_url)

@router.get("/auth/microsoft/callback")
@limiter.limit("20/minute")
async def callback(request: Request, code: str, state: str, error: Optional[str] = None, error_description: Optional[str] = None):
    """Handle Microsoft OAuth callback"""
    # Handle OAuth errors
    if error:
        logger.error(f"OAuth error: {error} - {error_description}")
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login Failed</title>
            <meta http-equiv="refresh" content="5;url={settings.frontend_url}">
        </head>
        <body style="font-family: Arial, sans-serif; padding: 40px; text-align: center;">
            <h1>Login Failed</h1>
            <p>Error: {error}</p>
            <p>{error_description or ''}</p>
            <p>Redirecting to home page in 5 seconds...</p>
            <p>If not redirected, <a href="{settings.frontend_url}">click here</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)
    
    logger.info(f"Callback received - State: {state}")
    
    # Verify state
    state_data = get_state(state)
    if not state_data:
        logger.warning(f"Invalid state: {state}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid state parameter"}
        )
    
    # Clean up state
    delete_state(state)
    
    try:
        # Exchange code for token
        logger.info("Exchanging code for token...")
        result = msal_app.acquire_token_by_authorization_code(
            code,
            scopes=["User.Read", "email"],
            redirect_uri=settings.redirect_uri
        )
        
        if "access_token" not in result:
            error = result.get("error", "unknown_error")
            error_description = result.get("error_description", "Unknown error")
            logger.error(f"Token acquisition failed: {error} - {error_description}")
            
            # Handle specific errors
            if error == "invalid_grant":
                error_message = "The authorization code has expired or already been used."
            elif error == "consent_required":
                error_message = "User consent is required. Please try logging in again."
            else:
                error_message = error_description
            
            return JSONResponse(
                status_code=400,
                content={"error": error, "error_description": error_message}
            )
        
        logger.info("Token acquired successfully")
        
        # Get user profile from Microsoft Graph
        async with httpx.AsyncClient() as client:
            graph_response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {result['access_token']}"},
            )
            
            if graph_response.status_code != 200:
                logger.error(f"Failed to get user profile: {graph_response.text}")
                raise HTTPException(status_code=500, detail="Failed to get user profile")
            
            user_profile = graph_response.json()
            logger.info(f"User profile retrieved: {user_profile.get('displayName', 'Unknown')}")
        
        # Store refresh token
        if "refresh_token" in result:
            logger.info(f"Storing refresh token for user {user_profile['id']}")
            store_refresh_token(user_profile["id"], result["refresh_token"])
        else:
            logger.warning("No refresh token received from Microsoft")
        
        # Create JWT token with user data
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={
                "user_data": user_profile,
                "sub": user_profile["id"],  # Subject claim
                "email": user_profile.get("mail") or user_profile.get("userPrincipalName"),
            },
            expires_delta=access_token_expires
        )
        
        # Create success response
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login Successful</title>
            <script>
                setTimeout(function() {{
                    window.location.href = "{settings.frontend_url}";
                }}, 2000);
            </script>
            <meta http-equiv="refresh" content="2;url={settings.frontend_url}">
        </head>
        <body style="font-family: Arial, sans-serif; padding: 40px; text-align: center;">
            <h1>Login Successful!</h1>
            <p>Welcome, {user_profile.get('displayName', user_profile.get('userPrincipalName', 'User'))}!</p>
            <p>Redirecting in 2 seconds...</p>
            <p>If not redirected, <a href="{settings.frontend_url}">click here</a></p>
        </body>
        </html>
        """
        
        response = HTMLResponse(content=success_html)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite=settings.cookie_samesite,
            domain=settings.cookie_domain,
            max_age=settings.access_token_expire_minutes * 60
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(e) if settings.is_development else "An error occurred"}
        )

@router.post("/auth/refresh")
@limiter.limit("5/minute")
async def refresh_token(request: Request):
    """Refresh access token using refresh token"""
    try:
        # Get current user ID from expired token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="No access token")
        
        # Decode without verification to get user ID
        unverified_payload = jwt.decode(
            token, 
            settings.secret_key, 
            algorithms=[settings.algorithm], 
            options={"verify_signature": False, "verify_exp": False}
        )
        user_id = unverified_payload.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get stored refresh token
        stored_refresh_token = get_refresh_token(user_id)
        if not stored_refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token available")
        
        # Use refresh token to get new access token
        result = msal_app.acquire_token_by_refresh_token(
            stored_refresh_token,
            scopes=["User.Read", "email"]
        )
        
        if "access_token" not in result:
            # If refresh fails, delete the invalid refresh token
            delete_refresh_token(user_id)
            raise HTTPException(status_code=401, detail="Failed to refresh token")
        
        # Get updated user profile
        async with httpx.AsyncClient() as client:
            graph_response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {result['access_token']}"},
            )
            user_profile = graph_response.json()
        
        # Update refresh token if a new one was provided
        if "refresh_token" in result:
            store_refresh_token(user_id, result["refresh_token"])
        
        # Create new JWT
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        new_access_token = create_access_token(
            data={
                "user_data": user_profile,
                "sub": user_profile["id"],
                "email": user_profile.get("mail") or user_profile.get("userPrincipalName"),
            },
            expires_delta=access_token_expires
        )
        
        response = JSONResponse(content={"message": "Token refreshed successfully"})
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite=settings.cookie_samesite,
            domain=settings.cookie_domain,
            max_age=settings.access_token_expire_minutes * 60
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(status_code=401, detail="Failed to refresh token")

@router.get("/api/user")
@limiter.limit("100/minute")
async def get_user(request: Request, current_user: dict = Depends(get_current_user)):
    """Get current authenticated user"""
    return {"user": current_user}

@router.get("/api/protected")
@limiter.limit("100/minute")
async def protected_route(request: Request, current_user: dict = Depends(get_current_user)):
    """Example protected route"""
    return {
        "message": "This is a protected resource",
        "user": current_user,
        "timestamp": datetime.now(UTC).isoformat()
    }

@router.get("/api/debug/refresh-token-status")
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

@router.post("/auth/logout")
@limiter.limit("20/minute")
async def logout(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
    """Logout user"""
    # Get JWT ID for revocation
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
                options={"verify_signature": False, "verify_exp": False}
            )
            jti = payload.get("jti")
            if jti:
                revoke_access_token(jti)
        except Exception as e:
            logger.error(f"Error revoking token: {e}")
    
    # Clear refresh token
    user_id = current_user.get("id")
    if user_id:
        delete_refresh_token(user_id)
    
    # Create response
    logout_response = JSONResponse(content={
        "message": "Logged out successfully",
        "logout_url": f"https://login.microsoftonline.com/{settings.azure_tenant_id}/oauth2/v2.0/logout?post_logout_redirect_uri={settings.frontend_url}"
    })
    
    # Clear cookies
    logout_response.delete_cookie(key="access_token", domain=settings.cookie_domain)
    
    return logout_response

@router.get("/api/rate-limit-status")
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

@router.get("/api/debug/redis-stats")
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

@router.get("/api/debug/azure-redis-info")
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
