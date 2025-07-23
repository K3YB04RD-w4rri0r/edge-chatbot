from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List, Dict, Any
from functools import lru_cache
import secrets
import os
from enum import Enum


class Environment(str, Enum):
    """Application environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    
    # Application Settings
    app_name: str = Field(default="Internal_Edge_tool", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    environment: Environment = Field(default=Environment.DEVELOPMENT, env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # API Settings
    api_prefix: str = Field(default="/api/v1", env="API_PREFIX")
    openapi_url: Optional[str] = Field(default="/openapi.json", env="OPENAPI_URL")
    docs_url: Optional[str] = Field(default="/docs", env="DOCS_URL")
    redoc_url: Optional[str] = Field(default="/redoc", env="REDOC_URL")
    
    # Server Settings
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    reload: bool = Field(default=False, env="RELOAD")
    
    # Security Settings
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32), env="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    algorithm: str = Field(default="HS256", env="ALGORITHM")
    bcrypt_rounds: int = Field(default=12, env="BCRYPT_ROUNDS")
    
    # CORS Settings
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="CORS_ORIGINS"
    )
    cors_allow_credentials: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    cors_allow_methods: List[str] = Field(default=["*"], env="CORS_ALLOW_METHODS")
    cors_allow_headers: List[str] = Field(default=["*"], env="CORS_ALLOW_HEADERS")
    
    # Database Settings
    database_url: str = Field(
        default="sqlite:///./app.db",
        env="DATABASE_URL"
    )
    database_echo: bool = Field(default=False, env="DATABASE_ECHO")
    database_pool_size: int = Field(default=5, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, env="DATABASE_MAX_OVERFLOW")
    
    # Redis Settings (for caching, sessions, etc.)
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_db: int = Field(default=0, env="REDIS_DB")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL")  # seconds
    
    # Email Settings
    smtp_host: Optional[str] = Field(default=None, env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_user: Optional[str] = Field(default=None, env="SMTP_USER")
    smtp_password: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    smtp_tls: bool = Field(default=True, env="SMTP_TLS")
    email_from: str = Field(default="noreply@example.com", env="EMAIL_FROM")
    email_from_name: str = Field(default="My App", env="EMAIL_FROM_NAME")
    
    # AWS Settings (if using AWS services)
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    s3_bucket: Optional[str] = Field(default=None, env="S3_BUCKET")
    
    # External API Keys
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    stripe_api_key: Optional[str] = Field(default=None, env="STRIPE_API_KEY")
    stripe_webhook_secret: Optional[str] = Field(default=None, env="STRIPE_WEBHOOK_SECRET")
    sendgrid_api_key: Optional[str] = Field(default=None, env="SENDGRID_API_KEY")
    
    # Logging Settings
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        env="LOG_FORMAT"
    )
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    
    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    
    # File Upload Settings
    max_upload_size: int = Field(default=10 * 1024 * 1024, env="MAX_UPLOAD_SIZE")  # 10MB
    allowed_upload_extensions: List[str] = Field(
        default=[".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx"],
        env="ALLOWED_UPLOAD_EXTENSIONS"
    )
    upload_directory: str = Field(default="./uploads", env="UPLOAD_DIRECTORY")
    
    # Feature Flags
    enable_registration: bool = Field(default=True, env="ENABLE_REGISTRATION")
    enable_oauth: bool = Field(default=False, env="ENABLE_OAUTH")
    enable_2fa: bool = Field(default=False, env="ENABLE_2FA")
    maintenance_mode: bool = Field(default=False, env="MAINTENANCE_MODE")
    
    # Pagination
    default_page_size: int = Field(default=20, env="DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(default=100, env="MAX_PAGE_SIZE")
    
    # Monitoring and Analytics
    sentry_dsn: Optional[str] = Field(default=None, env="SENTRY_DSN")
    google_analytics_id: Optional[str] = Field(default=None, env="GOOGLE_ANALYTICS_ID")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    @field_validator("cors_origins", mode = "before")
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("environment", mode = "before")
    def validate_environment(cls, v):
        """Ensure environment is valid"""
        if isinstance(v, str):
            v = v.lower()
        return v
    
    @field_validator("database_url")
    def validate_database_url(cls, v, info):
        """Adjust database URL based on environment"""
        env = info.data.get("environment")
        if env == Environment.TESTING:
            return "sqlite:///./test.db"
        return v

    @field_validator("openapi_url", "docs_url", "redoc_url")
    def disable_docs_in_production(cls, v, info):
        """Disable API documentation in production"""
        if info.data.get("environment") == Environment.PRODUCTION:
            return None
        return v
    
    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT
    
    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION
    
    @property
    def is_testing(self) -> bool:
        return self.environment == Environment.TESTING
    
    @property
    def database_settings(self) -> Dict[str, Any]:
        """Get database configuration for SQLAlchemy"""
        return {
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
            "echo": self.database_echo,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
        }
    
    @property
    def redis_settings(self) -> Dict[str, Any]:
        """Get Redis configuration"""
        if not self.redis_url:
            return {}
        
        return {
            "url": self.redis_url,
            "password": self.redis_password,
            "db": self.redis_db,
            "decode_responses": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        }
    
    def get_db_url(self) -> str:
        """Get database URL with async driver if needed"""
        if self.database_url.startswith("postgresql://"):
            # Convert to async driver for asyncio
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        elif self.database_url.startswith("mysql://"):
            return self.database_url.replace("mysql://", "mysql+aiomysql://")
        return self.database_url


class DevelopmentSettings(Settings):
    """Development environment settings"""
    model_config = SettingsConfigDict(env_file=".env.development")
    
    debug: bool = True
    reload: bool = True
    database_echo: bool = True
    log_level: str = "DEBUG"


class ProductionSettings(Settings):
    """Production environment settings"""
    model_config = SettingsConfigDict(env_file=".env.production")
    
    debug: bool = False
    reload: bool = False
    database_echo: bool = False
    log_level: str = "INFO"
    
    @field_validator("secret_key")
    def validate_secret_key(cls, v):
        """Ensure secret key is set in production"""
        if not v or v == "changeme":
            raise ValueError("Secret key must be set in production")
        return v


class TestingSettings(Settings):
    """Testing environment settings"""
    model_config = SettingsConfigDict(env_file=".env.testing")
    
    environment: Environment = Environment.TESTING
    database_url: str = "sqlite:///./test.db"
    redis_db: int = 15  # Use a different Redis DB for testing


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    The @lru_cache decorator ensures we only create one instance
    of settings throughout the application lifetime.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return ProductionSettings()
    elif env == "testing":
        return TestingSettings()
    else:
        return DevelopmentSettings()


# Create a global settings instance
settings = get_settings()


# Configuration validation on startup
def validate_config():
    """Validate critical configuration on application startup"""
    errors = []
    
    # Check required settings in production
    if settings.is_production:
        if not settings.secret_key or settings.secret_key == "changeme":
            errors.append("SECRET_KEY must be set in production")
        
        if settings.debug:
            errors.append("DEBUG must be False in production")
        
        if "localhost" in settings.cors_origins or "*" in settings.cors_origins:
            errors.append("CORS origins should be restricted in production")
    
    # Check database connection
    if not settings.database_url:
        errors.append("DATABASE_URL must be set")
    
    # Check email configuration if enabled
    if settings.smtp_host and not all([settings.smtp_user, settings.smtp_password]):
        errors.append("SMTP credentials must be set when SMTP is enabled")
    
    if errors:
        raise ValueError(f"Configuration errors: {'; '.join(errors)}")
