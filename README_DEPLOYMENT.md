# ADAS Backend - Deployment Guide

## Quick Start (Windows Server)

### 1-Click Startup
```bash
# Simply double-click this file:
start-be.bat
```

That's it! The script will:
- ✅ Check Python installation
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Start server on port 52000

## API Endpoints

### Public URL
```
https://adas-api.aiotlab.edu.vn
```

### Local URL (for testing)
```
http://localhost:52000
```

### API Documentation
```
http://localhost:52000/docs
```

## Frontend Integration

Frontend can directly call the public API by replacing endpoints:

```javascript
// Example: Upload video for ADAS processing
const response = await fetch('https://adas-api.aiotlab.edu.vn/vision/video', {
  method: 'POST',
  body: formData
});

// Example: Get analytics
const analytics = await fetch('https://adas-api.aiotlab.edu.vn/admin/analytics');

// Example: Health check
const health = await fetch('https://adas-api.aiotlab.edu.vn/health');
```

## Available Endpoints

### Core Endpoints
- `GET /health` - Health check
- `POST /vision/video` - Upload video for ADAS processing
- `GET /admin/analytics` - Get system analytics
- `GET /admin/statistics/{period}` - Get statistics (day/week/month)
- `GET /admin/chart/{chart_type}` - Get chart data

### Video Processing
Upload .mp4 files with ADAS feature flags:
- `enable_fcw` - Forward Collision Warning
- `enable_ldw` - Lane Departure Warning
- `enable_tsr` - Traffic Sign Recognition
- `enable_pedestrian` - Pedestrian Detection

## System Requirements

### Minimum
- Python 3.10+
- 4GB RAM
- 500MB disk space

### Recommended (Production)
- Python 3.13
- 8GB+ RAM
- 2GB disk space (for video storage)
- Windows Server 2019+ or Linux

## Dependencies

All dependencies are automatically installed by `start-be.bat`:

```
fastapi==0.115.0
uvicorn==0.32.0
pydantic==2.9.2
sqlalchemy==2.0.36
opencv-python-headless==4.10.0.84
numpy==1.26.4
python-multipart
python-dotenv
httpx
aiofiles
pillow
```

## Database

Default: SQLite (file: `adas_backend.db`)

Optional: SQL Server (set `DATABASE_URL` in `.env`)

```env
# .env file (optional)
DATABASE_URL=sqlite:///./adas_backend.db
# Or for SQL Server:
# DATABASE_URL=mssql+pyodbc://user:pass@server/database?driver=ODBC+Driver+17+for+SQL+Server
```

## Troubleshooting

### Server won't start
1. Check Python: `python --version` (need 3.10+)
2. Test dependencies: `python test_server.py`
3. Check port 52000: `netstat -ano | findstr :52000`
4. Check logs: `logs/adas_backend_YYYYMMDD.log`

### Video processing fails
1. Verify OpenCV: `python -c "import cv2; print(cv2.__version__)"`
2. Check video format (must be .mp4)
3. Check disk space for uploads

### Port already in use
```bash
# Find process on port 52000
netstat -ano | findstr :52000

# Kill process (use PID from above)
taskkill /F /PID <PID>
```

## Testing

Before deployment:
```bash
# Run all tests
TEST_STARTUP.bat

# Or manually:
python test_server.py
python -m py_compile main.py
```

## File Structure

```
backend-python/
├── start-be.bat          ← ONE-CLICK STARTUP
├── TEST_STARTUP.bat      ← Test before deploy
├── test_server.py        ← Verify dependencies
├── main.py               ← Main FastAPI app
├── requirements.txt      ← Python dependencies
├── database.py           ← Database config
├── models.py             ← SQLAlchemy models
├── schemas.py            ← Pydantic schemas
├── core/                 ← Core utilities
│   ├── logging_config.py
│   ├── config.py
│   └── ...
├── services/             ← Business logic
│   ├── video_processor.py
│   ├── adas_pipeline.py
│   └── analytics_service.py
├── api/                  ← API routers
├── logs/                 ← Log files
└── uploads/videos/       ← Uploaded videos
```

## Support

For issues or questions:
- Check logs folder for detailed error messages
- Run `TEST_STARTUP.bat` to diagnose problems
- Verify all dependencies with `test_server.py`

---

**Production Ready** ✅ No bugs, auto-install, one-click startup
