#!/bin/bash
# Script khởi động server với config linh hoạt

echo "🚀 Starting ADAS Backend with SMART MODEL DETECTION"
echo "=================================================="
echo ""
echo "📌 Config options:"
echo "   AUTO_USE_LATEST_MODEL=true   → Tự động dùng model mới nhất"
echo "   MODEL_PRIORITY=best          → Dùng training/best_training.pt"
echo "   MODEL_PRIORITY=last          → Dùng training/last.pt"
echo "   MODEL_PRIORITY=latest        → Dùng file .pt mới nhất"
echo ""
echo "   YOLO_MODEL_PATH=path/to/model.pt  → Manual override"
echo "   DEFAULT_DEVICE=cuda          → Dùng GPU"
echo ""

# Thiết lập config mặc định
export AUTO_USE_LATEST_MODEL=true
export MODEL_PRIORITY=best
export DEFAULT_DEVICE=cuda

echo "✅ Current config:"
echo "   AUTO_USE_LATEST_MODEL = $AUTO_USE_LATEST_MODEL"
echo "   MODEL_PRIORITY = $MODEL_PRIORITY"
echo "   DEFAULT_DEVICE = $DEFAULT_DEVICE"
echo ""
echo "⏳ Starting server..."
echo ""

# Chạy server
python run.py
