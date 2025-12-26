# HƯỚNG DẪN CÀI ĐẶT SQL SERVER

## 🚀 CÁCH 1: Import Script SQL Sẵn (KHUYẾN NGHỊ)

### Bước 1: Cài SQL Server
- Download SQL Server 2019/2022 Express
- Hoặc dùng SQL Server có sẵn

### Bước 2: Mở SQL Server Management Studio (SSMS)
```
Server name: localhost
Authentication: Windows Authentication (hoặc SQL Server Authentication)
```

### Bước 3: Import Database
```sql
-- Cách 1: Mở file database_schema.sql trong SSMS
-- File -> Open -> File -> Chọn database_schema.sql
-- Nhấn Execute (F5)

-- Cách 2: Dùng sqlcmd
sqlcmd -S localhost -i database_schema.sql
```

### Bước 4: Kiểm tra
```sql
USE adas_production;
SELECT * FROM users;
-- Sẽ thấy admin user đã được tạo
```

### Bước 5: Cấu hình .env
```env
# backend/.env
DATABASE_URL=mssql+pyodbc://sa:YourPassword@localhost/adas_production?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=sa
DB_PASSWORD=YourPassword
ENVIRONMENT=production
```

### Bước 6: Chạy Backend
```bash
cd BE-ADAS
python run.py --production
```

---

## 🔧 CÁCH 2: Development với SQLite (KHÔNG CẦN SQL SERVER)

### Chỉ cần:
```env
# backend/.env
DATABASE_URL=sqlite:///./adas.db
ENVIRONMENT=development
```

### Chạy:
```bash
python run.py
```

Database sẽ tự động tạo file `backend/adas.db`

---

## 📊 THÔNG TIN DATABASE

### Tables đã tạo:
1. ✅ **users** - Người dùng (admin, operator, viewer, driver)
2. ✅ **vehicles** - Xe (biển số, loại xe, chủ sở hữu)
3. ✅ **trips** - Chuyến đi (thời gian, khoảng cách, tốc độ)
4. ✅ **video_jobs** - Jobs xử lý video (pending, processing, completed)
5. ✅ **safety_events** - Sự kiện an toàn (FCW, LDW, DMS)
6. ✅ **driver_states** - Trạng thái tài xế (drowsy detection)
7. ✅ **traffic_signs** - Biển báo (speed limits, violations)
8. ✅ **alerts** - Cảnh báo real-time
9. ✅ **model_versions** - Phiên bản AI models

### Default Admin Account:
```
Username: admin
Password: Admin123!@#
Email: admin@adas.vn
Role: admin
```

### Sample Vehicle:
```
License Plate: 29A-12345
Type: car
Model: Toyota Camry 2023
```

---

## ✅ TEST DATABASE

### Test 1: Login API
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "Admin123!@#"
  }'
```

### Test 2: Get Users
```bash
curl -X GET http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test 3: Get Vehicles
```bash
curl -X GET http://localhost:8000/api/v1/vehicles
```

---

## 🔒 BẢO MẬT

### Đổi Admin Password:
```sql
USE adas_production;

UPDATE users 
SET hashed_password = '$2b$12$NEW_HASH_HERE'
WHERE username = 'admin';
```

### Tạo User Mới:
```sql
INSERT INTO users (username, email, hashed_password, full_name, role, is_active)
VALUES ('operator1', 'operator@adas.vn', '$2b$12$...', 'Operator User', 'operator', 1);
```

---

## 🐛 TROUBLESHOOTING

### Lỗi: "Cannot connect to SQL Server"
```bash
# Kiểm tra SQL Server đang chạy
# Windows Services -> SQL Server (MSSQLSERVER) -> Start
```

### Lỗi: "Login failed for user 'sa'"
- Bật SQL Server Authentication
- SQL Server Configuration Manager -> Enable SQL Server Authentication

### Lỗi: "Driver not found"
```bash
# Cài ODBC Driver 18 for SQL Server
# Download từ Microsoft
```

---

## 📝 LƯU Ý

1. ✅ File `database_schema.sql` đã có SẴN tất cả
2. ✅ Không cần chạy Python script để tạo database
3. ✅ Chỉ cần import 1 lần
4. ✅ Development dùng SQLite (không cần SQL Server)
5. ✅ Production dùng SQL Server (import script)
