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


