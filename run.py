#!/usr/bin/env python3
"""
ADAS Backend - Universal Startup Script
Chạy được trên cả Windows và macOS/Linux
Usage: python run.py
"""

import os
import sys
import subprocess
import platform
import time
import signal

# Colors for terminal output
class Colors:
    if platform.system() == 'Windows':
        # Windows console colors
        BLUE = ''
        GREEN = ''
        YELLOW = ''
        RED = ''
        NC = ''
    else:
        # Unix/macOS ANSI colors
        BLUE = '\033[0;34m'
        GREEN = '\033[0;32m'
        YELLOW = '\033[1;33m'
        RED = '\033[0;31m'
        NC = '\033[0m'

def print_header():
    print(f"{Colors.BLUE}")
    print("=" * 60)
    print("🚀 ADAS Backend Server - Universal Startup")
    print(f"   Platform: {platform.system()} {platform.release()}")
    print("=" * 60)
    print(f"{Colors.NC}")

def check_python():
    print(f"{Colors.YELLOW}[1/4] Checking Python...{Colors.NC}")
    version = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    
    if major < 3 or (major == 3 and minor < 8):
        print(f"{Colors.RED}❌ Python 3.8+ required. Found: {version}{Colors.NC}")
        sys.exit(1)
    
    print(f"{Colors.GREEN}✅ Python {version}{Colors.NC}")

def install_dependencies():
    print(f"{Colors.YELLOW}[2/4] Checking dependencies...{Colors.NC}")
    
    try:
        import fastapi
        print(f"{Colors.GREEN}✅ Dependencies OK{Colors.NC}")
    except ImportError:
        print(f"{Colors.YELLOW}Installing requirements...{Colors.NC}")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "-r", "requirements.txt", "--quiet"
            ])
            print(f"{Colors.GREEN}✅ Dependencies installed{Colors.NC}")
        except subprocess.CalledProcessError:
            print(f"{Colors.RED}❌ Failed to install dependencies{Colors.NC}")
            sys.exit(1)

def kill_existing_server():
    print(f"{Colors.YELLOW}[3/4] Stopping old server (if any)...{Colors.NC}")
    
    if platform.system() == 'Windows':
        # Windows: Kill by port
        try:
            subprocess.run([
                'powershell', '-Command',
                "Get-Process -Name python* -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*main.py*' } | Stop-Process -Force"
            ], capture_output=True)
            
            # Also try to kill by port 8000
            subprocess.run([
                'powershell', '-Command',
                "(Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
            ], capture_output=True)
        except:
            pass
    else:
        # macOS/Linux: Kill by process and port
        try:
            subprocess.run(['pkill', '-9', '-f', 'python3 main.py'], 
                         capture_output=True, timeout=2)
            subprocess.run(['pkill', '-9', '-f', 'python3.*uvicorn'], 
                         capture_output=True, timeout=2)
            
            # Kill by port
            result = subprocess.run(['lsof', '-ti:8000'], 
                                  capture_output=True, text=True, timeout=2)
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], timeout=1)
                    except:
                        pass
        except:
            pass
    
    time.sleep(2)
    print(f"{Colors.GREEN}✅ Ready{Colors.NC}")

def start_server():
    print(f"{Colors.YELLOW}[4/4] Starting server...{Colors.NC}")
    print(f"{Colors.BLUE}")
    print("=" * 60)
    print("📊 API Docs: http://localhost:8000/docs")
    print("💚 Health: http://localhost:8000/health")
    print("🎯 Alerts: http://localhost:8000/api/alerts/latest")
    print("📦 Dataset: http://localhost:8000/api/dataset/stats")
    print("=" * 60)
    print(f"{Colors.NC}")
    print(f"{Colors.GREEN}Press Ctrl+C to stop{Colors.NC}\n")
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{Colors.YELLOW}Stopping server...{Colors.NC}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start server
    try:
        if platform.system() == 'Windows':
            # Windows: Use python directly
            subprocess.run([sys.executable, "main.py"])
        else:
            # macOS/Linux: Use python3
            subprocess.run([sys.executable, "main.py"])
    except KeyboardInterrupt:
        print(f"\n{Colors.GREEN}Server stopped{Colors.NC}")
    except Exception as e:
        print(f"{Colors.RED}❌ Error: {e}{Colors.NC}")
        sys.exit(1)

def main():
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print_header()
    check_python()
    install_dependencies()
    kill_existing_server()
    start_server()

if __name__ == "__main__":
    main()
