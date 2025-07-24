from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional, List

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
    
    # Logging Configuration
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

@lru_cache()
def get_settings():
    return Settings()