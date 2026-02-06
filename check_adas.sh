#!/bin/bash
# Quick Debug Script - Check ADAS System Status
# Run on server: bash check_adas.sh

echo "======================================"
echo "🔍 ADAS SYSTEM DEBUG"
echo "======================================"

# 1. Check Celery Worker
echo ""
echo "[1] Celery Worker Status:"
systemctl status adas-worker | grep -A 3 "Active:"

# 2. Check if models exist
echo ""
echo "[2] Models Check:"
ls -lh ~/BE-ADAS/backend/models/*.pt 2>/dev/null || echo "❌ No models found"

# 3. Check Python imports
echo ""
echo "[3] Testing Python Imports:"
cd ~/BE-ADAS
python3 << 'EOF'
import sys
sys.path.insert(0, '/home/phonglv/BE-ADAS/backend')

print("Testing imports...")
try:
    from perception.pipeline.video_pipeline_v11 import process_video, VideoPipelineV11, ADASPipeline
    print("✅ process_video OK")
    print("✅ VideoPipelineV11 OK")
    print("✅ ADASPipeline OK")
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
EOF

# 4. Check recent logs
echo ""
echo "[4] Recent Worker Logs (last 20 lines):"
tail -n 20 ~/BE-ADAS/logs/worker.log

# 5. Check GPU
echo ""
echo "[5] GPU Status:"
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv 2>/dev/null || echo "ℹ️  GPU check skipped"

echo ""
echo "======================================"
echo "✅ Debug Complete"
echo "======================================"
