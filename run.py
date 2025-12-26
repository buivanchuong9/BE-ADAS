"""
ADAS BACKEND - MAIN ENTRY POINT
================================
Chạy file này để khởi động toàn bộ hệ thống.

Usage:
    python run.py              # Development mode (port 8000)
    python run.py --production # Production mode (port 52000)
    python run.py --port 8080  # Custom port
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# Thêm thư mục backend vào Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))


def check_dependencies():
    """Kiểm tra dependencies đã được cài đặt chưa"""
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        print("✅ Dependencies OK")
        return True
    except ImportError as e:
        print(f"❌ Thiếu dependencies: {e}")
        print("\nChạy lệnh sau để cài đặt:")
        print("  pip install -r requirements.txt")
        return False


def init_database():
    """Khởi tạo database nếu chưa tồn tại"""
    print("\n🔧 Đang kiểm tra database...")
    
    db_file = backend_dir / "adas.db"
    if db_file.exists():
        print("✅ Database đã tồn tại")
        return True
    
    print("📦 Khởi tạo database mới...")
    try:
        # Import và chạy init_db
        os.chdir(backend_dir)
        from app.db.session import init_db
        import asyncio
        asyncio.run(init_db())
        print("✅ Database khởi tạo thành công")
        return True
    except Exception as e:
        print(f"❌ Lỗi khởi tạo database: {e}")
        print("\nThử chạy thủ công:")
        print("  cd backend")
        print("  python scripts/init_db.py")
        return False


def run_server(host="0.0.0.0", port=8000, reload=True):
    """Chạy Uvicorn server"""
    print(f"\n🚀 Đang khởi động ADAS Backend...")
    print(f"📡 Host: {host}")
    print(f"🔌 Port: {port}")
    print(f"🔄 Hot reload: {'Bật' if reload else 'Tắt'}")
    print(f"\n📖 API Documentation: http://localhost:{port}/docs")
    print(f"🏥 Health Check: http://localhost:{port}/health")
    print("\n⚠️  Nhấn Ctrl+C để dừng server\n")
    
    # Chuyển vào thư mục backend
    os.chdir(backend_dir)
    
    # Chạy uvicorn
    cmd = [
        "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]
    
    if reload:
        cmd.append("--reload")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\n👋 Server đã dừng. Bye!")
    except FileNotFoundError:
        print("\n❌ Không tìm thấy 'uvicorn'")
        print("Cài đặt bằng: pip install uvicorn")


def main():
    parser = argparse.ArgumentParser(description="ADAS Backend Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    parser.add_argument("--production", action="store_true", help="Production mode (port 52000, no reload)")
    parser.add_argument("--no-reload", action="store_true", help="Disable hot reload")
    parser.add_argument("--skip-db-check", action="store_true", help="Skip database check")
    
    args = parser.parse_args()
    
    # Production mode
    if args.production:
        args.port = 52000
        args.no_reload = True
        print("🏭 PRODUCTION MODE")
    
    # Banner
    print("\n" + "="*60)
    print("  🚗 ADAS BACKEND - Advanced Driver Assistance System")
    print("  📍 Domain: https://adas-api.aiotlab.edu.vn:52000")
    print("  🔧 Version: 2.0.0")
    print("="*60)
    
    # Kiểm tra dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Khởi tạo database
    if not args.skip_db_check:
        if not init_database():
            response = input("\n⚠️  Tiếp tục chạy mà không có database? (y/N): ")
            if response.lower() != 'y':
                sys.exit(1)
    
    # Chạy server
    run_server(
        host=args.host,
        port=args.port,
        reload=not args.no_reload
    )


if __name__ == "__main__":
    main()
