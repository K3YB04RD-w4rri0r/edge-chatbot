from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import logging
from config import get_settings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)
settings: 'Settings' = get_settings()

# Database URL construction for Azure
# Format: postgresql://username:password@hostname:port/database
# For Azure SQL: mssql+pyodbc://username:password@hostname:port/database?driver=ODBC+Driver+17+for+SQL+Server
def get_database_url():
    """Construct database URL based on settings"""
    # You'll need to add these to your Settings class in config.py:
    # db_type: str = "postgresql"  # or "mssql" for Azure SQL
    # db_host: str
    # db_port: int = 5432  # or 1433 for SQL Server
    # db_name: str
    # db_user: str
    # db_password: str
    # db_ssl_mode: str = "require"  # for PostgreSQL
    
    if hasattr(settings, 'db_type') and settings.db_type == "mssql":
        # Azure SQL Database
        return (
            f"mssql+pyodbc://{settings.db_user}:{settings.db_password}@"
            f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
            f"?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
        )
    else:
        # Azure Database for PostgreSQL
        return (
            f"postgresql://{settings.db_user}:{settings.db_password}@"
            f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
            f"?sslmode={getattr(settings, 'db_ssl_mode', 'require')}"
        )

# Create engine with Azure-optimized settings
engine = create_engine(
    get_database_url(),
    # Connection pool settings optimized for Azure
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.is_development,  # SQL logging in development
    # For serverless/Azure Functions, use NullPool
    # poolclass=NullPool,
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    """
    Database session dependency for FastAPI routes
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Test database connection
def test_db_connection():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False