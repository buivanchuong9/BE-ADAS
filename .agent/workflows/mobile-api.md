---
description: How to use the Mobile API for video upload and processing
---

# Mobile API Workflow

This workflow describes how to use the Mobile API endpoints for video upload and AI analysis.

## 📱 Base URL

```
https://adas-api.aiotlab.edu.vn/api/mobile
```

## 🔐 Authentication

All requests require Bearer token:
```
Authorization: Bearer <access_token>
```

## 📤 Step 1: Upload Video

```bash
curl -X POST "https://adas-api.aiotlab.edu.vn/api/mobile/video/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@video.mp4" \
  -F "video_type=dashcam" \
  -F "device=cuda"
```

**Response (HTTP 202):**
```json
{
  "success": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Video đã được nhận và đang chờ xử lý",
  "estimated_time_seconds": 120,
  "created_at": "2026-01-19T19:30:00Z"
}
```

## 📊 Step 2: Poll Status (every 3-5 seconds)

```bash
curl "https://adas-api.aiotlab.edu.vn/api/mobile/video/status/{job_id}" \
  -H "Authorization: Bearer $TOKEN"
```

**Status Values:**
- `queued` - Video đang chờ trong hàng đợi
- `processing` - AI đang phân tích
- `completed` - Hoàn thành, có kết quả
- `failed` - Lỗi xử lý

## 📥 Step 3: Download Result

When status = `completed`, result video URL is available at:
```
https://adas-api.aiotlab.edu.vn/public/results/{job_id}_result.mp4
```

Or use the download endpoint:
```bash
curl "https://adas-api.aiotlab.edu.vn/api/mobile/video/download/{job_id}" \
  -H "Authorization: Bearer $TOKEN" \
  -o result.mp4
```

## 📋 Step 4: View History

```bash
curl "https://adas-api.aiotlab.edu.vn/api/mobile/video/history?page=1&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

## 🔧 Debug Commands

```bash
# Check API health
curl https://adas-api.aiotlab.edu.vn/api/mobile/health

# Test upload without processing
curl -X POST https://adas-api.aiotlab.edu.vn/debug/upload-test \
  -F "file=@video.mp4"
```

## 📝 Files Modified

- `backend/app/api/mobile.py` - Mobile API router
- `backend/app/main.py` - Added mobile router + public results endpoint
