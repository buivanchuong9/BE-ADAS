#!/bin/bash
# Script to completely remove SQL Server legacy code
# Run this after backing up your database

echo "🗑️  Removing SQL Server legacy files..."

# Remove legacy session file
if [ -f "backend/app/db/session_v2_legacy.py" ]; then
    rm backend/app/db/session_v2_legacy.py
    echo "✓ Removed session_v2_legacy.py"
fi

# Remove legacy VideoJob model (already renamed to .legacy)
if [ -f "backend/app/db/models/video_job.py.legacy" ]; then
    rm backend/app/db/models/video_job.py.legacy
    echo "✓ Removed video_job.py.legacy"
fi

# Remove legacy VideoJobRepository (already renamed to .legacy)
if [ -f "backend/app/db/repositories/video_job_repo.py.legacy" ]; then
    rm backend/app/db/repositories/video_job_repo.py.legacy
    echo "✓ Removed video_job_repo.py.legacy"
fi

# Remove any .pyc files from deleted modules
find backend -name "*.pyc" -delete
find backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

echo ""
echo "✅ SQL Server legacy code removed successfully!"
echo ""
echo "📋 Summary:"
echo "   - session_v2_legacy.py (SQL Server session)"
echo "   - video_job.py (legacy model)"
echo "   - video_job_repo.py (legacy repository)"
echo ""
echo "🎯 System is now 100% PostgreSQL v3.0"
