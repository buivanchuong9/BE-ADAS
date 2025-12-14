# 🚀 ADAS Backend - FastAPI Vision API

Backend FastAPI cho xử lý computer vision real-time với YOLO11 và lane detection.

## ⚡ Quick Start

### Windows Server (One-Click)
Chỉ cần double-click:
```
start-be.bat
```
Script sẽ tự động:
- ✅ Tạo virtual environment
- ✅ Cài đặt tất cả dependencies (PyTorch, FastAPI, YOLO, OpenCV...)
- ✅ Chạy server trên `0.0.0.0:52000`

### macOS / Linux
```bash
# Cài đặt dependencies
pip install -r requirements.txt

# Chạy server
python main.py
```

## 📋 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **GET** | `/health` | Health check |
| **POST** | `/vision/frame` | Process single frame (base64 image) |
| **WS** | `/vision/stream` | Real-time video streaming |
| **GET** | `/docs` | Swagger API docs |

## 🧪 Test API

### Health Check
```bash
curl http://localhost:52000/health
```

### Process Frame
```python
import requests
import base64

# Encode image to base64
with open("image.jpg", "rb") as f:
    frame_b64 = base64.b64encode(f.read()).decode()

# Send request
response = requests.post(
    "http://localhost:52000/vision/frame",
    json={"frame": frame_b64}
)

print(response.json())
```

**Response:**
```json
{
  "detections": [
    {
      "label": "car",
      "confidence": 0.95,
      "bbox": [x, y, w, h]
    }
  ],
  "lanes": {"detected": true, "count": 2},
  "elapsed_ms": 45.2
}
```

## 🌐 Deploy với Cloudflare Tunnel

```bash
# Install cloudflared
# Windows: Download từ https://github.com/cloudflare/cloudflared/releases
# macOS: brew install cloudflare/cloudflare/cloudflared

# Start tunnel
cloudflared tunnel --url http://localhost:52000

# Output: https://xyz-abc-123.trycloudflare.com
```

## 📦 Dependencies

- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **PyTorch** - Deep learning backend
- **Ultralytics** - YOLO11
- **OpenCV** - Computer vision
- **NumPy** - Numerical processing

## 🗂️ Project Structure

```
backend-python/
├── main.py              # FastAPI app (0.0.0.0:52000)
├── vision/              # Vision processing
│   ├── detector.py      # YOLO11 detection
│   └── lane.py          # Lane detection
├── ai_models/           # AI models & weights
│   └── weights/         # YOLO weights
├── start-be.bat         # Windows one-click start
└── requirements.txt     # Python dependencies
```

## 🔧 Troubleshooting

### Port đã được sử dụng
```bash
# Windows
netstat -ano | findstr :52000
taskkill /PID <PID> /F

# macOS/Linux
lsof -ti:52000 | xargs kill -9
```

### Dependencies lỗi
Xóa `venv` và chạy lại `start-be.bat`:
```bash
rmdir /s /q venv
start-be.bat
```

## 📝 Configuration

Server config trong `main.py`:
- Host: `0.0.0.0` (accept từ mọi IP)
- Port: `52000`
- CORS: Enabled (all origins)
- Log level: INFO

## ✨ Features

✅ Real-time object detection (YOLO11)  
✅ Lane detection  
✅ WebSocket streaming  
✅ REST API  
✅ CORS enabled  
✅ Cloudflare Tunnel compatible  
✅ Health check endpoint  
✅ Auto-generated API docs  

---

**Ready for production!** 🎉
