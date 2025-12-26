"""
Test Database Connection
=========================
Quick script to verify SQL Server connection.
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import engine
from app.core.config import settings
from sqlalchemy import text


async def test_connection():
    """Test database connection"""
    print("=" * 80)
    print("Testing SQL Server Connection")
    print("=" * 80)
    print(f"Host: {settings.DB_HOST}:{settings.DB_PORT}")
    print(f"Database: {settings.DB_NAME}")
    print(f"User: {settings.DB_USER}")
    print("")
    
    try:
        async with engine.begin() as conn:
            # Get SQL Server version
            result = await conn.execute(text("SELECT @@VERSION"))
            version = result.scalar()
            
            print("✓ Connection successful!")
            print("")
            print("SQL Server Version:")
            print(version)
            print("")
            
            # Get database name
            result = await conn.execute(text("SELECT DB_NAME()"))
            db_name = result.scalar()
            print(f"✓ Connected to database: {db_name}")
            print("")
            
            # List tables
            result = await conn.execute(text("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """))
            tables = result.fetchall()
            
            if tables:
                print(f"✓ Found {len(tables)} tables:")
                for table in tables:
                    print(f"  - {table[0]}")
            else:
                print("⚠ No tables found. Run migrations:")
                print("  alembic upgrade head")
                print("  OR")
                print("  python backend/scripts/init_db.py")
            
            print("")
            print("=" * 80)
            print("Connection test complete!")
            print("=" * 80)
            
    except Exception as e:
        print(f"✗ Connection failed:")
        print(f"  Error: {e}")
        print("")
        print("Troubleshooting:")
        print("1. Ensure SQL Server is running")
        print("2. Check credentials in .env file")
        print("3. Verify ODBC Driver 17 is installed")
        print("4. Check firewall settings")
        raise


if __name__ == "__main__":
    asyncio.run(test_connection())
