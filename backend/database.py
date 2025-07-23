# Tiny Item In-memory database for testing purposes
items_db = {}
current_id = 1


# backend/database.py - Updated for Microsoft Auth
from sqlalchemy import create_engine, event
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
    import backend.models.auth_models  # This registers User and UserSession models
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Verify creation
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Database initialized. Tables: {tables}")
    
    expected_tables = ['users', 'user_sessions']
    missing_tables = [t for t in expected_tables if t not in tables]
    
    if missing_tables:
        raise RuntimeError(f"Failed to create tables: {missing_tables}")
    
    print("✓ All tables created successfully")
    
    # Optional: Create first admin user instructions
    print("\n" + "="*50)
    print("IMPORTANT: First User Setup")
    print("="*50)
    print("After the first user logs in via Microsoft:")
    print("1. Run: python -m scripts.make_first_admin")
    print("2. Or manually update the database:")
    print("   UPDATE users SET is_superuser = 1 WHERE id = 1;")
    print("="*50 + "\n")

# Optional: Add database event listeners for debugging
if settings.is_development:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Enable foreign keys for SQLite in development"""
        if settings.database_url.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

# Cleanup function for production
def cleanup_expired_sessions():
    """
    Cleanup expired sessions periodically.
    This should be called by a background task/cron job.
    """
    from datetime import datetime, timezone
    from backend.models.auth_models import UserSession
    
    db = SessionLocal()
    try:
        expired_count = db.query(UserSession).filter(
            UserSession.expires_at < datetime.now(timezone.utc)
        ).delete()
        db.commit()
        print(f"Cleaned up {expired_count} expired sessions")
    except Exception as e:
        print(f"Error cleaning up sessions: {e}")
        db.rollback()
    finally:
        db.close()
