# HƯỚNG DẪN SETUP SQL SERVER VỚI DOCKER

## 🐳 CÁCH 1: Dùng Docker (KHUYẾN NGHỊ - Dễ nhất)

### **Bước 1: Cài Docker Desktop**
- Windows: Download Docker Desktop từ docker.com
- Restart máy sau khi cài

### **Bước 2: Chạy SQL Server Container**
```bash
docker run -e "ACCEPT_EULA=1" -e "MSSQL_SA_PASSWORD=123456aA@$" -e "MSSQL_PID=Developer" -e "MSSQL_USER=SA" -p 1433:1433 -d --name=sql mcr.microsoft.com/azure-sql-edge
```

**Thông tin:**
- Container name: `sql`
- User: `SA`
- Password: `123456aA@$`
- Port: `1433`
- Image: Azure SQL Edge (nhẹ hơn SQL Server)

### **Bước 3: Kiểm tra Container đang chạy**
```bash
docker ps
```

Kết quả sẽ thấy container `sql` đang UP.

### **Bước 4: Import Database Schema**
```bash
# Copy file SQL vào container
docker cp database_schema.sql sql:/tmp/schema.sql

# Chạy SQL script
docker exec -it sql /opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P "123456aA@$" -i /tmp/schema.sql
```

**Hoặc dùng Azure Data Studio / DBeaver:**
- Host: `localhost`
- Port: `1433`
- User: `SA`
- Password: `123456aA@$`
- Mở file `database_schema.sql` và Execute

### **Bước 5: Cấu hình Backend**

✅ **File `.env.production` đã được config sẵn:**
```env
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=SA
DB_PASSWORD=123456aA@$
```

**Chỉ cần copy:**
```bash
# Windows
copy .env.production backend\.env

# macOS/Linux
cp .env.production backend/.env
```

### **Bước 6: Chạy Backend**
```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
python run.py --production
```

---

## 🎯 LỆNH DOCKER HỮU ÍCH

### **Dừng SQL Server**
```bash
docker stop sql
```

### **Khởi động lại**
```bash
docker start sql
```

### **Xem logs**
```bash
docker logs sql
```

### **Vào SQL Server shell**
```bash
docker exec -it sql /opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P "123456aA@$"
```

### **Xóa container (reset database)**
```bash
docker stop sql
docker rm sql
# Sau đó chạy lại docker run...
```

### **Backup Database**
```bash
# Export to file
docker exec -it sql /opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P "123456aA@$" -Q "BACKUP DATABASE adas_production TO DISK='/tmp/backup.bak'"

# Copy backup file ra ngoài
docker cp sql:/tmp/backup.bak ./adas_backup.bak
```

---

## 📊 TEST CONNECTION

### **Test từ Backend**
```bash
cd backend
python -c "from app.db.session import engine; print('✅ Connected!' if engine else '❌ Failed')"
```

### **Test API**
```bash
# Start backend
python run.py --production

# Test health
curl http://localhost:52000/health

# Test login
curl -X POST http://localhost:52000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin123!@#"}'
```

---

## 🔧 TROUBLESHOOTING

### **Lỗi: "docker: command not found"**
→ Cài Docker Desktop và restart terminal

### **Lỗi: "Port 1433 already in use"**
```bash
# Tìm process đang dùng port 1433
# Windows
netstat -ano | findstr :1433
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :1433
kill -9 <PID>
```

### **Lỗi: "Login failed for user 'SA'"**
→ Kiểm tra password trong docker run command và .env phải giống nhau

### **Lỗi: "Cannot connect to Docker daemon"**
→ Mở Docker Desktop và đợi nó khởi động xong

---

## ⚡ QUICK START SCRIPT

**Tạo file `start_with_docker.sh` (macOS/Linux):**
```bash
#!/bin/bash

# Start SQL Server container
if ! docker ps | grep -q sql; then
    echo "Starting SQL Server container..."
    docker start sql || docker run -e "ACCEPT_EULA=1" -e "MSSQL_SA_PASSWORD=123456aA@$" -e "MSSQL_PID=Developer" -e "MSSQL_USER=SA" -p 1433:1433 -d --name=sql mcr.microsoft.com/azure-sql-edge
    sleep 10
fi

# Copy .env
cp .env.production backend/.env

# Start backend
source venv/bin/activate
python run.py --production
```

**Tạo file `start_with_docker.bat` (Windows):**
```batch
@echo off

REM Start SQL Server container
docker ps | findstr sql >nul
if errorlevel 1 (
    echo Starting SQL Server container...
    docker start sql || docker run -e "ACCEPT_EULA=1" -e "MSSQL_SA_PASSWORD=123456aA@$" -e "MSSQL_PID=Developer" -e "MSSQL_USER=SA" -p 1433:1433 -d --name=sql mcr.microsoft.com/azure-sql-edge
    timeout /t 10
)

REM Copy .env
copy /Y .env.production backend\.env

REM Start backend
call venv\Scripts\activate
python run.py --production
```

**Chạy:**
```bash
# Windows
start_with_docker.bat

# macOS/Linux
chmod +x start_with_docker.sh
./start_with_docker.sh
```

---

## ✅ ADVANTAGES OF DOCKER

1. ✅ **Không cần cài SQL Server** - Chạy trong container
2. ✅ **Nhẹ** - Azure SQL Edge chỉ ~300MB
3. ✅ **Dễ reset** - Xóa container và tạo mới
4. ✅ **Cross-platform** - Chạy trên Windows/macOS/Linux
5. ✅ **Isolated** - Không ảnh hưởng hệ thống
6. ✅ **Password đã config sẵn** - Không cần sửa .env

---

## 🎉 SUMMARY

```bash
# 1. Chạy SQL Server
docker run -e "ACCEPT_EULA=1" -e "MSSQL_SA_PASSWORD=123456aA@$" -e "MSSQL_PID=Developer" -e "MSSQL_USER=SA" -p 1433:1433 -d --name=sql mcr.microsoft.com/azure-sql-edge

# 2. Import database
docker cp database_schema.sql sql:/tmp/schema.sql
docker exec -it sql /opt/mssql-tools/bin/sqlcmd -S localhost -U SA -P "123456aA@$" -i /tmp/schema.sql

# 3. Copy config
copy .env.production backend\.env

# 4. Run backend
python run.py --production
```

**Done!** 🚀
