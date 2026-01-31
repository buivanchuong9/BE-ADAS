#!/bin/bash
# Script để fix Celery worker bị stuck/deadlock

echo "🔧 FIXING CELERY WORKER..."
echo ""

# 1. Kill all Celery processes
echo "1️⃣ Killing all Celery processes..."
pkill -9 -f "celery"
sleep 2

# 2. Clear Redis queue (DANGEROUS - only if stuck)
echo "2️⃣ Clearing Redis queue..."
read -p "⚠️  Clear Redis queue? This will delete all pending tasks! (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    redis-cli FLUSHALL
    echo "   ✅ Redis cleared"
else
    echo "   ⏭️  Skipped Redis clear"
fi

# 3. Navigate to project
echo ""
echo "3️⃣ Navigating to project..."
cd ~/BE-ADAS

# 4. Export env
echo "4️⃣ Exporting environment..."
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend

# 5. Start Celery worker
echo ""
echo "5️⃣ Starting Celery worker..."
nohup python -m celery -A app.core.celery_config worker --loglevel=info --pool=solo > logs/worker.log 2>&1 &
WORKER_PID=$!
echo "   ✅ Worker started (PID: $WORKER_PID)"

# 6. Start Celery beat
echo ""
echo "6️⃣ Starting Celery beat..."
nohup python -m celery -A app.core.celery_config beat --loglevel=info > logs/beat.log 2>&1 &
BEAT_PID=$!
echo "   ✅ Beat started (PID: $BEAT_PID)"

# 7. Verify
echo ""
echo "7️⃣ Verifying worker is running..."
sleep 3
ps aux | grep celery | grep -v grep

echo ""
echo "✅ CELERY WORKER FIXED!"
echo ""
echo "📋 Next steps:"
echo "   1. Check logs: tail -f logs/worker.log"
echo "   2. Upload a test video"
echo "   3. Monitor processing"
