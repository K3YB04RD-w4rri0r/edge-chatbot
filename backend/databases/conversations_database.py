from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import logging
from typing import AsyncGenerator
import urllib.parse
import re

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Base class for models
Base = declarative_base()

def get_database_url(async_driver: bool = False) -> str:
    """
    Construct database URL for Azure Database for PostgreSQL or MySQL
    """
    if settings.database_url:
        url = settings.database_url
        if async_driver:
            # Convert sync URL to async URL with explicit drivers
            if "postgresql" in url and "+asyncpg" not in url:
                # Handle various PostgreSQL driver formats
                if "postgresql+psycopg2://" in url:
                    url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
                elif "postgresql+psycopg://" in url:
                    url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
                elif "postgresql://" in url:
                    url = url.replace("postgresql://", "postgresql+asyncpg://")
                # Convert sslmode to ssl for asyncpg
                if "sslmode=" in url:
                    url = re.sub(r'sslmode=([^&]+)', r'ssl=\1', url)
            elif "mysql" in url and "+aiomysql" not in url:
                # Handle various MySQL driver formats
                if "mysql+pymysql://" in url:
                    url = url.replace("mysql+pymysql://", "mysql+aiomysql://")
                elif "mysql://" in url:
                    url = url.replace("mysql://", "mysql+aiomysql://")
        else:
            # Convert async URL back to sync URL with explicit drivers
            if "postgresql+asyncpg://" in url:
                url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
                # Convert ssl to sslmode for psycopg2
                if "ssl=" in url and "sslmode=" not in url:
                    url = re.sub(r'ssl=([^&]+)', r'sslmode=\1', url)
            elif "postgresql+psycopg://" in url and "+psycopg2" not in url:
                # Already a sync driver, but ensure it's the correct one
                url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
            elif url.startswith("postgresql://"):
                # Plain postgresql:// should be converted to explicit sync driver
                url = url.replace("postgresql://", "postgresql+psycopg2://")
            elif "mysql+aiomysql://" in url:
                url = url.replace("mysql+aiomysql://", "mysql+pymysql://")
            elif url.startswith("mysql://"):
                # Plain mysql:// should be converted to explicit sync driver
                url = url.replace("mysql://", "mysql+pymysql://")
        return url
    
    # URL encode password to handle special characters
    password = urllib.parse.quote_plus(settings.db_password)
    
    if settings.db_type.lower() == "postgresql":
        # PostgreSQL URL format for Azure with explicit drivers
        username = settings.db_user
        if "@" not in username and settings.db_host.endswith(".postgres.database.azure.com"):
            # Azure PostgreSQL requires username@servername format
            server_name = settings.db_host.split(".")[0]
            username = f"{settings.db_user}@{server_name}"
        
        # URL encode the username to handle special characters
        username = urllib.parse.quote_plus(username)
        
        # Choose driver based on async requirement - explicit drivers
        driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
        
        # Build base URL
        base_url = (
            f"{driver}://{username}:{password}@"
            f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
        )
        
        # Add SSL parameters safely
        ssl_params = []
        if hasattr(settings, 'db_ssl_mode') and settings.db_ssl_mode:
            # Validate and escape SSL mode
            ssl_mode = str(settings.db_ssl_mode).strip()
            if ssl_mode in ['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full']:
                ssl_params.append(f"sslmode={urllib.parse.quote_plus(ssl_mode)}")
            else:
                logger.warning(f"Invalid SSL mode '{ssl_mode}', defaulting to 'require'")
                ssl_params.append("sslmode=require")
        else:
            # Default to require for Azure
            ssl_params.append("sslmode=require")
        
        # Add any additional SSL parameters if needed
        if hasattr(settings, 'db_ssl_cert') and settings.db_ssl_cert:
            ssl_params.append(f"sslcert={urllib.parse.quote_plus(settings.db_ssl_cert)}")
        if hasattr(settings, 'db_ssl_key') and settings.db_ssl_key:
            ssl_params.append(f"sslkey={urllib.parse.quote_plus(settings.db_ssl_key)}")
        if hasattr(settings, 'db_ssl_rootcert') and settings.db_ssl_rootcert:
            ssl_params.append(f"sslrootcert={urllib.parse.quote_plus(settings.db_ssl_rootcert)}")
        
        url = base_url + ("?" + "&".join(ssl_params) if ssl_params else "")
    
    else:
        raise ValueError(f"Unsupported database type: {settings.db_type}. Use 'postgresql'")
    
    # Log URL structure (without credentials) in development
    if settings.is_development:
        safe_url = url.split("://")[0] + "://***:***@" + url.split("@", 1)[1] if "@" in url else url
        logger.debug(f"Generated database URL: {safe_url}")
    
    return url

# Create sync engine with Azure-optimized settings
def create_azure_engine():
    """
    Create SQLAlchemy engine optimized for Azure databases
    """
    database_url = get_database_url(async_driver=False)
    
    # Azure-optimized connection pool settings
    engine_args = {
        "pool_pre_ping": True,  # Verify connections before using
        "pool_recycle": 300,    # Recycle connections after 5 minutes
        "echo": settings.is_development,  # Log SQL in development
    }
    
    if settings.is_production:
        # Production settings for Azure
        engine_args.update({
            "poolclass": QueuePool,
            "pool_size": 20,        # Azure SQL Database supports many connections
            "max_overflow": 10,     # Additional connections when needed
            "pool_timeout": 30,     # Wait up to 30 seconds for a connection
        })
    else:
        # Development settings
        engine_args.update({
            "poolclass": QueuePool,
            "pool_size": 5,
            "max_overflow": 0,
        })
    
    engine = create_engine(database_url, **engine_args)
    
    return engine

# Create async engine with Azure-optimized settings
def create_azure_async_engine():
    """
    Create async SQLAlchemy engine optimized for Azure databases
    """
    database_url = get_database_url(async_driver=True)
    
    # Azure-optimized connection pool settings for async
    # Note: Do NOT specify poolclass for async engines - SQLAlchemy will
    # automatically use AsyncAdaptedQueuePool
    engine_args = {
        "pool_pre_ping": True,  # Verify connections before using
        "pool_recycle": 300,    # Recycle connections after 5 minutes
        "echo": settings.is_development,  # Log SQL in development
    }
    
    if settings.is_production:
        # Production settings for Azure
        engine_args.update({
            "pool_size": 20,        # Azure SQL Database supports many connections
            # Note: max_overflow is handled differently in async engines
        })
    else:
        # Development settings
        engine_args.update({
            "pool_size": 5,
        })
    
    async_engine = create_async_engine(database_url, **engine_args)
    return async_engine



# Create engines and sessions
try:
    # Sync engine (for scripts, etc.)
    engine = create_azure_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Async engine (for web routes)
    async_engine = create_azure_async_engine()
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    logger.info(f"Database engines created for {settings.db_type} at {settings.db_host}")
except Exception as e:
    logger.error(f"Failed to create database engines: {e}")
    raise





# Async dependency to get database session (Used for the routes)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Primary async database dependency for all routes"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Test database connection (async version)
async def test_async_db_connection() -> bool:
    """
    Test if async database is accessible
    """
    try:
        async with async_engine.begin() as conn:
            # Simple query that works on all databases
            result = await conn.execute(text("SELECT 1"))
            await result.fetchone()
            logger.info("Async database connection test successful")
            return True
    except Exception as e:
        logger.error(f"Async database connection test failed: {e}")
        return False

# Test database connection (sync version)
def test_db_connection() -> bool:
    """
    Test if sync database is accessible
    """
    try:
        # Try to connect and execute a simple query
        with engine.connect() as conn:
            # Simple query that works on all databases
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            logger.info("Sync database connection test successful")
            return True
    except Exception as e:
        logger.error(f"Sync database connection test failed: {e}")
        return False
