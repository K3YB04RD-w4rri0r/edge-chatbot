# Tiny Item In-memory database for testing purposes
items_db = {}
current_id = 1


from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

# Create engine with settings
engine = create_engine(
    settings.database_url,
    **settings.database_settings
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    """
    Create a new database session for each request
    and close it when the request is done.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables
def init_db():
    """Initialize database tables"""
    # Import all models here to ensure they're registered
    from . import auth_models  # noqa
    Base.metadata.create_all(bind=engine)