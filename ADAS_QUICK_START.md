# 🚀 ADAS Quick Start Guide

## ⚡ Chạy ngay trong 3 bước

### 1️⃣ Cài đặt dependencies
```bash
cd /Users/chuong/Desktop/AI/backend-python
pip install -r requirements.txt
```

### 2️⃣ Download model weights (tùy chọn)
```bash
chmod +x download_adas_models.sh
./download_adas_models.sh
```

Hoặc model sẽ tự động download khi chạy lần đầu.

### 3️⃣ Chạy ADAS
```bash
# Webcam
python adas_main.py --source 0

# Video file
python adas_main.py --source video.mp4

# RTSP camera
python adas_main.py --source rtsp://192.168.1.100:554/stream
```

## 🎮 Controls

- **Q/ESC**: Thoát
- **+/-**: Tăng/giảm tốc độ
- **SPACE**: Pause/Resume
- **R**: Reset stats
- **S**: Show stats

## 📋 Ví dụ

```bash
# Test với webcam, tốc độ 80 km/h
python adas_main.py --source 0 --speed 80

# Test với video, không audio
python adas_main.py --source video.mp4 --no-audio

# Chỉ test FCW
python adas_main.py --source 0 --no-tsr --no-ldw

# Quick test với ảnh
python test_adas.py
```

## ✨ Tính năng

✅ **TSR**: Nhận diện biển báo, đọc tốc độ giới hạn  
✅ **FCW**: Phát hiện xe, tính khoảng cách, cảnh báo va chạm  
✅ **LDW**: Phát hiện làn đường, cảnh báo lệch làn  
✅ **HUD**: Hiển thị tốc độ, cảnh báo real-time  
✅ **Audio**: Cảnh báo bằng giọng nói  

## 🎯 Tối ưu

**FPS thấp?**
```bash
python adas_main.py --source 0 --width 640 --height 480
```

**Camera không hoạt động?**
```bash
python adas_main.py --source 1  # Thử index khác
```

**Tắt audio?**
```bash
python adas_main.py --source 0 --no-audio
```

## 📖 Xem thêm

Chi tiết đầy đủ: [ADAS_README.md](ADAS_README.md)

---

**Happy driving! 🚗💨**
