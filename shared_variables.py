from fastapi import Request
import redis
import ssl
import logging
from urllib.parse import urlparse
from datetime import timezone
from slowapi import Limiter
import msal
from slowapi.util import get_remote_address
from jose import jwt
from config import get_settings
import logging
from datetime import timezone
import time
import sys


def create_azure_redis_client(settings):
    """
    Create a Redis client optimized for Azure Cache for Redis
    """
    # If using Redis URL
    if settings.redis_url:
        parsed_url = urlparse(settings.redis_url)
        
        # Azure Cache for Redis specific settings
        connection_kwargs = {
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True,
            'retry_on_error': [redis.ConnectionError, redis.TimeoutError],
            'health_check_interval': 30,  # Keep connection alive
        }
        
        # Handle SSL for Azure Cache
        if parsed_url.scheme == 'rediss':
            connection_kwargs.update({
                'ssl': True,
                'ssl_cert_reqs': 'required',
                'ssl_ca_certs': None,  # Use system CA bundle
                'ssl_check_hostname': True,
            })
            
            # For development/testing only - skip cert verification
            if settings.environment == "development" and settings.redis_ssl_cert_reqs == "none":
                connection_kwargs['ssl_cert_reqs'] = 'none'
                connection_kwargs['ssl_check_hostname'] = False
        
        return redis.from_url(settings.redis_url, **connection_kwargs)
    
    # If using individual settings
    else:
        connection_kwargs = {
            'host': settings.redis_host,
            'port': settings.redis_port,
            'db': settings.redis_db,
            'password': settings.redis_password,
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True,
            'retry_on_error': [redis.ConnectionError, redis.TimeoutError],
            'health_check_interval': 30,
        }
        
        # Azure Cache requires SSL on port 6380
        if settings.redis_ssl or settings.redis_port == 6380:
            connection_kwargs.update({
                'ssl': True,
                'ssl_cert_reqs': getattr(ssl, f'CERT_{settings.redis_ssl_cert_reqs.upper()}', ssl.CERT_REQUIRED),
                'ssl_ca_certs': None,
                'ssl_check_hostname': True,
            })
            
            # Development mode - less strict SSL
            if settings.environment == "development" and settings.redis_ssl_cert_reqs == "none":
                connection_kwargs['ssl_cert_reqs'] = ssl.CERT_NONE
                connection_kwargs['ssl_check_hostname'] = False
        
        return redis.Redis(**connection_kwargs)

def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key based on IP and user if authenticated"""
    # Try to get user from JWT token
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(
                token, 
                settings.secret_key, 
                algorithms=[settings.algorithm],
                options={"verify_signature": False}  # Just to get user ID
            )
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except:
            pass
    
    # Fall back to IP address
    return get_remote_address(request)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Initialize settings
settings = get_settings()
# For Python < 3.11 compatibility
UTC = timezone.utc



# Initialize rate limiter with Redis
limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=settings.redis_connection_string,
    default_limits=[settings.rate_limit_default] if settings.rate_limit_enabled else [],
    enabled=settings.rate_limit_enabled
)



# Redis client 
try:
    # Use Azure-optimized client
    redis_client = create_azure_redis_client(settings)
    
    # Test connection with retry
    max_retries = 3
    for attempt in range(max_retries):
        try:
            redis_client.ping()
            logger.info(f"Connected to Redis at {settings.redis_host or 'URL'}")
            
            # Log connection details for Azure Cache
            if "redis.cache.windows.net" in (settings.redis_host or settings.redis_url or ""):
                info = redis_client.info()
                logger.info(f"Azure Cache for Redis - Version: {info.get('redis_version')}, "
                        f"Mode: {info.get('redis_mode', 'standalone')}, "
                        f"Memory: {info.get('used_memory_human', 'N/A')}")
            break
        except redis.ConnectionError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Redis connection attempt {attempt + 1} failed, retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise            
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    logger.error("Ensure Azure Cache for Redis is accessible and credentials are correct")
    sys.exit(1)
except Exception as e:
    logger.error(f"Redis initialization error: {e}")
    sys.exit(1)



# MSAL configuration
msal_config = {
    "client_id": settings.azure_client_id,
    "client_secret": settings.azure_client_secret,
    "authority": f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
}
# Creates MSAL application instance
msal_app = msal.ConfidentialClientApplication(
    msal_config["client_id"],
    authority=msal_config["authority"],
    client_credential=msal_config["client_secret"],
)



