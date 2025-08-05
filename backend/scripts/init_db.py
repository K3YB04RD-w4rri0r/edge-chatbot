import os
import sys
import logging
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError


from backend.databases.conversations_database import Base, test_db_connection, get_database_url
from config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


def get_engine():
    """Lazy load engine to avoid import-time failures"""
    from backend.databases.conversations_database import engine
    return engine


def create_database_if_not_exists():
    """Create the database if it doesn't exist (PostgreSQL only)"""
    if settings.db_type.lower() != "postgresql":
        return True
    
    try:
        engine = get_engine()
        # Try to connect to the target database
        with engine.connect() as conn:
            logger.info(f"Database '{settings.db_name}' already exists")
            return True
    except OperationalError as e:
        if "does not exist" in str(e):
            logger.info(f"Database '{settings.db_name}' does not exist. Creating...")
            
            # Connect to default 'postgres' database to create our database
            from sqlalchemy import create_engine
            temp_url = settings.database_url or get_database_url()
            temp_url = temp_url.replace(f"/{settings.db_name}", "/postgres")
            temp_engine = create_engine(temp_url, isolation_level='AUTOCOMMIT')
            
            try:
                with temp_engine.connect() as conn:
                    conn.execute(text(f"CREATE DATABASE {settings.db_name}"))
                    logger.info(f"✓ Database '{settings.db_name}' created successfully")
                return True
            except ProgrammingError as create_error:
                # Handle race condition: another pod might have created it
                if "already exists" in str(create_error) or "duplicate_database" in str(create_error):
                    logger.info(f"✓ Database '{settings.db_name}' already exists (created by another process)")
                    return True
                else:
                    logger.error(f"Failed to create database: {create_error}")
                    return False
            except Exception as create_error:
                logger.error(f"Failed to create database: {create_error}")
                return False
        else:
            logger.error(f"Database connection error: {e}")
            return False


def verify_tables_exist():
    """Verify that all required tables exist in the database"""
    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {'users', 'conversations', 'messages', 'attachments'}
    
    missing_tables = required_tables - existing_tables
    if missing_tables:
        logger.warning(f"Missing tables: {missing_tables}")
        return False
    
    logger.info(f"✓ All required tables exist: {existing_tables}")
    return True


def create_tables_with_sqlalchemy():
    """Try to create tables using SQLAlchemy ORM"""
    try:
        logger.info("Creating tables using SQLAlchemy...")
        engine = get_engine()
        
        # Ensure models are imported (they are at the top)
        logger.info(f"Models registered: {list(Base.metadata.tables.keys())}")
        
        # Create all tables
        Base.metadata.create_all(bind=engine, checkfirst=True)
        
        # Verify they were created
        if verify_tables_exist():
            logger.info("✓ Tables created successfully with SQLAlchemy")
            return True
        else:
            logger.warning("SQLAlchemy create_all() completed but tables not found")
            return False
            
    except Exception as e:
        logger.error(f"Error creating tables with SQLAlchemy: {e}")
        return False


def create_tables_with_sql():
    """Create tables using raw SQL as fallback"""
    try:
        logger.info("Creating tables using raw SQL...")
        engine = get_engine()
        
        with engine.begin() as conn:  # This ensures commit
            # Create users table
            if settings.db_type.lower() == "postgresql":
                # PostgreSQL version with trigger for updated_at
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(36) PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        display_name VARCHAR(255),
                        given_name VARCHAR(100),
                        surname VARCHAR(100),
                        job_title VARCHAR(255),
                        department VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE NOT NULL,
                        is_admin BOOLEAN DEFAULT FALSE NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        last_login TIMESTAMP WITH TIME ZONE
                    )
                """))
                
                # Create trigger function for updating updated_at
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql'
                """))
                
                # Create trigger for users table
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS update_users_updated_at ON users
                """))
                conn.execute(text("""
                    CREATE TRIGGER update_users_updated_at
                        BEFORE UPDATE ON users
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column()
                """))
                
            else:
                # MySQL version with ON UPDATE CURRENT_TIMESTAMP
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(36) PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        display_name VARCHAR(255),
                        given_name VARCHAR(100),
                        surname VARCHAR(100),
                        job_title VARCHAR(255),
                        department VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE NOT NULL,
                        is_admin BOOLEAN DEFAULT FALSE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
                        last_login TIMESTAMP
                    )
                """))
            
            # Create indexes for users
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_email ON users(email)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_active ON users(is_active)"))
            
            # Create conversations table with proper defaults
            if settings.db_type.lower() == "postgresql":
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id SERIAL PRIMARY KEY,
                        owner_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        conversation_title VARCHAR(255) NOT NULL,
                        status VARCHAR(50) DEFAULT 'active' NOT NULL,
                        model_choice VARCHAR(36) DEFAULT 'gpt-4o' NOT NULL,
                        model_instructions VARCHAR(511) DEFAULT 'You are a helpful, harmless, and honest assistant.' NOT NULL,
                        token_count INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        accessed_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                
                # Create trigger for conversations table
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations
                """))
                conn.execute(text("""
                    CREATE TRIGGER update_conversations_updated_at
                        BEFORE UPDATE ON conversations
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column()
                """))
                
            else:
                # MySQL version
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        owner_id VARCHAR(36) NOT NULL,
                        conversation_title VARCHAR(255) NOT NULL,
                        status VARCHAR(50) DEFAULT 'active' NOT NULL,
                        model_choice VARCHAR(36) DEFAULT 'gpt-4o' NOT NULL,
                        model_instructions VARCHAR(511) DEFAULT 'You are a helpful, harmless, and honest assistant.' NOT NULL,
                        token_count INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
                        accessed_at TIMESTAMP,
                        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """))
            
            # Create indexes for conversations
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_owner_status ON conversations(owner_id, status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_owner_created ON conversations(owner_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_status_created ON conversations(status, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_model_instructions ON conversations(model_instructions)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conversation_model_choice ON conversations(model_choice)"))
            
            # Create messages table
            if settings.db_type.lower() == "postgresql":
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        parent_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
                        role VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        token_count INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        edited_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                
                # Create trigger for messages table
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS update_messages_updated_at ON messages
                """))
                conn.execute(text("""
                    CREATE TRIGGER update_messages_updated_at
                        BEFORE UPDATE ON messages
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column()
                """))
                
            else:
                # MySQL version
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        conversation_id INT NOT NULL,
                        parent_message_id INT,
                        role VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        token_count INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
                        edited_at TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                        FOREIGN KEY (parent_message_id) REFERENCES messages(id) ON DELETE SET NULL
                    )
                """))
            
            # Create indexes for messages
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_message_conversation_created ON messages(conversation_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_message_conversation_role ON messages(conversation_id, role)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_message_parent ON messages(parent_message_id)"))
            
            # Create attachments table (corrected to match SQLAlchemy model)
            if settings.db_type.lower() == "postgresql":
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS attachments (
                        id SERIAL PRIMARY KEY,
                        uuid VARCHAR(36) UNIQUE NOT NULL,
                        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        uploader_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        filename VARCHAR(255) NOT NULL,
                        original_filename VARCHAR(255) NOT NULL,
                        content_type VARCHAR(100) NOT NULL,
                        file_size BIGINT NOT NULL,
                        file_hash VARCHAR(64) NOT NULL,
                        storage_path VARCHAR(500) NOT NULL,
                        storage_backend VARCHAR(50) DEFAULT 'azure' NOT NULL,
                        attachment_type VARCHAR(20) DEFAULT 'other' NOT NULL,
                        extra_metadata JSONB,
                        activity_status VARCHAR(20) DEFAULT 'inactive' NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                        virus_scanned BOOLEAN DEFAULT FALSE NOT NULL,
                        virus_scan_result VARCHAR(255),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        deleted_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                
                # Create trigger for attachments table
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS update_attachments_updated_at ON attachments
                """))
                conn.execute(text("""
                    CREATE TRIGGER update_attachments_updated_at
                        BEFORE UPDATE ON attachments
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column()
                """))
                
            else:
                # MySQL version
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS attachments (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        uuid VARCHAR(36) UNIQUE NOT NULL,
                        conversation_id INT NOT NULL,
                        uploader_id VARCHAR(36) NOT NULL,
                        filename VARCHAR(255) NOT NULL,
                        original_filename VARCHAR(255) NOT NULL,
                        content_type VARCHAR(100) NOT NULL,
                        file_size BIGINT NOT NULL,
                        file_hash VARCHAR(64) NOT NULL,
                        storage_path VARCHAR(500) NOT NULL,
                        storage_backend VARCHAR(50) DEFAULT 'azure' NOT NULL,
                        attachment_type VARCHAR(20) DEFAULT 'other' NOT NULL,
                        extra_metadata JSON,
                        activity_status VARCHAR(20) DEFAULT 'inactive' NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                        virus_scanned BOOLEAN DEFAULT FALSE NOT NULL,
                        virus_scan_result VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
                        deleted_at TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                        FOREIGN KEY (uploader_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                """))
            
            # Create indexes for attachments
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_attachment_uuid ON attachments(uuid)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_attachment_conversation ON attachments(conversation_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_attachment_uploader_created ON attachments(uploader_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_attachment_status ON attachments(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_attachment_activity_status ON attachments(activity_status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_attachment_hash ON attachments(file_hash)"))
            
            logger.info("✓ SQL execution completed")
        
        # Verify tables were created
        return verify_tables_exist()
        
    except Exception as e:
        logger.error(f"Error creating tables with SQL: {e}")
        return False


def show_table_info():
    """Display information about existing tables"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            logger.info("\nDatabase table information:")
            logger.info("-" * 50)
            
            # Get table information based on database type
            if settings.db_type.lower() == "postgresql":
                query = text("""
                    SELECT 
                        t.table_name,
                        COUNT(c.column_name) as column_count
                    FROM information_schema.tables t
                    LEFT JOIN information_schema.columns c 
                        ON t.table_name = c.table_name 
                        AND t.table_schema = c.table_schema
                    WHERE t.table_schema = 'public' 
                        AND t.table_type = 'BASE TABLE'
                    GROUP BY t.table_name
                    ORDER BY t.table_name
                """)
            else:  # MySQL
                query = text("""
                    SELECT 
                        t.TABLE_NAME as table_name,
                        COUNT(c.COLUMN_NAME) as column_count
                    FROM information_schema.TABLES t
                    LEFT JOIN information_schema.COLUMNS c 
                        ON t.TABLE_NAME = c.TABLE_NAME 
                        AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
                    WHERE t.TABLE_SCHEMA = :db_name 
                        AND t.TABLE_TYPE = 'BASE TABLE'
                    GROUP BY t.TABLE_NAME
                    ORDER BY t.TABLE_NAME
                """)
            
            result = conn.execute(query, {"db_name": settings.db_name} if settings.db_type.lower() == "mysql" else {})
            
            for table_name, column_count in result:
                logger.info(f"Table: {table_name} ({column_count} columns)")
                
                # Get row count using safer method
                row_count = get_safe_row_count(conn, table_name)
                logger.info(f"  Rows: {row_count}")
            
            logger.info("-" * 50)
            
    except Exception as e:
        logger.error(f"Error getting table info: {e}")


def get_safe_row_count(conn, table_name):
    """Safely get row count for a table using proper quoting and column access"""
    try:
        # Use proper identifier quoting based on database type
        if settings.db_type.lower() == "postgresql":
            # PostgreSQL uses double quotes for identifiers
            quoted_table = f'"{table_name}"'
        else:  # MySQL
            # MySQL uses backticks for identifiers
            quoted_table = f'`{table_name}`'
        
        # This is safe because table_name comes from database metadata, not user input
        count_query = text(f'SELECT COUNT(*) as row_count FROM {quoted_table}')
        result = conn.execute(count_query)
        row = result.first()
        
        # Safe column access - try different approaches
        if hasattr(row, 'row_count'):
            return row.row_count
        elif hasattr(row, 'ROW_COUNT'):  # MySQL might uppercase it
            return row.ROW_COUNT
        else:
            # Use index access as fallback
            return row[0]
            
    except Exception as e:
        logger.error(f"Error getting row count for {table_name}: {e}")
        return "Error"


def init_database():
    """Initialize database with all necessary tables"""
    logger.info(f"Initializing {settings.db_type} database at {settings.db_host}...")
    
    # Step 1: Test connection
    if not test_db_connection():
        logger.error("Failed to connect to database. Please check your configuration.")
        return False
    
    # Step 2: Create database if needed (PostgreSQL only)
    if settings.db_type.lower() == "postgresql":
        if not create_database_if_not_exists():
            return False
    
    # Step 3: Check if tables already exist
    if verify_tables_exist():
        logger.info("✓ All tables already exist!")
        show_table_info()
        return True
    
    # Step 4: Try to create tables with SQLAlchemy first
    logger.info("Creating database tables...")
    if create_tables_with_sqlalchemy():
        show_table_info()
        return True
    
    # Step 5: Fallback to raw SQL
    logger.warning("SQLAlchemy method failed, trying raw SQL...")
    if create_tables_with_sql():
        show_table_info()
        return True
    
    logger.error("Failed to create tables with both methods")
    return False


def drop_all_tables():
    """Drop all tables (use with caution!)"""
    logger.warning(f"Dropping all tables from {settings.db_type} database...")
    
    try:
        engine = get_engine()
        with engine.begin() as conn:
            # Drop triggers first (PostgreSQL)
            if settings.db_type.lower() == "postgresql":
                conn.execute(text("DROP TRIGGER IF EXISTS update_attachments_updated_at ON attachments"))
                conn.execute(text("DROP TRIGGER IF EXISTS update_messages_updated_at ON messages"))
                conn.execute(text("DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations"))
                conn.execute(text("DROP TRIGGER IF EXISTS update_users_updated_at ON users"))
                conn.execute(text("DROP FUNCTION IF EXISTS update_updated_at_column()"))
            
            # Drop in correct order due to foreign keys
            conn.execute(text("DROP TABLE IF EXISTS attachments CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS messages CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS conversations CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            logger.info("✓ All tables dropped successfully")
        return True
    except Exception as e:
        logger.error(f"Error dropping tables: {e}")
        return False


def main():
    """Main function with CLI argument handling"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database initialization tool')
    parser.add_argument('--drop', action='store_true', help='Drop all tables')
    parser.add_argument('--info', action='store_true', help='Show table information')
    parser.add_argument('--recreate', action='store_true', help='Drop and recreate all tables')
    parser.add_argument('--verify', action='store_true', help='Verify tables exist')
    
    args = parser.parse_args()
    

    
    try:
        # Handle connection errors gracefully
        if args.info:
            try:
                if test_db_connection():
                    show_table_info()
                else:
                    logger.error("Cannot connect to database")
                    return 1
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                logger.info("Make sure your database server is running and accessible")
                return 1
                
        elif args.verify:
            try:
                if test_db_connection():
                    if verify_tables_exist():
                        logger.info("✓ All required tables exist")
                        show_table_info()
                        return 0
                    else:
                        logger.error("✗ Some tables are missing")
                        return 1
                else:
                    logger.error("Cannot connect to database")
                    return 1
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                return 1
                
        elif args.drop:
            response = input("⚠️  Are you sure you want to DROP all tables? This cannot be undone! (yes/no): ")
            if response.lower() == "yes":
                try:
                    if drop_all_tables():
                        return 0
                    return 1
                except Exception as e:
                    logger.error(f"Failed to drop tables: {e}")
                    return 1
            else:
                logger.info("Operation cancelled.")
                return 0
                
        elif args.recreate:
            response = input("⚠️  This will DROP and RECREATE all tables. All data will be lost! Continue? (yes/no): ")
            if response.lower() == "yes":
                try:
                    if drop_all_tables() and init_database():
                        logger.info("\n✅ Database recreated successfully!")
                        return 0
                    return 1
                except Exception as e:
                    logger.error(f"Failed to recreate database: {e}")
                    return 1
            else:
                logger.info("Operation cancelled.")
                return 0
                
        else:
            # Default action: initialize database
            try:
                if init_database():
                    logger.info("\n✅ Database initialization complete!")
                    logger.info("You can now run your FastAPI application.")
                    return 0
                else:
                    logger.error("\n❌ Database initialization failed!")
                    logger.error("Please check the errors above and try again.")
                    return 1
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                logger.info("Make sure your database server is running and accessible")
                return 1
                
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())