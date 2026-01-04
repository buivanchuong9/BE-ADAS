# HƯỚNG DẪN TÍCH HỢP FRONTEND - HYBRID ID SYSTEM

## 🎯 Mục Đích

Frontend chỉ cần gọi **1 API duy nhất** để lấy thông tin user với Integer ID (tương thích legacy) từ Supabase JWT token.

---

## 🚀 Cách Sử Dụng

### 1. **Đăng Nhập Qua Supabase (Frontend)**

```javascript
// Login với Supabase
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password123'
})

if (error) {
  console.error('Login failed:', error)
  return
}

// Lấy JWT token
const token = data.session.access_token
console.log('Token:', token)
```

### 2. **Gọi API Backend Để Lấy User Info**

```javascript
// Call backend API
const response = await fetch('https://adas-api.aiotlab.edu.vn/api/auth/me', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
})

const userData = await response.json()
console.log('User Data:', userData)
```

**Response:**
```json
{
  "success": true,
  "user": {
    "id": 123,                                          // ✅ Integer ID (dùng cho legacy)
    "auth_id": "550e8400-e29b-41d4-a716-446655440000",  // UUID từ Supabase
    "email": "user@example.com",
    "role": "admin"
  }
}
```

### 3. **Lưu Thông Tin User Vào State**

```javascript
// Lưu vào localStorage hoặc state management
localStorage.setItem('userId', userData.user.id)         // Integer ID
localStorage.setItem('authId', userData.user.auth_id)    // UUID
localStorage.setItem('userEmail', userData.user.email)
localStorage.setItem('userRole', userData.user.role)
```

---

## 📡 API Endpoints

### **GET /api/auth/me** ✅

Lấy thông tin user hiện tại (yêu cầu authentication).

**Headers:**
```
Authorization: Bearer <supabase_jwt_token>
```

**Response (Success - 200):**
```json
{
  "success": true,
  "user": {
    "id": 123,
    "auth_id": "uuid-here",
    "email": "user@example.com",
    "role": "admin"
  }
}
```

**Response (Error - 401):**
```json
{
  "detail": "Not authenticated"
}
```

---

### **GET /api/auth/status** ✅

Kiểm tra trạng thái đăng nhập (không yêu cầu authentication).

**Headers:** (Optional)
```
Authorization: Bearer <token>
```

**Response (Authenticated):**
```json
{
  "authenticated": true,
  "user": {
    "id": 123,
    "auth_id": "uuid",
    "email": "user@example.com",
    "role": "admin"
  }
}
```

**Response (Not Authenticated):**
```json
{
  "authenticated": false,
  "user": null
}
```

---

## 🔧 Cấu Hình Backend

### Production Domain
```
https://adas-api.aiotlab.edu.vn
```

### Local Development
```
http://localhost:8000
```

---

## ✅ Test Thử API

### Bước 1: Lấy Token Từ Supabase

Đăng nhập vào Supabase Dashboard hoặc dùng frontend để lấy token.

### Bước 2: Test API

```bash
# Test với token
curl -X GET "https://adas-api.aiotlab.edu.vn/api/auth/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

### Bước 3: Kiểm Tra Response

```json
{
  "success": true,
  "user": {
    "id": 123,           // ✅ Đây là ID integer cần dùng
    "auth_id": "...",
    "email": "...",
    "role": "..."
  }
}
```

---

## 🎨 Frontend Code Example (React)

```jsx
import { useEffect, useState } from 'react'
import { supabase } from './supabaseClient'

function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkUser()
  }, [])

  async function checkUser() {
    try {
      // Lấy session hiện tại
      const { data: { session } } = await supabase.auth.getSession()
      
      if (!session) {
        setLoading(false)
        return
      }

      // Gọi backend để lấy user info với integer ID
      const response = await fetch('https://adas-api.aiotlab.edu.vn/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${session.access_token}`
        }
      })

      const data = await response.json()
      
      if (data.success) {
        setUser(data.user)  // {id: 123, auth_id: "...", email: "...", role: "..."}
      }
    } catch (error) {
      console.error('Error:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div>Loading...</div>

  if (!user) return <div>Please login</div>

  return (
    <div>
      <h1>Welcome {user.email}</h1>
      <p>User ID: {user.id}</p>         {/* Integer ID */}
      <p>Auth ID: {user.auth_id}</p>    {/* UUID */}
      <p>Role: {user.role}</p>
    </div>
  )
}
```

---

## 🔒 Bảo Mật

### Token Expiration

JWT token từ Supabase có thời gian hết hạn. Frontend cần:

1. **Check token expiration** trước khi gọi API
2. **Refresh token** khi cần thiết
3. **Handle 401 errors** và redirect đến login

```javascript
// Refresh token khi hết hạn
supabase.auth.onAuthStateChange((event, session) => {
  if (event === 'TOKEN_REFRESHED') {
    console.log('Token refreshed')
    // Gọi lại API nếu cần
  }
})
```

---

## 🐛 Xử Lý Lỗi

| Lỗi | Nguyên Nhân | Giải Pháp |
|-----|-------------|-----------|
| 401 Unauthorized | Token không hợp lệ hoặc hết hạn | Refresh token hoặc đăng nhập lại |
| 403 Forbidden | Không có token trong header | Thêm Authorization header |
| 503 Service Unavailable | Database không khả dụng | Thử lại sau hoặc liên hệ admin |

---

## 📝 Tóm Tắt

### ✅ **Những Gì Frontend Cần Làm:**

1. Đăng nhập qua Supabase Auth → Lấy JWT token
2. Gọi `GET /api/auth/me` với token → Nhận integer ID
3. Dùng integer ID cho các API khác (videos, trips, etc.)

### ✅ **Những Gì Backend Đã Làm:**

1. Verify JWT signature (RS256)
2. Extract UUID từ token
3. Query database để lấy integer ID
4. Return user object với **cả integer ID và UUID**

### 🎯 **Kết Quả:**

Frontend chỉ cần gọi **1 API** và nhận được **integer ID** để dùng cho tất cả các API legacy khác mà không cần thay đổi code!

---

**Status:** ✅ Đã test và hoạt động hoàn hảo
**Ready:** 🚀 Sẵn sàng cho production
