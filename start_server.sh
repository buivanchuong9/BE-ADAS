#!/bin/bash
# Start ADAS Backend Server
# Production-grade startup script

echo "========================================="
echo "ADAS Backend - Starting..."
echo "========================================="

# Create required directories
mkdir -p logs
mkdir -p uploads/videos
mkdir -p ai_models/weights

# Check Python version
python3 --version

# Start server
echo "Starting FastAPI server on port 52000..."
python3 main.py
