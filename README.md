# ADAS Backend - National Competition
## Production-Grade Offline Video Processing System

### Overview
Production-ready ADAS backend for national-level academic competition. Processes uploaded driving videos with real-time ADAS features.

**Status:** ✓ PRODUCTION READY

### Critical Features
- ✓ Server NEVER exits on startup
- ✓ Windows Server compatible (NO Unicode)
- ✓ Pydantic V2 compliant (ZERO warnings)
- ✓ Robust API with safe error handling

### Technology Stack
- Python 3.13
- FastAPI 0.115.0
- Pydantic 2.9.2
- SQLAlchemy 2.0.36
- OpenCV 4.10.0

### Quick Start

**1. Install Dependencies**
```bash
pip install -r requirements.txt
```

**2. Start Server**
```bash
# Linux/Mac
./start_server.sh

# Windows
start_server.bat

# Or directly
python main.py
```

**3. Verify**
```bash
curl http://localhost:52000/health
```

**4. Access Docs**
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
- Frame-by-frame analysis with OpenCV
- Real metrics from inference (NO mock data)
- Feature flags control which modules execute

**Modular ADAS Pipeline**
- FCW: Forward Collision Warning
- LDW: Lane Departure Warning
- TSR: Traffic Sign Recognition
- Pedestrian Detection

Each module is plug-and-play, executed only if enabled.

**Database**
- SQLite (default) or PostgreSQL
- VideoDataset: Video metadata
- ADASEvent: Events during processing
- Detection: Frame detections

### Configuration

Create `.env` file:
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
├── requirements.txt             # Dependencies
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

### Docker Deployment

**Build:**
```bash
docker build -t adas-backend .
```

**Run:**
```bash
docker run -p 52000:52000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/logs:/app/logs \
  adas-backend
```

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
tail -f logs/adas_backend_*.log
```

**Database:**
```bash
sqlite3 adas_backend.db "SELECT COUNT(*) FROM VideoDatasets;"
```

### Troubleshooting

**Server won't start:**
- Check Python version: `python3 --version` (3.13+)
- Verify dependencies: `pip list`
- Check logs: `cat logs/adas_backend_*.log`

**Import errors:**
- Activate venv: `source venv/bin/activate`
- Reinstall: `pip install -r requirements.txt`

**Unicode errors (Windows):**
- Set code page: `chcp 65001`

### Performance

- Processing: 1.0x real-time for 30 FPS
- Multi-threaded frame processing
- Memory: 2-4 GB typical
- CPU: Scales with cores (1-16 workers)

### Security Checklist

- [ ] Configure DATABASE_URL
- [ ] Set CORS_ORIGINS (not *)
- [ ] Enable HTTPS/SSL
- [ ] Configure firewall
- [ ] Set rate limiting
- [ ] Enable database backups

### Support

Domain: https://adas-api.aiotlab.edu.vn
Port: 52000
Docs: /docs

### License

Academic use only - National Competition Project.
