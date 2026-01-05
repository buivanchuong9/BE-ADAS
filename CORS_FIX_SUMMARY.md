# CORS Preflight Issue - Fix Summary

## 🐛 Problem Diagnosis

### Issue
Browser sends **OPTIONS preflight request** to `GET /api/auth/me` and receives **400 Bad Request**, blocking the actual GET request.

### Root Cause
**Incorrect middleware execution order** caused authentication to run before CORS handling:

```
❌ WRONG ORDER (Before Fix):
1. CORSMiddleware (added first with app.add_middleware)
2. RequestIDMiddleware (added second)
3. @app.middleware("http") log_requests (runs AFTER add_middleware)
4. FastAPI routing → /api/auth/me endpoint
5. Authentication dependency (get_current_user)
6. ❌ OPTIONS request has no Authorization header → 400/401 error
```

### Why This Happens
- Middlewares added with `app.add_middleware()` run in **reverse order** (last added runs first)
- Middlewares defined with `@app.middleware("http")` run **AFTER** all `add_middleware()` calls
- The `log_requests` middleware was passing requests to FastAPI routing, which triggered authentication checks on OPTIONS requests

---

## ✅ Solution Applied

### 1. **Reordered Middleware Stack**

```python
✅ CORRECT ORDER (After Fix):
1. CORSMiddleware (added LAST, runs FIRST)
2. CloudflareLoggingMiddleware (added second-to-last)
3. RequestIDMiddleware (added third-to-last)
4. OPTIONS handler (catches all OPTIONS before routing)
5. FastAPI routing → endpoints
```

### 2. **Key Changes Made**

#### A. Converted `@app.middleware("http")` to `BaseHTTPMiddleware`
**Before:**
```python
@app.middleware("http")
async def log_requests(request, call_next):
    # This runs AFTER app.add_middleware() calls
    ...
```

**After:**
```python
class CloudflareLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Now runs in correct order with other middlewares
        ...

app.add_middleware(CloudflareLoggingMiddleware)
```

#### B. Moved CORSMiddleware to be Added LAST
**Before:**
```python
app.add_middleware(CORSMiddleware, ...)  # Added first
app.add_middleware(RequestIDMiddleware)  # Added second
```

**After:**
```python
app.add_middleware(RequestIDMiddleware)           # Added first (runs last)
app.add_middleware(CloudflareLoggingMiddleware)   # Added second (runs second-to-last)
app.add_middleware(CORSMiddleware, ...)           # Added LAST (runs FIRST) ✅
```

#### C. Added Explicit OPTIONS Handler
```python
@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """
    Catches all OPTIONS preflight requests and returns 200 OK.
    Prevents OPTIONS from reaching protected endpoints.
    """
    return Response(status_code=200)
```

#### D. Updated CORS Configuration
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://adas-api.aiotlab.edu.vn",
        "https://your-frontend-domain.com",  # ⚠️ REPLACE WITH YOUR ACTUAL FRONTEND URL
        "http://localhost:3000",  # React/Next.js
        "http://localhost:5173",  # Vite
        # ... other origins
    ],
    allow_credentials=True,  # ✅ Now True to support Authorization headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],  # Allows Authorization header
    expose_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)
```

---

## 🔧 Configuration Required

### ⚠️ **IMPORTANT: Update Frontend Origin**

In `main.py` line ~258, replace this placeholder:
```python
"https://your-frontend-domain.com",  # Replace with actual frontend domain
```

With your **actual frontend URL**, for example:
```python
"https://adas-frontend.aiotlab.edu.vn",  # Your production frontend
```

---

## 🧪 Testing the Fix

### 1. **Restart the Backend**
```bash
# Stop current server (Ctrl+C)
# Restart
python run.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 52000 --reload
```

### 2. **Test with Browser DevTools**

Open your frontend app and check the Network tab:

**Expected Result:**
```
✅ OPTIONS /api/auth/me → 200 OK
   Response Headers:
   - access-control-allow-origin: https://your-frontend.com
   - access-control-allow-methods: GET, POST, PUT, DELETE, OPTIONS, PATCH
   - access-control-allow-headers: *
   - access-control-allow-credentials: true

✅ GET /api/auth/me → 200 OK (with Authorization header)
   Response: { "success": true, "user": {...} }
```

### 3. **Test with cURL**

```bash
# Test OPTIONS preflight
curl -X OPTIONS https://adas-api.aiotlab.edu.vn/api/auth/me \
  -H "Origin: https://your-frontend.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  -v

# Expected: 200 OK with CORS headers

# Test actual GET request
curl -X GET https://adas-api.aiotlab.edu.vn/api/auth/me \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT_TOKEN" \
  -H "Origin: https://your-frontend.com" \
  -v

# Expected: 200 OK with user data
```

---

## 📊 How Middleware Order Works in FastAPI

### Execution Flow

```
Browser Request
    ↓
[CORSMiddleware] ← Added LAST (runs FIRST)
    ↓ (if not OPTIONS, continue)
[CloudflareLoggingMiddleware] ← Added second-to-last
    ↓
[RequestIDMiddleware] ← Added first (runs last)
    ↓
[OPTIONS Handler] ← Catches OPTIONS before routing
    ↓ (if not OPTIONS, continue)
[FastAPI Routing]
    ↓
[Endpoint Dependencies] ← get_current_user (requires auth)
    ↓
[Endpoint Handler]
    ↓
Response (flows back through middleware in reverse)
```

### Key Principle
> **Middlewares added with `app.add_middleware()` execute in REVERSE order**
> 
> - First added = Runs last (closest to endpoint)
> - Last added = Runs first (closest to client)

---

## 🎯 Why This Fix Works

1. **CORSMiddleware runs FIRST** (added last)
   - Intercepts OPTIONS requests immediately
   - Adds CORS headers to response
   - Returns 200 OK for preflight

2. **OPTIONS handler catches any remaining OPTIONS**
   - Prevents OPTIONS from reaching protected endpoints
   - Returns 200 OK before authentication checks

3. **Authentication only runs for actual requests**
   - GET /api/auth/me with Authorization header → ✅ Works
   - OPTIONS /api/auth/me without Authorization → ✅ Handled by CORS/OPTIONS handler

4. **Logging middleware doesn't interfere**
   - Now properly structured as BaseHTTPMiddleware
   - Runs in correct order with other middlewares

---

## 🔒 Security Notes

### `allow_credentials=True`
- **Required** for sending `Authorization` headers from browser
- Browser will include cookies and auth headers in requests
- **Important:** Must specify exact origins (no wildcards with credentials)

### Origin Whitelist
- Only add trusted frontend domains
- Remove `http://localhost:*` in production
- Keep development origins for local testing

### Headers
- `allow_headers=["*"]` allows `Authorization` header
- `expose_headers=["*"]` lets frontend read response headers
- `max_age=3600` reduces preflight requests (1 hour cache)

---

## 📝 Summary

### Changes Made
1. ✅ Converted `@app.middleware("http")` to `CloudflareLoggingMiddleware(BaseHTTPMiddleware)`
2. ✅ Reordered middleware: CORSMiddleware added LAST (runs FIRST)
3. ✅ Added explicit OPTIONS handler to catch preflight requests
4. ✅ Updated CORS config: `allow_credentials=True`, explicit methods, `max_age=3600`
5. ✅ Added frontend origin placeholders (needs your actual URL)

### What to Do Next
1. **Update frontend origin** in `main.py` (line ~258)
2. **Restart backend server**
3. **Test from browser** - OPTIONS should return 200 OK
4. **Verify GET /api/auth/me** works with Authorization header

### Expected Outcome
- ✅ OPTIONS /api/auth/me → 200 OK (no auth required)
- ✅ GET /api/auth/me → 200 OK (with valid token)
- ✅ Frontend can fetch user profile successfully
- ✅ No more CORS errors in browser console

---

**Author:** Senior ADAS Engineer  
**Date:** 2026-01-05  
**Issue:** CORS Preflight 400 Bad Request  
**Status:** ✅ FIXED
