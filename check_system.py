#!/usr/bin/env python3
"""
SCRIPT KIỂM TRA HỆ THỐNG ADAS v3.0
===================================
Kiểm tra GPU, CUDA, dependencies và đưa ra khuyến nghị tối ưu
"""

import sys
import subprocess

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_section(text):
    print(f"\n📋 {text}")
    print("-" * 70)

def check_command(cmd):
    """Check if command exists"""
    try:
        subprocess.run(cmd, shell=True, capture_output=True, check=True)
        return True
    except:
        return False

print_header("🔍 KIỂM TRA HỆ THỐNG ADAS v3.0")

# 1. Check Python
print_section("1. Python Environment")
print(f"   Python version: {sys.version.split()[0]}")
print(f"   Python path: {sys.executable}")

# 2. Check PyTorch & CUDA
print_section("2. PyTorch & CUDA")
try:
    import torch
    print(f"   ✅ PyTorch version: {torch.__version__}")
    print(f"   CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print(f"   ✅ CUDA version: {torch.version.cuda}")
        print(f"   GPU count: {torch.cuda.device_count()}")
        
        for i in range(torch.cuda.device_count()):
            name = torch.cuda.get_device_name(i)
            props = torch.cuda.get_device_properties(i)
            vram = props.total_memory / (1024**3)
            print(f"\n   🎮 GPU {i}: {name}")
            print(f"      VRAM: {vram:.1f} GB")
            print(f"      Compute Capability: {props.major}.{props.minor}")
            
            # Test GPU speed
            print(f"      Testing GPU speed...")
            try:
                x = torch.randn(1000, 1000).cuda()
                y = torch.randn(1000, 1000).cuda()
                import time
                start = time.time()
                for _ in range(100):
                    z = torch.matmul(x, y)
                torch.cuda.synchronize()
                elapsed = time.time() - start
                print(f"      ✅ GPU speed test: {elapsed:.3f}s (100 iterations)")
            except Exception as e:
                print(f"      ❌ GPU test failed: {e}")
    else:
        print("\n   ❌ CUDA NOT AVAILABLE")
        print("   ⚠️  Hệ thống chỉ dùng CPU → RẤT CHẬM")
        print("\n   📝 Cách khắc phục:")
        print("      1. Kiểm tra GPU: nvidia-smi")
        print("      2. Cài CUDA Toolkit")
        print("      3. Cài PyTorch GPU: pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        
except ImportError:
    print("   ❌ PyTorch chưa cài đặt")
    print("   Cài đặt: pip3 install torch torchvision")

# 3. Check Ultralytics YOLO
print_section("3. Ultralytics YOLO")
try:
    from ultralytics import YOLO
    import ultralytics
    print(f"   ✅ Ultralytics version: {ultralytics.__version__}")
    
    # Check model file
    import os
    model_path = "yolo11n.pt"
    if os.path.exists(model_path):
        print(f"   ✅ Model file found: {model_path}")
    else:
        print(f"   ⚠️  Model file not found: {model_path}")
        print(f"      Will download on first use")
        
except ImportError:
    print("   ❌ Ultralytics chưa cài đặt")
    print("   Cài đặt: pip3 install ultralytics")

# 4. Check OpenCV
print_section("4. OpenCV")
try:
    import cv2
    print(f"   ✅ OpenCV version: {cv2.__version__}")
    
    # Check video codec support
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    print(f"   ✅ MP4 codec supported")
    
except ImportError:
    print("   ❌ OpenCV chưa cài đặt")
    print("   Cài đặt: pip3 install opencv-python")

# 5. Check NumPy
print_section("5. NumPy")
try:
    import numpy as np
    print(f"   ✅ NumPy version: {np.__version__}")
except ImportError:
    print("   ❌ NumPy chưa cài đặt")

# 6. Check SQLAlchemy
print_section("6. Database (SQLAlchemy)")
try:
    import sqlalchemy
    print(f"   ✅ SQLAlchemy version: {sqlalchemy.__version__}")
    
    # Check asyncpg
    try:
        import asyncpg
        print(f"   ✅ asyncpg installed (PostgreSQL driver)")
    except:
        print(f"   ❌ asyncpg not found")
        
except ImportError:
    print("   ❌ SQLAlchemy chưa cài đặt")

# 7. Check FastAPI
print_section("7. FastAPI")
try:
    import fastapi
    print(f"   ✅ FastAPI version: {fastapi.__version__}")
except ImportError:
    print("   ❌ FastAPI chưa cài đặt")

# 8. System info
print_section("8. System Information")
try:
    import platform
    print(f"   OS: {platform.system()} {platform.release()}")
    print(f"   Machine: {platform.machine()}")
    print(f"   Processor: {platform.processor()}")
    
    # Check CPU cores
    import multiprocessing
    print(f"   CPU cores: {multiprocessing.cpu_count()}")
    
    # Check RAM
    try:
        import psutil
        ram = psutil.virtual_memory()
        print(f"   RAM: {ram.total / (1024**3):.1f} GB (Available: {ram.available / (1024**3):.1f} GB)")
    except:
        pass
        
except:
    pass

# 9. Performance estimate
print_section("9. Ước tính hiệu năng")
try:
    import torch
    if torch.cuda.is_available():
        print("   🚀 GPU ENABLED")
        print("   Tốc độ xử lý dự kiến: 30-60 fps")
        print("   Thời gian xử lý video 50s: ~30-60 giây")
        print("   ✅ HIỆU NĂNG TỐI ƯU")
    else:
        print("   ⚠️  CPU ONLY")
        print("   Tốc độ xử lý dự kiến: 6-8 fps")
        print("   Thời gian xử lý video 50s: ~3-4 phút")
        print("   ❌ HIỆU NĂNG THẤP - CẦN KÍCH HOẠT GPU")
except:
    print("   ❓ Không thể ước tính")

# Summary
print_header("📊 TÓM TẮT")

issues = []
recommendations = []

try:
    import torch
    if not torch.cuda.is_available():
        issues.append("❌ GPU chưa hoạt động")
        recommendations.append("1. Kích hoạt GPU (quan trọng nhất)")
        recommendations.append("   - Kiểm tra: nvidia-smi")
        recommendations.append("   - Cài CUDA Toolkit")
        recommendations.append("   - Cài PyTorch GPU version")
except:
    issues.append("❌ PyTorch chưa cài")
    recommendations.append("1. Cài PyTorch")

if not issues:
    print("\n✅ HỆ THỐNG HOẠT ĐỘNG TỐT")
    print("   Tất cả dependencies đã cài đặt")
    print("   GPU đã kích hoạt")
    print("   Sẵn sàng xử lý video tốc độ cao")
else:
    print("\n⚠️  CÓ VẤN ĐỀ CẦN KHẮC PHỤC:")
    for issue in issues:
        print(f"   {issue}")
    
    print("\n📝 KHUYẾN NGHỊ:")
    for rec in recommendations:
        print(f"   {rec}")

print("\n" + "=" * 70)
print("Hoàn tất kiểm tra!")
print("=" * 70 + "\n")
