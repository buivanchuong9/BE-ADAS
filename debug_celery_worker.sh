#!/bin/bash
# Debug script để kiểm tra tại sao Celery worker "im thít"

echo "🔍 DEBUGGING CELERY WORKER..."
echo ""

# 1. Check Celery worker process
echo "1️⃣ Checking Celery worker process..."
ps aux | grep celery | grep -v grep
echo ""

# 2. Check Redis connection
echo "2️⃣ Checking Redis connection..."
redis-cli ping
echo ""

# 3. Check Redis queue length
echo "3️⃣ Checking Redis queue length..."
redis-cli llen celery
echo ""

# 4. Check active tasks
echo "4️⃣ Checking active tasks in Redis..."
redis-cli keys "celery-task-meta-*" | wc -l
echo ""

# 5. Check worker log (last 50 lines)
echo "5️⃣ Checking worker log (last 50 lines)..."
tail -50 logs/worker.log
echo ""

# 6. Check if worker is stuck
echo "6️⃣ Checking if worker is processing anything..."
redis-cli --scan --pattern "celery-task-meta-*" | head -5 | while read key; do
    echo "Key: $key"
    redis-cli get "$key"
    echo ""
done

echo ""
echo "✅ Debug complete!"
echo ""
echo "📋 RECOMMENDATIONS:"
echo "   1. If worker process not found → Restart worker"
echo "   2. If Redis queue > 0 → Worker is stuck, restart it"
echo "   3. If active tasks > 0 but no progress → Worker deadlock, kill and restart"
echo "   4. If Redis ping fails → Restart Redis"
