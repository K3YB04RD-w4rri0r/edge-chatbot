# Tiny Item In-memory database for testing purposes
items_db = {}
current_id = 1


# backend/database.py - Simple fix
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
    # IMPORTANT: Import models here to register them with Base
    # This import must happen AFTER Base is defined
    import backend.models.auth_models  # This registers the User model
    
    # Now create all tables
    Base.metadata.create_all(bind=engine)
    
    # Verify creation
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Database initialized. Tables: {tables}")
    
    if 'users' not in tables:
        raise RuntimeError("Failed to create users table! Check model imports.")

