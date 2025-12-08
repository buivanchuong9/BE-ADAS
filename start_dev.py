#!/usr/bin/env python3
"""
ADAS Backend - Development Server Launcher
Automatically activates venv and runs the backend server
"""

import os
import sys
import subprocess
from pathlib import Path

# Get the backend directory
BACKEND_DIR = Path(__file__).parent.absolute()
VENV_DIR = BACKEND_DIR / "venv"
MAIN_PY = BACKEND_DIR / "main.py"

def check_venv():
    """Check if venv exists"""
    if not VENV_DIR.exists():
        print("❌ Virtual environment not found!")
        print(f"Create it with: python3 -m venv {VENV_DIR}")
        sys.exit(1)

def get_python_executable():
    """Get the venv Python executable"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    else:
        return VENV_DIR / "bin" / "python"

def main():
    """Run the backend server"""
    print("=" * 60)
    print("🚗 Starting ADAS Backend Server...")
    print("=" * 60)
    
    # Check venv
    check_venv()
    
    # Get Python executable
    python_exe = get_python_executable()
    
    if not python_exe.exists():
        print(f"❌ Python executable not found: {python_exe}")
        sys.exit(1)
    
    print(f"✓ Using Python: {python_exe}")
    print(f"✓ Running: {MAIN_PY}")
    print()
    
    # Change to backend directory
    os.chdir(BACKEND_DIR)
    
    # Run main.py with venv Python
    try:
        subprocess.run([str(python_exe), str(MAIN_PY)], check=True)
    except KeyboardInterrupt:
        print("\n\n🛑 Backend server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Backend exited with error code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
