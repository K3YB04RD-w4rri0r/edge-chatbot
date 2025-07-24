from fastapi import FastAPI, Request, HTTPException, Depends, status, Response
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any
import msal
import httpx
from jose import JWTError, jwt
import uuid
from contextlib import asynccontextmanager
import asyncio
import logging
import redis
import json
from config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize settings
settings = get_settings()

# Redis client (optional for development)
redis_client = None
if settings.redis_url:
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
elif not settings.is_development:
    # Redis configuration for production
    redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True
    )


# Fallback to in-memory storage for development
auth_states: Dict[str, dict] = {}
refresh_tokens: Dict[str, dict] = {}

# Background task for cleanup
async def cleanup_auth_states():
    """Clean up expired auth states every hour"""
    while True:
        try:
            if redis_client:
                # Redis handles expiration automatically
                await asyncio.sleep(3600)
            else:
                # In-memory cleanup
                current_time = datetime.now(UTC)
                expired_states = [
                    state for state, data in auth_states.items()
                    if current_time - data["timestamp"] > timedelta(minutes=10)
                ]
                for state in expired_states:
                    auth_states.pop(state, None)
                
                # Cleanup expired refresh tokens
                expired_tokens = [
                    token for token, data in refresh_tokens.items()
                    if current_time - data["timestamp"] > timedelta(days=settings.refresh_token_expire_days)
                ]
                for token in expired_tokens:
                    refresh_tokens.pop(token, None)
                    
                await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    cleanup_task = asyncio.create_task(cleanup_auth_states())
    yield
    # Shutdown
    logger.info("Shutting down...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Microsoft Login API", lifespan=lifespan)

# CORS - Special handling for development
if settings.is_development:
    # Use a custom CORS middleware for development that handles file:// protocol
    class DevCORSMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
            return response
    
    app.add_middleware(DevCORSMiddleware)
else:
    # Use strict CORS settings in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

# MSAL configuration
msal_config = {
    "client_id": settings.azure_client_id,
    "client_secret": settings.azure_client_secret,
    "authority": f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
}

# Create MSAL application instance
msal_app = msal.ConfidentialClientApplication(
    msal_config["client_id"],
    authority=msal_config["authority"],
    client_credential=msal_config["client_secret"],
)

# State management functions
def store_state(state: str, data: dict):
    """Store state with Redis or in-memory fallback"""
    if redis_client:
        redis_client.setex(f"auth_state:{state}", 600, json.dumps(data))
    else:
        auth_states[state] = {**data, "timestamp": datetime.now(UTC)}

def get_state(state: str) -> Optional[dict]:
    """Retrieve state from Redis or in-memory"""
    if redis_client:
        data = redis_client.get(f"auth_state:{state}")
        return json.loads(data) if data else None
    else:
        return auth_states.get(state)

def delete_state(state: str):
    """Delete state from Redis or in-memory"""
    if redis_client:
        redis_client.delete(f"auth_state:{state}")
    else:
        auth_states.pop(state, None)

def store_refresh_token(user_id: str, refresh_token: str):
    """Store refresh token securely"""
    if redis_client:
        redis_client.setex(
            f"refresh_token:{user_id}", 
            settings.refresh_token_expire_days * 86400, 
            refresh_token
        )
    else:
        refresh_tokens[user_id] = {
            "token": refresh_token,
            "timestamp": datetime.now(UTC)
        }

def get_refresh_token(user_id: str) -> Optional[str]:
    """Retrieve refresh token"""
    if redis_client:
        return redis_client.get(f"refresh_token:{user_id}")
    else:
        data = refresh_tokens.get(user_id)
        return data["token"] if data else None

# JWT token creation and validation
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def create_refresh_token() -> str:
    """Create a refresh token"""
    return str(uuid.uuid4())

async def get_current_user(request: Request) -> dict:
    """Validate JWT token and return user data"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        
        # Validate token expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, UTC) < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_data = payload.get("user_data")
        if user_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_data
        
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Routes
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    health_status = {"status": "OK", "timestamp": datetime.now(UTC).isoformat()}
    
    # Check Redis connection if configured
    if redis_client:
        try:
            redis_client.ping()
            health_status["redis"] = "connected"
        except Exception as e:
            health_status["redis"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
    
    return health_status

@app.get("/auth/microsoft")
async def login():
    """Initiate Microsoft OAuth login"""
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    
    # Store state
    store_state(state, {"timestamp": datetime.now(UTC).isoformat()})
    
    # Get authorization URL
    auth_url = msal_app.get_authorization_request_url(
        scopes=["User.Read", "email"],
        state=state,
        redirect_uri=settings.redirect_uri,
        prompt="select_account",  # Always show account selection
    )
    
    logger.info(f"Initiating login with state: {state}")
    return RedirectResponse(url=auth_url)

@app.get("/auth/microsoft/callback")
async def callback(code: str, state: str, error: Optional[str] = None, error_description: Optional[str] = None):
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
            redirect_uri=settings.redirect_uri,
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
        
        # Store refresh token if available
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
                // JavaScript redirect as backup
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
            <script>
                console.log("Redirecting to:", "{settings.frontend_url}");
            </script>
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
        
        # Set refresh token cookie if in production
        if settings.is_production and "refresh_token" in result:
            refresh_token_id = create_refresh_token()
            response.set_cookie(
                key="refresh_token_id",
                value=refresh_token_id,
                httponly=True,
                secure=settings.secure_cookies,
                samesite=settings.cookie_samesite,
                domain=settings.cookie_domain,
                max_age=settings.refresh_token_expire_days * 86400
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(e) if settings.is_development else "An error occurred"}
        )

@app.post("/auth/refresh")
async def refresh_token(request: Request):
    """Refresh access token using refresh token"""
    try:
        # Get current user ID from expired token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="No access token")
        
        # Decode without verification to get user ID
        unverified_payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm], options={"verify_signature": False})
        user_id = unverified_payload.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get stored refresh token
        refresh_token = get_refresh_token(user_id)
        if not refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token available")
        
        # Use refresh token to get new access token
        result = msal_app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=["User.Read", "email"]
        )
        
        if "access_token" not in result:
            raise HTTPException(status_code=401, detail="Failed to refresh token")
        
        # Get updated user profile
        async with httpx.AsyncClient() as client:
            graph_response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {result['access_token']}"},
            )
            user_profile = graph_response.json()
        
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
        
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(status_code=401, detail="Failed to refresh token")

@app.get("/api/user")
async def get_user(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user"""
    return {"user": current_user}

@app.get("/api/protected")
async def protected_route(current_user: dict = Depends(get_current_user)):
    """Example protected route"""
    return {
        "message": "This is a protected resource",
        "user": current_user,
        "timestamp": datetime.now(UTC).isoformat()
    }

@app.get("/api/debug/refresh-token-status")
async def debug_refresh_token_status(current_user: dict = Depends(get_current_user)):
    """Debug endpoint to check refresh token status"""
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")
    
    user_id = current_user.get("id")
    has_refresh_token = bool(get_refresh_token(user_id))
    
    return {
        "user_id": user_id,
        "has_refresh_token": has_refresh_token,
        "message": "Refresh token available" if has_refresh_token else "No refresh token stored"
    }

@app.post("/auth/logout")
async def logout(response: Response, current_user: dict = Depends(get_current_user)):
    """Logout user"""
    # Clear refresh token if exists
    user_id = current_user.get("id")
    if user_id and redis_client:
        redis_client.delete(f"refresh_token:{user_id}")
    elif user_id:
        refresh_tokens.pop(user_id, None)
    
    # Create response
    logout_response = JSONResponse(content={
        "message": "Logged out successfully",
        "logout_url": f"https://login.microsoftonline.com/{settings.azure_tenant_id}/oauth2/v2.0/logout?post_logout_redirect_uri={settings.frontend_url}"
    })
    
    # Clear cookies
    logout_response.delete_cookie(key="access_token", domain=settings.cookie_domain)
    logout_response.delete_cookie(key="refresh_token_id", domain=settings.cookie_domain)
    
    return logout_response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.log_level.lower()
    )