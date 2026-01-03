"""
ADAS BACKEND v3.0 - MAIN ENTRY POINT (PostgreSQL)
==================================================
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


def check_environment_file():
    """Kiểm tra file .env đã tồn tại"""
    root_dir = Path(__file__).parent
    env_file = root_dir / ".env"
    
    if env_file.exists():
        print(f"✅ File .env đã sẵn sàng")
        return True
    else:
        print(f"❌ Không tìm thấy file .env")
        print("💡 Tạo file .env với nội dung:")
        print("""
PG_HOST=localhost
PG_PORT=5432
PG_NAME=adas_db
PG_USER=adas_user
PG_PASSWORD=adas123
API_BASE_URL=https://adas-api.aiotlab.edu.vn
DEBUG=False
ENVIRONMENT=production
        """)
        return False


def check_dependencies():
    """Kiểm tra dependencies đã được cài đặt chưa"""
    print("\n🔍 Đang kiểm tra dependencies...")
    missing = []
    
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    
    try:
        import uvicorn
    except ImportError:
        missing.append("uvicorn")
    
    try:
        import sqlalchemy
    except ImportError:
        missing.append("sqlalchemy")
    
    try:
        import asyncpg
    except ImportError:
        missing.append("asyncpg")
    
    if missing:
        print(f"❌ Thiếu dependencies: {', '.join(missing)}")
        print("\n📦 Đang tự động cài đặt dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt", "-q"])
            print("✅ Đã cài đặt dependencies thành công")
            return True
        except Exception as e:
            print(f"❌ Lỗi khi cài đặt: {e}")
            print("\nChạy thủ công:")
            print("  pip install -r backend/requirements.txt")
            return False
    else:
        print("✅ Dependencies OK")
        return True


def check_postgresql_connection():
    """Kiểm tra kết nối PostgreSQL"""
    print("\n🔌 Đang kiểm tra kết nối PostgreSQL...")
    try:
        from app.core.config import settings
        import asyncpg
        import asyncio
        
        async def test_connection():
            try:
                conn = await asyncpg.connect(
                    host=settings.PG_HOST,
                    port=settings.PG_PORT,
                    database=settings.PG_NAME,
                    user=settings.PG_USER,
                    password=settings.PG_PASSWORD,
                    timeout=5
                )
                await conn.close()
                return True
            except Exception as e:
                raise e
        
        asyncio.run(test_connection())
        print("✅ Kết nối PostgreSQL thành công")
        return True
    except Exception as e:
        print(f"❌ Không thể kết nối PostgreSQL: {e}")
        print("\n⚠️  Hãy đảm bảo PostgreSQL đang chạy:")
        print("  - Ubuntu: sudo systemctl status postgresql")
        print("  - macOS: brew services list | grep postgresql")
        print("\n� Kiểm tra:")
        print("  1. PostgreSQL đang chạy")
        print("  2. Database 'adas_db' đã tồn tại")
        print("  3. Thông tin đăng nhập trong .env đúng")
        return False


def run_server(host="0.0.0.0", port=8000, reload=True):
    """Chạy Uvicorn server"""
    print(f"\n🚀 Đang khởi động ADAS Backend Server v3.0...")
    print(f"📡 Host: {host}")
    print(f"🔌 Port: {port}")
    print(f"🔄 Hot reload: {'Bật' if reload else 'Tắt'}")
    print(f"\n📖 API Documentation: http://{host}:{port}/docs")
    print(f"🏥 Health Check: http://{host}:{port}/health")
    print(f"🔌 WebSocket Alerts: ws://{host}:{port}/ws/alerts")
    print("\n⚠️  Nhấn Ctrl+C để dừng server\n")
    print("="*60)
    
    backend_path = Path(backend_dir).resolve()
    
    cmd = [
        str(sys.executable),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        str(host),
        "--port",
        str(port),
        "--proxy-headers",
    ]
    
    if reload:
        cmd.append("--reload")
    
    print("\n🔧 Uvicorn command:")
    print(f"   Working directory: {backend_path}")
    print(f"   Command: {' '.join(cmd)}")
    print("="*60 + "\n")
    
    try:
        subprocess.run(
            cmd,
            cwd=str(backend_path),
            shell=False,
            check=False
        )
    except KeyboardInterrupt:
        print("\n\n👋 Server đã dừng. Bye!")
    except FileNotFoundError as e:
        print(f"\n❌ Không tìm thấy Python hoặc uvicorn: {e}")
        print("\n💡 Kiểm tra:")
        print(f"  1. Python: {sys.executable}")
        print(f"  2. Uvicorn: pip show uvicorn")
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy server: {e}")
        print("\n💡 Thử chạy thủ công:")
        print(f"  cd backend && uvicorn app.main:app --host {host} --port {port} --proxy-headers")


def main():
    parser = argparse.ArgumentParser(description="ADAS Backend Server v3.0")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    parser.add_argument("--production", action="store_true", help="Production mode (port 52000, no reload)")
    parser.add_argument("--no-reload", action="store_true", help="Disable hot reload")
    parser.add_argument("--skip-checks", action="store_true", help="Skip all system checks")
    
    args = parser.parse_args()
    
    # Production mode
    if args.production:
        args.port = 52000
        args.no_reload = True
    
    # Banner
    print("\n" + "="*60)
    print("  🚗 ADAS BACKEND - Advanced Driver Assistance System")
    print("  📍 Domain: https://adas-api.aiotlab.edu.vn:52000")
    print("  🔧 Version: 3.0.0 (PostgreSQL)")
    print("  🏭 Mode:", "PRODUCTION" if args.production else "DEVELOPMENT")
    print("="*60)
    
    if args.skip_checks:
        print("\n⏩ Bỏ qua system checks (--skip-checks)")
    else:
        # Step 1: Kiểm tra .env file
        if not check_environment_file():
            sys.exit(1)
        
        # Step 2: Kiểm tra và cài đặt dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Step 3: Kiểm tra kết nối PostgreSQL
        if not check_postgresql_connection():
            print("\n⚠️  Tiếp tục khởi động server (có thể lỗi nếu DB không sẵn sàng)...")
    
    # Step 4: Chạy server
    run_server(
        host=args.host,
        port=args.port,
        reload=not args.no_reload
    )


if __name__ == "__main__":
    main()
