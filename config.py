from pydantic_settings import BaseSettings
from pydantic import validator
from functools import lru_cache
from typing import Optional, List, Dict
import json

class Settings(BaseSettings):
    # Azure AD Configuration
    azure_client_id: str
    azure_client_secret: str
    azure_tenant_id: str = "common"  # common, organizations, consumers, or specific tenant ID
    redirect_uri: str
    
    # JWT Configuration
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Application Configuration
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    environment: str = "development"  # development, staging, production
    
    # CORS Configuration
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000", "http://127.0.0.1:8080"]
    cors_allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE"]
    cors_allow_headers: List[str] = ["Content-Type", "Authorization"]
    
    # Redis Configuration (optional in development)
    redis_url: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # Security Configuration
    secure_cookies: bool = False  # Set to True in production
    cookie_domain: Optional[str] = None  # Set for production (e.g., ".yourdomain.com")
    cookie_samesite: str = "lax"  # lax, strict, or none
    
    # Rate Limiting Configuration
    rate_limit_enabled: bool = True
    rate_limit_default: str = "1000 per hour"  # Default global rate limit
    rate_limit_auth: str = "10 per minute"     # For auth endpoints
    rate_limit_refresh: str = "5 per minute"   # For token refresh
    rate_limit_api: str = "100 per minute"     # For regular API endpoints
    
    # Per-endpoint rate limits (can be customized)
    rate_limits: Dict[str, str] = {
        "/auth/microsoft": "10 per minute",
        "/auth/microsoft/callback": "20 per minute",
        "/auth/refresh": "5 per minute",
        "/auth/logout": "20 per minute",
        "/api/user": "100 per minute",
        "/api/protected": "100 per minute",
        "/health": "30 per minute",
    }
    
    # Logging Configuration
    log_level: str = "INFO"
    
    @validator('cors_origins', 'cors_allow_methods', 'cors_allow_headers', pre=True)
    def parse_list(cls, v):
        if isinstance(v, str):
            # Handle JSON-like strings
            try:
                return json.loads(v)
            except:
                # Handle comma-separated values
                return [x.strip() for x in v.split(',')]
        return v
    
    @validator('rate_limits', pre=True)
    def parse_rate_limits(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                # If not valid JSON, return empty dict
                return {}
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"
    
    @property
    def redis_connection_string(self) -> Optional[str]:
        """Generate Redis connection string for rate limiter"""
        if self.redis_url:
            return self.redis_url
        elif self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        else:
            return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

@lru_cache()
def get_settings():
    return Settings()