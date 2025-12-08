# Database configuration and connection
# Supports both SQLite (for testing) and SQL Server (for production)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, StaticPool
import os
from dotenv import load_dotenv
import urllib

load_dotenv()

# Get database URL from environment or use in-memory SQLite
# Use in-memory database to avoid file permission issues in Docker
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///:memory:")

# Determine if using SQLite
is_sqlite = DATABASE_URL.startswith("sqlite")

# Create engine with appropriate settings
if is_sqlite:
    # SQLite configuration
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Required for SQLite
        poolclass=StaticPool,
        echo=False,
    )
else:
    # SQL Server configuration - use DATABASE_URL from .env directly
    # This supports both the new format (DATABASE_URL with full connection string)
    # and legacy format (individual SQL_* environment variables)
    
    if "mssql" in DATABASE_URL or "pyodbc" in DATABASE_URL:
        # New format: DATABASE_URL contains full connection string
        engine = create_engine(
            DATABASE_URL,
            poolclass=NullPool,
            echo=False,
            connect_args={"timeout": 30}
        )
    else:
        # Legacy format: Build from individual environment variables
        SERVER = os.getenv("SQL_SERVER", "localhost")
        DATABASE = os.getenv("SQL_DATABASE", "ADAS_DB")
        USERNAME = os.getenv("SQL_USERNAME", "sa")
        PASSWORD = os.getenv("SQL_PASSWORD", "")
        DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")
        
        # Encode password for URL
        password_encoded = urllib.parse.quote_plus(PASSWORD) if PASSWORD else ""
        
        if PASSWORD:
            DATABASE_URL = f"mssql+pyodbc://{USERNAME}:{password_encoded}@{SERVER}/{DATABASE}?driver={DRIVER}&TrustServerCertificate=yes"
        else:
            # Windows Authentication
            DATABASE_URL = f"mssql+pyodbc://{SERVER}/{DATABASE}?driver={DRIVER}&trusted_connection=yes&TrustServerCertificate=yes"
        
        engine = create_engine(
            DATABASE_URL,
            poolclass=NullPool,
            echo=False,
            connect_args={"timeout": 30}
        )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency for FastAPI
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Test connection
def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            print("✅ Database connection successful!")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing database connection...")
    # Get server and database info for display
    if is_sqlite:
        print(f"Database: SQLite (in-memory)")
    else:
        server = os.getenv("SQL_SERVER", "localhost")
        database = os.getenv("SQL_DATABASE", "ADAS_DB")
        print(f"Server: {server}")
        print(f"Database: {database}")
    test_connection()
