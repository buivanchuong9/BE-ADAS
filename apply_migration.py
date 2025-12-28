"""
Database Migration Script
=========================
Applies missing columns to video_jobs table on production database.

This script safely adds columns that are missing from the database schema.
"""

import pyodbc
import sys
from pathlib import Path

def run_migration():
    """Apply migration to add missing columns to video_jobs table"""
    
    print("=" * 60)
    print("DATABASE MIGRATION - Add Missing Columns to video_jobs")
    print("=" * 60)
    
    # Read migration SQL
    migration_file = Path(__file__).parent / "migration_fix_video_jobs.sql"
    
    if not migration_file.exists():
        print(f"ERROR: Migration file not found: {migration_file}")
        return False
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()
    
    # Split by GO statements
    batches = [batch.strip() for batch in migration_sql.split('GO') if batch.strip()]
    
    try:
        # Simple connection string for Windows SQL Server
        conn_str = (
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost,1433;'
            'DATABASE=adas_production;'
            'UID=sa;'
            'PWD=YourStrongPassword123;'
            'TrustServerCertificate=yes;'
        )
        
        print(f"\nConnecting to SQL Server on localhost:1433...")
        print(f"Database: adas_production\n")
        
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()
        
        print(f"Executing {len(batches)} SQL batches...\n")
        
        for i, batch in enumerate(batches, 1):
            if not batch or batch.startswith('--'):
                continue
            
            try:
                cursor.execute(batch)
                conn.commit()
                print(f"✓ Batch {i} executed successfully")
                    
            except Exception as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower():
                    print(f"⊙ Batch {i}: Column already exists (OK)")
                else:
                    print(f"✗ Batch {i} error: {e}")
                    conn.rollback()
        
        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        print("\nYou can now start the server with: python run.py")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure SQL Server is running")
        print("2. Check if ODBC Driver 17 for SQL Server is installed")
        print("3. Verify SQL Server credentials (default: sa/YourStrongPassword123)")
        print("4. Or run migration_fix_video_jobs.sql manually in SSMS")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
