# DEPLOYMENT CHECKLIST - UBUNTU SERVER

## ✅ Đã Sẵn Sàng (Local)

- [x] Code refactored với Hybrid ID system
- [x] Supabase config đã set (SUPABASE_ANON_KEY)
- [x] Dependencies updated (supabase>=2.0.0)
- [x] API endpoints tested local
- [x] Test files cleaned up

## 🚀 Cần Làm Trên Ubuntu Server

### 1. Git Pull Code Mới

```bash
cd /path/to/backend-python
git pull origin main
```

### 2. Install Dependencies Mới

```bash
# Activate venv nếu có
source venv/bin/activate  # hoặc .venv/bin/activate

# Install supabase
pip install supabase>=2.0.0

# Hoặc install tất cả
pip install -r requirements.txt
```

### 3. Run Database Migration ⚠️ QUAN TRỌNG

```bash
# Connect vào PostgreSQL
sudo -u postgres psql -d adas_db

# Hoặc với user của bạn
psql -h localhost -U adas_user -d adas_db
```

Chạy các lệnh SQL:

```sql
-- 1. Add auth_id column
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_id UUID UNIQUE;

-- 2. Make hashed_password nullable
ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;

-- 3. Create index
CREATE INDEX IF NOT EXISTS idx_users_auth_id ON users(auth_id);

-- 4. Verify
\d users
```

### 4. Restart Server

```bash
# Stop server hiện tại
sudo systemctl stop adas-backend
# hoặc
pkill -f "uvicorn"

# Start lại
python run.py
# hoặc dùng systemd
sudo systemctl start adas-backend
```

### 5. Verify API Hoạt Động

```bash
# Test health
curl http://localhost:8000/health

# Test auth status
curl http://localhost:8000/api/auth/status

# Test auth/me (should return 403)
curl -i http://localhost:8000/api/auth/me
```

## 🔍 Checklist Verification

- [ ] `pip list | grep supabase` → hiển thị supabase 2.x.x
- [ ] Database có column `auth_id` trong table `users`
- [ ] Server restart thành công, không có error
- [ ] `/health` endpoint return 200
- [ ] `/api/auth/status` return `{authenticated: false}`
- [ ] `/api/auth/me` without token return 403

## ⚠️ Lưu Ý Quan Trọng

### SUPABASE_ANON_KEY
Đã hardcode trong `config.py`:
```python
SUPABASE_ANON_KEY: str = "eyJhbGc..."
```

✅ **Không cần set environment variable thêm**

### Port Configuration
- run.py mặc định chạy port **8000**
- Nginx/Cloudflare proxy từ 52000 → 8000

### Database Trigger (Optional - Làm Sau)
Để auto-sync users từ Supabase Auth, cần setup trigger trong Supabase Dashboard:
1. Dashboard → Database → Triggers
2. Table: `auth.users`
3. Event: `INSERT`
4. Function: `handle_new_user()`

## 🎯 Test End-to-End

### Từ Frontend:
1. Login Supabase → get JWT token
2. Call API:
```javascript
fetch('https://adas-api.aiotlab.edu.vn/api/auth/me', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```
3. Verify response có `id` (integer) và `auth_id` (UUID)

## ❓ Troubleshooting

### Lỗi "supabase-py not installed"
```bash
pip install supabase>=2.0.0
```

### Lỗi "Database unavailable"
→ Chưa chạy migration, column `auth_id` chưa tồn tại

### Lỗi 401 "User not synced"
→ User tồn tại trong Supabase Auth nhưng chưa có trong database
→ Cần tạo user manually trong `users` table hoặc setup trigger

## ✅ Summary

**Bước Tối Thiểu:**
1. Git pull
2. `pip install supabase>=2.0.0`
3. Run migration SQL (add `auth_id` column)
4. Restart server
5. Test API

**Thời gian:** ~5 phút

**Sẵn sàng deploy:** ✅ YES!
