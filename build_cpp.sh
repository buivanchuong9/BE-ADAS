#!/bin/bash
# Build script for C++ modules
# Usage: ./build_cpp.sh

set -e  # Exit on error

echo "======================================"
echo " Building ADAS C++ Modules"
echo "======================================"

# Check dependencies
echo "Checking dependencies..."

if ! command -v cmake &> /dev/null; then
    echo "❌ ERROR: CMake not found. Install: brew install cmake (macOS) or apt install cmake (Ubuntu)"
    exit 1
fi

if ! command -v g++ &> /dev/null; then
    echo "❌ ERROR: g++ not found. Install build tools."
    exit 1
fi

if ! pkg-config --exists opencv4; then
    echo "❌ ERROR: OpenCV not found. Install: brew install opencv (macOS) or apt install libopencv-dev (Ubuntu)"
    exit 1
fi

if ! python3 -c "import pybind11" 2>/dev/null; then
    echo "❌ ERROR: pybind11 not found. Install: pip install pybind11"
    exit 1
fi

# Check FFmpeg libraries (for hlsenc module)
if ! pkg-config --exists libavcodec libavformat libavutil libswscale; then
    echo "❌ ERROR: FFmpeg libraries not found."
    echo "   Install: brew install ffmpeg (macOS) or apt install libavcodec-dev libavformat-dev libavutil-dev libswscale-dev (Ubuntu)"
    exit 1
fi

echo "✅ All dependencies found"

# Create build directory
mkdir -p build
cd build

# Configure
echo ""
echo "Configuring CMake..."
cmake ../cpp_modules \
    -DCMAKE_BUILD_TYPE=Release \
    -DPYTHON_EXECUTABLE=$(which python3)

# Build
echo ""
echo "Building..."
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)

# Install to build/lib
echo ""
echo "Installing modules to build/lib..."
make install

# Verify
echo ""
echo "======================================"
echo " Build Complete!"
echo "======================================"
echo ""
echo "Modules built:"
ls -lh lib/*.so 2>/dev/null || ls -lh lib/*.dylib 2>/dev/null || echo "⚠️  No .so/.dylib files found"

echo ""
echo "Test the module:"
echo "  python3 -c 'import sys; sys.path.insert(0, \"build/lib\"); import renderer; print(renderer.__version__)'"
