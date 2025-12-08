#!/usr/bin/env python3
"""
ADAS Backend - One-Command Setup & Run
Tự động cài thư viện và chạy server chỉ với 1 lệnh
Usage: python start.py
"""

import os
import sys
import subprocess
import platform

def main():
    print("\n" + "="*60)
    print("🚀 ADAS Backend - Automatic Setup & Start")
    print("="*60 + "\n")
    
    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Step 1: Upgrade pip (optional - skip if fails)
    print("[1/3] Checking pip...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "--upgrade", "pip", "--quiet", "--user"
        ], timeout=10)
        print("✅ pip ready\n")
    except:
        print("⚠️  pip check skipped (already managed by system)\n")
    
    # Step 2: Install all requirements
    print("[2/3] Installing all dependencies...")
    print("This may take a few minutes...\n")
    
    try:
        # Install from requirements.txt
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "-r", "requirements.txt"
        ])
        print("\n✅ All dependencies installed\n")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error installing dependencies: {e}")
        print("\nTrying to install critical packages individually...\n")
        
        # Critical packages
        critical = [
            "fastapi", "uvicorn[standard]", "sqlalchemy",
            "python-multipart", "opencv-python", "pillow",
            "numpy", "torch", "torchvision", "ultralytics",
            "pyttsx3"
        ]
        
        for pkg in critical:
            try:
                print(f"Installing {pkg}...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", pkg
                ])
            except:
                print(f"⚠️  Failed to install {pkg}, continuing...")
    
    # Step 3: Start server
    print("\n[3/3] Starting server...\n")
    print("="*60)
    print("📊 Server will be available at:")
    print("   http://localhost:8000/docs")
    print("="*60)
    print("\nPress Ctrl+C to stop\n")
    
    try:
        # Import and run server
        import run
        run.main()
    except ImportError:
        # Fallback: run main.py directly
        try:
            subprocess.run([sys.executable, "main.py"])
        except KeyboardInterrupt:
            print("\n\n✅ Server stopped")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✅ Setup cancelled")
        sys.exit(0)
