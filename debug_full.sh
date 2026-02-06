#!/bin/bash
# Comprehensive ADAS Debug Script
# Check everything: code, imports, GPU, CUDA

echo "=========================================="
echo "🔍 COMPREHENSIVE ADAS DEBUG"
echo "=========================================="

cd ~/BE-ADAS

# 1. Check Git Status
echo ""
echo "=== [1] GIT STATUS ==="
echo "Current commit:"
git log --oneline -1
echo ""
echo "Changed files (if any):"
git status --short

# 2. Check __init__.py files
echo ""
echo "=== [2] CHECKING __init__.py FILES ==="
echo ""
echo "📁 backend/perception/pipeline/__init__.py:"
cat backend/perception/pipeline/__init__.py
echo ""
echo "📁 backend/perception/__init__.py:"
cat backend/perception/__init__.py
echo ""
echo "📁 backend/__init__.py:"
cat backend/__init__.py

# 3. Check if video_pipeline_v11.py exports correctly
echo ""
echo "=== [3] CHECKING video_pipeline_v11.py EXPORTS ==="
grep -n "class ADASPipeline" backend/perception/pipeline/video_pipeline_v11.py | head -1
grep -n "def process_video" backend/perception/pipeline/video_pipeline_v11.py | head -1

# 4. Check CUDA availability
echo ""
echo "=== [4] CUDA & GPU CHECK ==="
python3 << 'EOF'
import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU count: {torch.cuda.device_count()}")
    print(f"GPU name: {torch.cuda.get_device_name(0)}")
    print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
else:
    print("⚠️  CUDA NOT AVAILABLE - Will use CPU!")
EOF

# 5. Test imports with detailed error
echo ""
echo "=== [5] TESTING PYTHON IMPORTS (DETAILED) ==="
python3 << 'EOF'
import sys
import os

# Add to path
sys.path.insert(0, '/home/phonglv/BE-ADAS/backend')
os.chdir('/home/phonglv/BE-ADAS')

print("Python path:")
for p in sys.path[:3]:
    print(f"  - {p}")

print("\n--- Testing imports ---")

# Test 1: Module exists
try:
    import perception.pipeline.video_pipeline_v11 as vp
    print("✅ Module imported successfully")
    print(f"   Module file: {vp.__file__}")
except Exception as e:
    print(f"❌ Failed to import module: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Check what's in the module
print("\n--- Module contents ---")
print("Available in video_pipeline_v11:")
attrs = [x for x in dir(vp) if not x.startswith('_')]
for attr in attrs[:10]:  # Show first 10
    print(f"  - {attr}")

# Test 3: Import specific items
print("\n--- Testing specific imports ---")
try:
    from perception.pipeline.video_pipeline_v11 import ADASPipeline
    print("✅ ADASPipeline imported")
except Exception as e:
    print(f"❌ ADASPipeline import failed: {e}")

try:
    from perception.pipeline.video_pipeline_v11 import process_video
    print("✅ process_video imported")
except Exception as e:
    print(f"❌ process_video import failed: {e}")

try:
    from perception.pipeline.video_pipeline_v11 import VideoPipelineV11
    print("✅ VideoPipelineV11 imported (should be alias)")
except Exception as e:
    print(f"❌ VideoPipelineV11 import failed: {e}")
    print("   This suggests __init__.py is not exporting it correctly")

# Test 4: Via __init__.py
print("\n--- Testing via __init__.py ---")
try:
    from perception.pipeline import ADASPipeline, VideoPipelineV11, process_video
    print("✅ All imports via __init__.py successful")
    print(f"   ADASPipeline == VideoPipelineV11? {ADASPipeline is VideoPipelineV11}")
except Exception as e:
    print(f"❌ Import via __init__.py failed: {e}")
    import traceback
    traceback.print_exc()
EOF

# 6. Check models
echo ""
echo "=== [6] MODELS CHECK ==="
if [ -d "backend/models" ]; then
    echo "Models directory:"
    ls -lh backend/models/*.pt 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "❌ No .pt model files found!"
        echo "⚠️  Models MUST be downloaded for GPU inference"
    fi
else
    echo "❌ backend/models directory not found!"
fi

# 7. Check Celery worker status
echo ""
echo "=== [7] CELERY WORKER STATUS ==="
if pgrep -f "celery.*worker" > /dev/null; then
    echo "✅ Celery worker is running"
    echo "PIDs:"
    pgrep -f "celery.*worker"
else
    echo "❌ Celery worker is NOT running"
fi

# 8. Quick GPU usage check
echo ""
echo "=== [8] CURRENT GPU USAGE ==="
nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total --format=csv,noheader

echo ""
echo "=========================================="
echo "✅ DEBUG COMPLETE"
echo "=========================================="
