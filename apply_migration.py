"""
Database Migration Script
=========================
Applies missing columns to video_jobs table on production database.

This script safely adds columns that are missing from the database schema.
"""

import pyodbc
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.app.core.config import settings

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
        # Connect to database
        conn_str = settings.database_url.replace('mssql+pyodbc://', '')
        print(f"\nConnecting to database...")
        print(f"Connection: {conn_str.split('@')[1] if '@' in conn_str else 'localhost'}")
        
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        print(f"\nExecuting {len(batches)} SQL batches...\n")
        
        for i, batch in enumerate(batches, 1):
            if not batch or batch.startswith('--'):
                continue
            
            try:
                cursor.execute(batch)
                conn.commit()
                
                # Get any print messages
                while cursor.nextset():
                    pass
                    
            except Exception as e:
                print(f"Batch {i} warning: {e}")
                conn.rollback()
        
        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print("\nPlease run the migration_fix_video_jobs.sql file manually")
        print("in SQL Server Management Studio or using sqlcmd.")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
