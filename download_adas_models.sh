#!/bin/bash
# Download YOLO11 Model Weights
# Tự động tải các model weights cần thiết cho ADAS

set -e  # Exit on error

echo "=============================================="
echo "🚀 ADAS Model Weights Downloader"
echo "=============================================="

# Create weights directory
WEIGHTS_DIR="ai_models/weights"
mkdir -p "$WEIGHTS_DIR"

cd "$WEIGHTS_DIR"

echo ""
echo "📁 Weights directory: $(pwd)"
echo ""

# YOLO11 Models
declare -A MODELS=(
    ["yolo11n.pt"]="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
    ["yolo11s.pt"]="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt"
    ["yolo11m.pt"]="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt"
)

# Download function
download_model() {
    local model_name=$1
    local model_url=$2
    
    if [ -f "$model_name" ]; then
        echo "✅ $model_name already exists"
    else
        echo "📥 Downloading $model_name..."
        
        if command -v wget &> /dev/null; then
            wget -q --show-progress "$model_url" -O "$model_name"
        elif command -v curl &> /dev/null; then
            curl -L --progress-bar "$model_url" -o "$model_name"
        else
            echo "❌ Error: wget or curl not found"
            echo "   Please install wget or curl to download models"
            exit 1
        fi
        
        if [ -f "$model_name" ]; then
            echo "✅ Downloaded $model_name"
        else
            echo "❌ Failed to download $model_name"
            exit 1
        fi
    fi
}

# Ask user which models to download
echo "Select models to download:"
echo "1) yolo11n.pt (Nano - Fastest, 6MB)"
echo "2) yolo11s.pt (Small - Balanced, 22MB)"
echo "3) yolo11m.pt (Medium - Accurate, 50MB)"
echo "4) All models (78MB total)"
echo "5) Skip download (use existing)"
echo ""
read -p "Enter choice [1-5] (default: 1): " choice
choice=${choice:-1}

case $choice in
    1)
        echo ""
        echo "📦 Downloading YOLO11 Nano..."
        download_model "yolo11n.pt" "${MODELS[yolo11n.pt]}"
        ;;
    2)
        echo ""
        echo "📦 Downloading YOLO11 Small..."
        download_model "yolo11s.pt" "${MODELS[yolo11s.pt]}"
        ;;
    3)
        echo ""
        echo "📦 Downloading YOLO11 Medium..."
        download_model "yolo11m.pt" "${MODELS[yolo11m.pt]}"
        ;;
    4)
        echo ""
        echo "📦 Downloading all models..."
        for model in "${!MODELS[@]}"; do
            download_model "$model" "${MODELS[$model]}"
        done
        ;;
    5)
        echo ""
        echo "⏭️  Skipping model download"
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "=============================================="
echo "📊 Downloaded Models:"
echo "=============================================="
ls -lh *.pt 2>/dev/null || echo "No models found"

echo ""
echo "=============================================="
echo "✅ Setup complete!"
echo "=============================================="
echo ""
echo "You can now run ADAS:"
echo "  python adas_main.py --source 0"
echo ""
