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
import shutil

# Thêm thư mục backend vào Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))


def check_environment_file(is_production=False):
    """Kiểm tra file .env đã tồn tại"""
    root_dir = Path(__file__).parent
    env_file = root_dir / ".env"
    
    if env_file.exists():
        print(f"✅ File .env đã sẵn sàng")
        return True
    else:
        print(f"❌ Không tìm thấy file .env")
        print("💡 Pull code từ GitHub để có file .env")
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
        import pyodbc
    except ImportError:
        missing.append("pyodbc")
    
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


def check_sql_server_connection():
    """Kiểm tra kết nối SQL Server"""
    print("\n🔌 Đang kiểm tra kết nối SQL Server...")
    try:
        from app.core.config import settings
        import pyodbc
        
        conn_str = (
            f"DRIVER={{{settings.DB_DRIVER}}};"
            f"SERVER={settings.DB_HOST},{settings.DB_PORT};"
            f"UID={settings.DB_USER};"
            f"PWD={settings.DB_PASSWORD};"
            "TrustServerCertificate=yes;"
        )
        
        conn = pyodbc.connect(conn_str, timeout=5)
        conn.close()
        print("✅ Kết nối SQL Server thành công")
        return True
    except Exception as e:
        print(f"❌ Không thể kết nối SQL Server: {e}")
        print("\n⚠️  Hãy đảm bảo SQL Server đang chạy:")
        print("  - Docker: docker ps | grep mssql")
        print("  - Native: services.msc → SQL Server")
        return False


def init_database():
    """Khởi tạo database và tables nếu chưa tồn tại"""
    print("\n🔧 Đang kiểm tra database...")
    
    try:
        from app.core.config import settings
        import pyodbc
        
        # Kết nối master database để tạo database
        conn_str_master = (
            f"DRIVER={{{settings.DB_DRIVER}}};"
            f"SERVER={settings.DB_HOST},{settings.DB_PORT};"
            f"DATABASE=master;"
            f"UID={settings.DB_USER};"
            f"PWD={settings.DB_PASSWORD};"
            "TrustServerCertificate=yes;"
        )
        
        conn = pyodbc.connect(conn_str_master, timeout=10)
        cursor = conn.cursor()
        
        # Kiểm tra database có tồn tại không
        cursor.execute(f"SELECT database_id FROM sys.databases WHERE name = '{settings.DB_NAME}'")
        db_exists = cursor.fetchone() is not None
        
        if not db_exists:
            print(f"📦 Tạo database '{settings.DB_NAME}'...")
            cursor.execute(f"CREATE DATABASE {settings.DB_NAME}")
            conn.commit()
            print(f"✅ Database '{settings.DB_NAME}' đã được tạo")
        else:
            print(f"✅ Database '{settings.DB_NAME}' đã tồn tại")
        
        cursor.close()
        conn.close()
        
        # Khởi tạo tables và seed data
        print("📋 Đang khởi tạo tables và seed data...")
        
        # Dùng subprocess để chạy init script
        import subprocess
        result = subprocess.run(
            [sys.executable, "backend/scripts/init_db.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Database tables đã sẵn sàng")
            
            # Kiểm tra và seed data
            print("📦 Kiểm tra initial data...")
            result_seed = subprocess.run(
                [sys.executable, "backend/scripts/seed_data.py"],
                capture_output=True,
                text=True
            )
            
            if result_seed.returncode == 0:
                print("✅ Initial data đã sẵn sàng")
            else:
                # Seed data có thể fail nếu data đã có - không sao
                print("ℹ️ Data có thể đã tồn tại")
        else:
            print(f"⚠️  Init tables: {result.stderr}")
        
    except Exception as e:
        print(f"⚠️  Lỗi khởi tạo database: {e}")
        print("ℹ️  Database có thể đã được khởi tạo sẵn, tiếp tục...")


def run_server(host="0.0.0.0", port=8000, reload=True):
    """Chạy Uvicorn server"""
    print(f"\n🚀 Đang khởi động ADAS Backend Server...")
    print(f"📡 Host: {host}")
    print(f"🔌 Port: {port}")
    print(f"🔄 Hot reload: {'Bật' if reload else 'Tắt'}")
    print(f"\n📖 API Documentation: http://{host}:{port}/docs")
    print(f"🏥 Health Check: http://{host}:{port}/health")
    print(f"🔌 WebSocket Alerts: ws://{host}:{port}/ws/alerts")
    print("\n⚠️  Nhấn Ctrl+C để dừng server\n")
    print("="*60)
    
    # Lưu thư mục hiện tại
    original_dir = os.getcwd()
    
    # Chuyển vào thư mục backend
    os.chdir(backend_dir)
    
    # Chạy uvicorn
    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
        "--proxy-headers",  # Trust X-Forwarded-* headers from reverse proxy
        "--forwarded-allow-ips", "*",  # Allow all proxy IPs
    ]
    
    if reload:
        cmd.append("--reload")
    
    try:
        # Chạy với shell=False để tránh shell expansion
        subprocess.run(cmd, shell=False)
    except KeyboardInterrupt:
        print("\n\n👋 Server đã dừng. Bye!")
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy server: {e}")
        print("Thử chạy thủ công:")
        print(f"  cd backend && uvicorn app.main:app --host {host} --port {port}")
    finally:
        # Quay lại thư mục gốc
        os.chdir(original_dir)


def main():
    parser = argparse.ArgumentParser(description="ADAS Backend Server")
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
    print("  🔧 Version: 2.0.0")
    print("  🏭 Mode:", "PRODUCTION" if args.production else "DEVELOPMENT")
    print("="*60)
    
    if args.skip_checks:
        print("\n⏩ Bỏ qua system checks (--skip-checks)")
    else:
        # Step 1: Kiểm tra .env file
        if not check_environment_file(is_production=args.production):
            sys.exit(1)
        
        # Step 2: Kiểm tra và cài đặt dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Step 3: Kiểm tra kết nối SQL Server
        sql_connected = check_sql_server_connection()
        if not sql_connected:
            print("\n❌ Không thể kết nối SQL Server. Vui lòng kiểm tra:")
            print("  1. SQL Server đang chạy")
            print("  2. Thông tin đăng nhập trong .env")
            print("  3. ODBC Driver 17 đã cài")
            sys.exit(1)
        
        # Step 4: Khởi tạo database (không hỏi nếu thành công)
        init_database()
    
    # Step 5: Chạy server
    run_server(
        host=args.host,
        port=args.port,
        reload=not args.no_reload
    )


if __name__ == "__main__":
    main()
