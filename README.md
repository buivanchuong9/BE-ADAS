# ADAS Backend API - Production Deployment

## 🌐 Production Domain
**Base URL**: https://adas-api.aiotlab.edu.vn:52000

## 📡 API Endpoints

### Core Endpoints
- **API Documentation**: https://adas-api.aiotlab.edu.vn:52000/docs
- **OpenAPI Schema**: https://adas-api.aiotlab.edu.vn:52000/openapi.json
- **Health Check**: https://adas-api.aiotlab.edu.vn:52000/health

### Authentication
```bash
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/auth/login
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/auth/register
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/auth/refresh
```

### Video Processing
```bash
POST   https://adas-api.aiotlab.edu.vn:52000/api/v1/videos/upload
POST   https://adas-api.aiotlab.edu.vn:52000/api/v1/videos/process
GET    https://adas-api.aiotlab.edu.vn:52000/api/v1/videos/{id}
GET    https://adas-api.aiotlab.edu.vn:52000/api/v1/videos/{id}/status
DELETE https://adas-api.aiotlab.edu.vn:52000/api/v1/videos/{id}
```

### Real-time Alerts (WebSocket)
```javascript
// WebSocket connection
const ws = new WebSocket('wss://adas-api.aiotlab.edu.vn:52000/ws/alerts');

ws.onmessage = (event) => {
    const alert = JSON.parse(event.data);
    console.log('Alert:', alert);
};
```

### AI Models
```bash
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/models/list
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/models/update
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/models/{id}/info
```

### Driver Monitoring
```bash
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/driver/analyze
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/driver/stats
```

### Trips & Statistics
```bash
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/trips
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/trips/{id}
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/trips/{id}/stats
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/trips/{id}/end
```

### Events & Alerts
```bash
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/events
GET  https://adas-api.aiotlab.edu.vn:52000/api/v1/events/{id}
POST https://adas-api.aiotlab.edu.vn:52000/api/v1/alerts
```

## 🔐 Authentication Example

### Login
```bash
curl -X POST https://adas-api.aiotlab.edu.vn:52000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "Admin123!@#"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### Using Token
```bash
curl -X GET https://adas-api.aiotlab.edu.vn:52000/api/v1/videos \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 📦 Upload Video Example

```bash
curl -X POST https://adas-api.aiotlab.edu.vn:52000/api/v1/videos/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/video.mp4" \
  -F "title=Test Drive" \
  -F "description=Highway test"
```

## 🌐 Frontend Integration

### React/Next.js
```javascript
const API_BASE_URL = 'https://adas-api.aiotlab.edu.vn:52000';
const WS_URL = 'wss://adas-api.aiotlab.edu.vn:52000';

// API call
const response = await fetch(`${API_BASE_URL}/api/v1/videos`, {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

// WebSocket connection
const ws = new WebSocket(`${WS_URL}/ws/alerts`);
```

### Vue.js
```javascript
// axios configuration
import axios from 'axios';

const api = axios.create({
  baseURL: 'https://adas-api.aiotlab.edu.vn:52000',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add auth token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

## 🔧 Environment Configuration

### Production `.env`
```env
# API Configuration
API_BASE_URL=https://adas-api.aiotlab.edu.vn:52000
HOST=0.0.0.0
PORT=52000
ENVIRONMENT=production

# CORS - Production domains
CORS_ORIGINS=https://adas-api.aiotlab.edu.vn,https://adas-api.aiotlab.edu.vn:52000

# Database (SQL Server on localhost)
DB_HOST=localhost
DB_PORT=1433
DB_NAME=adas_production
DB_USER=adas_user
DB_PASSWORD=YourStrongPassword123!@#

# Security
SECRET_KEY=production-secret-key-min-32-characters-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Storage paths
STORAGE_ROOT=C:/inetpub/wwwroot/adas-backend/backend/storage
RAW_VIDEO_DIR=C:/inetpub/wwwroot/adas-backend/backend/storage/raw
PROCESSED_VIDEO_DIR=C:/inetpub/wwwroot/adas-backend/backend/storage/result
AUDIO_CACHE_DIR=C:/inetpub/wwwroot/adas-backend/backend/storage/audio_cache

# AI Models
YOLO_MODEL_PATH=C:/inetpub/wwwroot/adas-backend/backend/models/yolov11n.pt
DEFAULT_DEVICE=cuda  # or cpu

# Logging
LOG_LEVEL=INFO
LOG_DIR=C:/inetpub/wwwroot/adas-backend/backend/logs
```

## 🐳 Docker Deployment

### Using Docker Compose
```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop
docker-compose down
```

The service will be available at: https://adas-api.aiotlab.edu.vn:52000

## 🧪 Testing Production API

### Health Check
```bash
curl https://adas-api.aiotlab.edu.vn:52000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2025-12-26T10:30:00Z",
  "database": "connected",
  "gpu": "available"
}
```

### Run Full Test Suite
```bash
# Set production URL
export API_BASE_URL=https://adas-api.aiotlab.edu.vn:52000

# Run tests
python test_all_phases.py
```

## 📊 Monitoring

### Logs
```bash
# View real-time logs (Linux)
tail -f /var/log/adas/app.log

# View logs (Windows)
Get-Content C:\inetpub\wwwroot\adas-backend\backend\logs\app.log -Tail 50 -Wait
```

### Metrics Endpoints
```bash
# System metrics
curl https://adas-api.aiotlab.edu.vn:52000/api/v1/metrics/system

# Processing metrics
curl https://adas-api.aiotlab.edu.vn:52000/api/v1/metrics/processing
```

## 🔒 Security

### SSL/TLS Certificate
- Production uses HTTPS with valid SSL certificate
- Certificate managed by IIS/nginx
- Auto-renewal configured

### CORS Policy
Allowed origins:
- `https://adas-api.aiotlab.edu.vn`
- `https://adas-api.aiotlab.edu.vn:52000`

### Rate Limiting
- Default: 100 requests/minute per IP
- Authenticated: 1000 requests/minute per token

## 📚 Documentation

- **Interactive API Docs**: https://adas-api.aiotlab.edu.vn:52000/docs
- **ReDoc**: https://adas-api.aiotlab.edu.vn:52000/redoc
- **Deployment Guide**: [WINDOWS_SERVER_DEPLOYMENT.md](WINDOWS_SERVER_DEPLOYMENT.md)
- **Database Setup**: [DATABASE_SETUP_GUIDE.md](DATABASE_SETUP_GUIDE.md)
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)

## 🆘 Support

**Repository**: https://github.com/buivanchuong9/BE-ADAS.git  
**Team**: NCKH ADAS Development Team  
**Date**: December 2025

---

**Note**: For development, you can still use `http://localhost:8000` by setting `ENVIRONMENT=development` in `.env`.
