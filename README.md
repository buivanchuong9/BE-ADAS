# ADAS Backend - National Competition
## Production-Grade Offline Video Processing System

### Overview
Production-ready ADAS backend for national-level academic competition. Processes uploaded driving videos with real-time ADAS features.

**Status:** ✓ PRODUCTION READY - Windows Server Compatible

### Critical Features
- ✓ Server NEVER exits on startup
- ✓ Windows Server compatible (NO compilation required)
- ✓ Pydantic V2 compliant (ZERO warnings)
- ✓ Robust API with safe error handling
- ✓ Pre-built wheels only (no Visual Studio needed)

### Technology Stack
- Python 3.10+ (3.10, 3.11, 3.12 recommended)
- FastAPI 0.115.0
- Pydantic 2.9.2
- SQLAlchemy 2.0.36
- OpenCV 4.10.0 (optional)

### Windows Server Installation

**Option 1: Automatic (Recommended)**
```batch
install_windows.bat
```

**Option 2: Manual**
```batch
REM 1. Install Python 3.10+ from python.org
REM 2. Upgrade pip
python -m pip install --upgrade pip

REM 3. Install dependencies
pip install -r requirements.txt
```

**Option 3: Minimal (Without OpenCV)**
```batch
pip install -r requirements_minimal.txt
```

### Quick Start

**1. Windows Server**
```batch
start_server.bat
```

**2. Linux/Mac**
```bash
./start_server.sh
```

**3. Direct**
```bash
python main.py
```

**4. Verify**
```bash
curl http://localhost:52000/health
```

**5. Access Docs**
```
http://localhost:52000/docs
```

### API Endpoints

**Video Processing**
```
POST /vision/video
```
Upload video with feature flags:
- enable_fcw: Forward Collision Warning
- enable_ldw: Lane Departure Warning
- enable_tsr: Traffic Sign Recognition
- enable_pedestrian: Pedestrian Detection

**Admin Analytics**
```
GET /admin/overview              - Overview statistics
GET /admin/video/{id}/timeline   - Event timeline
GET /admin/statistics?period=day - Aggregated stats
GET /admin/charts?chart_type=... - Chart data
GET /health                      - Health check
```

### Architecture

**Offline Video Processing**
- Upload .mp4 files via multipart/form-data
- Frame-by-frame analysis with OpenCV (optional)
- Real metrics from inference (NO mock data)
- Feature flags control which modules execute

**Modular ADAS Pipeline**
- FCW: Forward Collision Warning
- LDW: Lane Departure Warning
- TSR: Traffic Sign Recognition
- Pedestrian Detection

Each module is plug-and-play, executed only if enabled.

**Database**
- SQLite (default) - no configuration needed
- PostgreSQL (optional) - for production
- VideoDataset: Video metadata
- ADASEvent: Events during processing
- Detection: Frame detections

### Configuration

Create `.env` file (optional):
```env
DATABASE_URL=sqlite:///./adas_backend.db
SERVER_HOST=0.0.0.0
SERVER_PORT=52000
DEBUG=False
```

### Project Structure

```
backend-python/
├── main.py                      # Main FastAPI application
├── database.py                  # Database configuration
├── models.py                    # SQLAlchemy models
├── schemas.py                   # Pydantic V2 schemas
├── requirements.txt             # Full dependencies
├── requirements_minimal.txt     # Minimal (no OpenCV)
├── install_windows.bat          # Windows installer
├── start_server.bat             # Windows startup
├── start_server.sh              # Linux/Mac startup
├── core/
│   ├── config.py               # Configuration
│   ├── logging_config.py       # ASCII-safe logging
│   ├── exceptions.py           # Custom exceptions
│   └── responses.py            # Standard responses
├── services/
│   ├── video_processor.py      # Video processing
│   ├── adas_pipeline.py        # ADAS modules
│   └── analytics_service.py    # Analytics
└── logs/                       # Application logs
```

### Troubleshooting

**Windows Server: NumPy/OpenCV Build Error**
```batch
REM Solution 1: Use pre-built wheels
pip install --only-binary :all: numpy opencv-python-headless

REM Solution 2: Use minimal requirements
pip install -r requirements_minimal.txt

REM Solution 3: Install Visual C++ Build Tools (not recommended)
REM Download from: https://visualstudio.microsoft.com/downloads/
```

**Server won't start:**
- Check Python version: `python --version` (3.10+)
- Verify dependencies: `pip list`
- Check logs: `type logs\adas_backend_*.log`

**Import errors:**
- Reinstall: `pip install --force-reinstall -r requirements.txt`
- Try minimal: `pip install -r requirements_minimal.txt`

**Permission errors (Windows):**
- Run as Administrator
- Check firewall settings for port 52000

**Database errors:**
- Delete adas_backend.db and restart
- Server will auto-create tables

### Testing

**System Test:**
```bash
python test_system.py
```

**Test Upload:**
```bash
curl -X POST http://localhost:52000/vision/video \
  -F "file=@test.mp4" \
  -F "enable_fcw=true" \
  -F "enable_ldw=true" \
  -F "confidence_threshold=0.5"
```

### Monitoring

**Health Check:**
```bash
curl http://localhost:52000/health
```

**Logs:**
```bash
# Windows
type logs\adas_backend_*.log

# Linux/Mac
tail -f logs/adas_backend_*.log
```

**Database:**
```bash
sqlite3 adas_backend.db "SELECT COUNT(*) FROM VideoDatasets;"
```

### Performance

- Processing: 1.0x real-time for 30 FPS
- Multi-threaded frame processing
- Memory: 2-4 GB typical
- CPU: Scales with cores (1-16 workers)

### Windows Server Deployment

**IIS Reverse Proxy:**
```xml
<rewrite>
  <rules>
    <rule name="ADAS Backend">
      <match url="(.*)" />
      <action type="Rewrite" url="http://localhost:52000/{R:1}" />
    </rule>
  </rules>
</rewrite>
```

**Windows Service (NSSM):**
```batch
nssm install AdasBackend python.exe
nssm set AdasBackend AppDirectory "C:\path\to\backend-python"
nssm set AdasBackend AppParameters "main.py"
nssm start AdasBackend
```

### Security Checklist

- [ ] Configure DATABASE_URL (not default)
- [ ] Set CORS_ORIGINS (not *)
- [ ] Enable HTTPS/SSL
- [ ] Configure Windows Firewall
- [ ] Set rate limiting
- [ ] Enable database backups

### Support

Domain: https://adas-api.aiotlab.edu.vn
Port: 52000
Docs: /docs

### License

Academic use only - National Competition Project.
