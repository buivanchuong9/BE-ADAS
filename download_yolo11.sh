#!/bin/bash
# Download YOLOv11 models

echo "🚀 Downloading YOLOv11 models..."

cd "$(dirname "$0")/ai_models/weights" || exit

# YOLOv11n - Nano (fastest, recommended for realtime)
echo "📥 Downloading YOLOv11n (Nano - 3.2M params)..."
wget -q --show-progress https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt || \
python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"

# YOLOv11s - Small (balanced)
echo "📥 Downloading YOLOv11s (Small - 9.4M params)..."
wget -q --show-progress https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt || \
python3 -c "from ultralytics import YOLO; YOLO('yolo11s.pt')"

# YOLOv11m - Medium (better accuracy)
echo "📥 Downloading YOLOv11m (Medium - 20.1M params)..."
wget -q --show-progress https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt || \
python3 -c "from ultralytics import YOLO; YOLO('yolo11m.pt')"

# YOLOv11n-seg for lane detection
echo "📥 Downloading YOLOv11n-seg (Segmentation)..."
wget -q --show-progress https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-seg.pt || \
python3 -c "from ultralytics import YOLO; YOLO('yolo11n-seg.pt')"

echo "✅ YOLOv11 models downloaded!"
echo ""
echo "Available models:"
ls -lh *.pt | grep yolo11

echo ""
echo "🎯 YOLOv11 improvements over v8:"
echo "  • 10-15% faster inference"
echo "  • 2-3% better mAP"
echo "  • Better small object detection"
echo "  • Improved occlusion handling"
echo "  • Enhanced tracking"
