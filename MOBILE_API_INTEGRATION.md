# 📱 Mobile API Integration Guide

**Base URL:** `https://adas-api.aiotlab.edu.vn`  
**Version:** 1.1.0  
**Updated:** March 2026

---

## 🎯 Quick Start

### Driver Monitoring Flow (In-Cabin Camera)

```javascript
// 1. Upload video
const formData = new FormData();
formData.append('file', videoFile);

const uploadRes = await fetch('https://adas-api.aiotlab.edu.vn/api/mobile/driver/upload', {
  method: 'POST',
  body: formData
});
const { job_id } = await uploadRes.json();

// 2. Poll for status
while (true) {
  const statusRes = await fetch(`https://adas-api.aiotlab.edu.vn/api/mobile/driver/status/${job_id}`);
  const status = await statusRes.json();
  
  if (status.status === 'completed') {
    // 3. Play video
    const videoUrl = `https://adas-api.aiotlab.edu.vn${status.result.video_url}`;
    // videoUrl ends with .mp4 - can stream instantly!
    break;
  }
  
  await new Promise(r => setTimeout(r, 2000)); // Poll every 2s
}
```

---

## 📹 Video Format - CRITICAL

### ⚠️ Why Video URL Must End with `.mp4`

Mobile video players (iOS AVPlayer, Android ExoPlayer) **check file extension** to determine format. Without `.mp4`, they may:
- ❌ Download entire file before playing
- ❌ Show "unsupported format" error
- ❌ Refuse to stream

### ✅ Correct URLs

```
✅ https://adas-api.aiotlab.edu.vn/api/mobile/driver/download/abc-123/result.mp4
✅ https://adas-api.aiotlab.edu.vn/api/mobile/video/download/xyz-789/result.mp4
```

### ❌ Incorrect URLs

```
❌ https://adas-api.aiotlab.edu.vn/api/mobile/driver/download/abc-123
❌ https://adas-api.aiotlab.edu.vn/api/download?job_id=abc-123
```

### 🎬 Video Encoding Specs

All videos are encoded with **mobile-compatible settings**:

```bash
# Backend uses these FFmpeg parameters:
-vcodec libx264           # H.264 codec (universal support)
-pix_fmt yuv420p          # Pixel format (iOS/Android compatible)
-profile:v baseline       # Baseline profile (max compatibility)
-level 3.0                # Level 3.0 (older devices support)
-movflags +faststart      # Progressive download (INSTANT STREAMING)
-acodec aac               # AAC audio (universal)
```

**Why this matters:**
- ✅ **`-movflags +faststart`** moves metadata to file start → video can stream immediately
- ✅ **`baseline` profile** works on ALL iOS/Android devices (even old ones)
- ✅ **`yuv420p`** pixel format required for Safari/Chrome

Without these settings, users must download the entire video before playback starts!

---

## 🚗 Driver Monitoring API

### 1. Upload Driver Video

**Endpoint:** `POST /api/mobile/driver/upload`

**Request:**
```http
POST https://adas-api.aiotlab.edu.vn/api/mobile/driver/upload
Content-Type: multipart/form-data

file: <video_file.mp4>
```

**iOS Swift:**
```swift
func uploadDriverVideo(videoURL: URL) async throws -> String {
    let url = URL(string: "https://adas-api.aiotlab.edu.vn/api/mobile/driver/upload")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    
    let boundary = UUID().uuidString
    request.setValue("multipart/form-data; boundary=\(boundary)", 
                    forHTTPHeaderField: "Content-Type")
    
    var body = Data()
    body.append("--\(boundary)\r\n")
    body.append("Content-Disposition: form-data; name=\"file\"; filename=\"video.mp4\"\r\n")
    body.append("Content-Type: video/mp4\r\n\r\n")
    body.append(try Data(contentsOf: videoURL))
    body.append("\r\n--\(boundary)--\r\n")
    
    request.httpBody = body
    
    let (data, _) = try await URLSession.shared.data(for: request)
    let result = try JSONDecoder().decode(UploadResponse.self, from: data)
    return result.job_id
}

struct UploadResponse: Codable {
    let success: Bool
    let job_id: String
    let status: String
    let message: String
}
```

**React Native:**
```javascript
async function uploadDriverVideo(videoUri) {
  const formData = new FormData();
  formData.append('file', {
    uri: videoUri,
    type: 'video/mp4',
    name: 'driver.mp4'
  });

  const res = await fetch('https://adas-api.aiotlab.edu.vn/api/mobile/driver/upload', {
    method: 'POST',
    body: formData,
    headers: { 'Content-Type': 'multipart/form-data' }
  });

  const data = await res.json();
  return data.job_id;
}
```

**Response:**
```json
{
  "success": true,
  "job_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "pending",
  "message": "Video đã được upload. Đang chờ xử lý phát hiện mệt mỏi/mất tập trung.",
  "video_type": "in_cabin",
  "estimated_time_seconds": 90,
  "created_at": "2026-03-01T10:30:00Z"
}
```

---

### 2. Check Processing Status

**Endpoint:** `GET /api/mobile/driver/status/{job_id}`

**Request:**
```http
GET https://adas-api.aiotlab.edu.vn/api/mobile/driver/status/a1b2c3d4-5678-90ab-cdef-1234567890ab
```

**iOS Swift Polling:**
```swift
func pollDriverStatus(jobId: String) async throws -> DriverResult {
    let baseURL = "https://adas-api.aiotlab.edu.vn/api/mobile/driver/status/"
    
    while true {
        let url = URL(string: baseURL + jobId)!
        let (data, _) = try await URLSession.shared.data(from: url)
        let status = try JSONDecoder().decode(StatusResponse.self, from: data)
        
        // Update UI with progress
        print("Progress: \(status.progress_percent)%")
        
        if status.status == "completed" {
            return status.result!
        } else if status.status == "failed" {
            throw APIError(message: status.error?.message ?? "Processing failed")
        }
        
        // Wait 2 seconds
        try await Task.sleep(nanoseconds: 2_000_000_000)
    }
}

struct StatusResponse: Codable {
    let success: Bool
    let job_id: String
    let status: String
    let progress_percent: Int
    let result: DriverResult?
    let error: ErrorDetail?
}

struct DriverResult: Codable {
    let video_url: String
    let download_url: String
    let duration_seconds: Double?
    let processing_time_seconds: Double?
}
```

**React Native Polling:**
```javascript
async function pollDriverStatus(jobId) {
  while (true) {
    const res = await fetch(
      `https://adas-api.aiotlab.edu.vn/api/mobile/driver/status/${jobId}`
    );
    const data = await res.json();
    
    console.log(`Progress: ${data.progress_percent}%`);
    
    if (data.status === 'completed') {
      return data.result; // { video_url: "...", download_url: "..." }
    }
    
    if (data.status === 'failed') {
      throw new Error(data.error?.message || 'Processing failed');
    }
    
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}
```

**Response - Processing:**
```json
{
  "success": true,
  "job_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "processing",
  "progress_percent": 75,
  "video_type": "in_cabin",
  "result": null,
  "error": null
}
```

**Response - Completed:**
```json
{
  "success": true,
  "job_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "completed",
  "progress_percent": 100,
  "video_type": "in_cabin",
  "result": {
    "download_url": "/api/mobile/driver/download/a1b2c3d4-5678-90ab-cdef-1234567890ab/result.mp4",
    "video_url": "/api/mobile/driver/download/a1b2c3d4-5678-90ab-cdef-1234567890ab/result.mp4",
    "duration_seconds": 60.5,
    "processing_time_seconds": 45.2,
    "fatigue_detection": true,
    "distraction_detection": true
  },
  "error": null
}
```

---

### 3. Play Result Video

**Endpoint:** `GET /api/mobile/driver/download/{job_id}/result.mp4` ⚠️ MUST end with `.mp4`

**iOS AVPlayer:**
```swift
import AVKit

func playDriverResult(jobId: String) {
    let videoURL = URL(string: "https://adas-api.aiotlab.edu.vn/api/mobile/driver/download/\(jobId)/result.mp4")!
    
    let player = AVPlayer(url: videoURL)
    let controller = AVPlayerViewController()
    controller.player = player
    
    present(controller, animated: true) {
        player.play()
    }
}
```

**React Native Video:**
```javascript
import Video from 'react-native-video';

function DriverResultPlayer({ jobId }) {
  const videoUrl = `https://adas-api.aiotlab.edu.vn/api/mobile/driver/download/${jobId}/result.mp4`;
  
  return (
    <Video
      source={{ uri: videoUrl }}
      style={{ width: '100%', height: 300 }}
      controls={true}
      resizeMode="contain"
      // Video will stream instantly thanks to faststart!
    />
  );
}
```

**HTML5:**
```html
<video controls width="100%">
  <source 
    src="https://adas-api.aiotlab.edu.vn/api/mobile/driver/download/a1b2c3d4/result.mp4" 
    type="video/mp4">
</video>
```

---

## 🚙 Dashcam Video API

Same flow as Driver Monitoring, but different endpoints:

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mobile/video/upload` | Upload dashcam video |
| GET | `/api/mobile/video/status/{job_id}` | Check status |
| GET | `/api/mobile/video/download/{job_id}/result.mp4` | Download result |
| GET | `/api/mobile/video/history?page=1&limit=20` | Get history |

### Upload Example

```javascript
const formData = new FormData();
formData.append('file', dashcamVideo);
formData.append('video_type', 'dashcam');
formData.append('device', 'cuda');

const res = await fetch('https://adas-api.aiotlab.edu.vn/api/mobile/video/upload', {
  method: 'POST',
  body: formData
});
```

---

## 🎨 Complete Example: Full Screen

```javascript
import React, { useState, useEffect } from 'react';
import { View, Button, Text, ActivityIndicator } from 'react-native';
import Video from 'react-native-video';
import DocumentPicker from 'react-native-document-picker';

const API_BASE = 'https://adas-api.aiotlab.edu.vn';

function DriverMonitorScreen() {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [videoUrl, setVideoUrl] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Upload
  const handleUpload = async () => {
    try {
      setUploading(true);
      
      const file = await DocumentPicker.pick({
        type: [DocumentPicker.types.video],
      });

      const formData = new FormData();
      formData.append('file', {
        uri: file[0].uri,
        type: file[0].type,
        name: file[0].name,
      });

      const res = await fetch(`${API_BASE}/api/mobile/driver/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      
      if (data.success) {
        setJobId(data.job_id);
        setStatus('pending');
      } else {
        alert('Upload failed: ' + data.error?.message);
      }
    } catch (err) {
      if (!DocumentPicker.isCancel(err)) {
        alert('Error: ' + err.message);
      }
    } finally {
      setUploading(false);
    }
  };

  // Poll status
  useEffect(() => {
    if (!jobId || status === 'completed' || status === 'failed') return;

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/mobile/driver/status/${jobId}`);
        const data = await res.json();

        setStatus(data.status);
        setProgress(data.progress_percent);

        if (data.status === 'completed') {
          setVideoUrl(`${API_BASE}${data.result.video_url}`);
        } else if (data.status === 'failed') {
          alert('Processing failed: ' + data.error?.message);
        }
      } catch (err) {
        console.error('Poll error:', err);
      }
    };

    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [jobId, status]);

  return (
    <View style={{ padding: 20 }}>
      <Text style={{ fontSize: 24, marginBottom: 20 }}>
        Driver Monitoring
      </Text>

      {!jobId && (
        <Button
          title={uploading ? "Uploading..." : "Select Video"}
          onPress={handleUpload}
          disabled={uploading}
        />
      )}

      {jobId && status !== 'completed' && (
        <View style={{ marginTop: 20 }}>
          <Text>Status: {status}</Text>
          <Text>Progress: {progress}%</Text>
          <ActivityIndicator size="large" />
        </View>
      )}

      {videoUrl && (
        <View style={{ marginTop: 20 }}>
          <Text style={{ fontSize: 18, marginBottom: 10 }}>Result:</Text>
          <Video
            source={{ uri: videoUrl }}
            style={{ width: '100%', height: 300 }}
            controls={true}
            resizeMode="contain"
          />
          <Button
            title="Upload Another Video"
            onPress={() => {
              setJobId(null);
              setVideoUrl(null);
              setStatus('idle');
              setProgress(0);
            }}
          />
        </View>
      )}
    </View>
  );
}

export default DriverMonitorScreen;
```

---

## ⚠️ Error Handling

All errors return JSON:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Description"
  }
}
```

### Common Errors

| Code | HTTP | Meaning |
|------|------|---------|
| `NO_FILE` | 400 | No file uploaded |
| `INVALID_FILE_TYPE` | 400 | Not a video file |
| `FILE_TOO_LARGE` | 400 | File > 500MB |
| `NOT_READY` | 400 | Video still processing |
| `NOT_FOUND` | 404 | Job ID not found |
| `PROCESSING_FAILED` | 200 | Processing error (check status.error) |

**Swift Error Handling:**
```swift
do {
    let result = try await uploadDriverVideo(videoURL: url)
} catch let error as APIError {
    switch error.code {
    case "FILE_TOO_LARGE":
        showAlert("Video quá lớn. Max 500MB")
    case "INVALID_FILE_TYPE":
        showAlert("Chỉ hỗ trợ .mp4, .avi, .mov")
    default:
        showAlert("Lỗi: \(error.message)")
    }
}
```

---

## 📊 Performance & Limits

### File Size
- **Max:** 500MB
- **Recommended:** < 100MB for faster upload

### Video Formats
- ✅ `.mp4` (recommended)
- ✅ `.avi`
- ✅ `.mov`
- ❌ `.mkv`, `.flv` (not supported)

### Processing Time
- **Driver Monitoring:** ~60-90s for 60s video
- **Dashcam:** ~90-120s for 60s video

### Polling Interval
- **Recommended:** 2-3 seconds
- **Min:** 1 second (don't poll faster!)

### Rate Limits (Soft)
- Upload: Max 10 videos/minute
- Status polling: Every 2+ seconds

---

## 🧪 Testing

### Health Check

```bash
curl https://adas-api.aiotlab.edu.vn/api/mobile/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "ADAS Mobile API",
  "version": "1.1.0",
  "endpoints": {
    "video": [
      "POST /api/mobile/video/upload",
      "GET /api/mobile/video/status/{job_id}",
      "GET /api/mobile/video/download/{job_id}/result.mp4"
    ],
    "driver_monitoring": [
      "POST /api/mobile/driver/upload",
      "GET /api/mobile/driver/status/{job_id}",
      "GET /api/mobile/driver/download/{job_id}/result.mp4"
    ]
  }
}
```

### Test Upload (cURL)

```bash
# Upload driver video
curl -X POST https://adas-api.aiotlab.edu.vn/api/mobile/driver/upload \
  -F "file=@test_video.mp4"

# Response: {"success": true, "job_id": "abc-123", ...}

# Check status
curl https://adas-api.aiotlab.edu.vn/api/mobile/driver/status/abc-123

# Download result (after completed)
curl -O https://adas-api.aiotlab.edu.vn/api/mobile/driver/download/abc-123/result.mp4
```

---

## 🔐 Authentication (Future)

Currently, all endpoints are public (no auth required).

**Planned:** Supabase JWT authentication

```javascript
// Login
const { data } = await supabase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password'
});

const token = data.session.access_token;

// Call API with token
fetch('https://adas-api.aiotlab.edu.vn/api/mobile/driver/upload', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
```

---

## 📝 Checklist for Integration

- [ ] Video URLs end with `.mp4` extension
- [ ] Poll status every 2-3 seconds (not faster!)
- [ ] Handle all error codes properly
- [ ] Show progress percentage to user
- [ ] Use AVPlayer (iOS) or ExoPlayer (Android) for playback
- [ ] Test with different video sizes (10MB, 50MB, 100MB)
- [ ] Add network timeout handling (upload may take 30s-2min)
- [ ] Cache video results locally after download
- [ ] Add retry logic for failed uploads
- [ ] Show estimated time remaining based on progress_percent

---

## 🆘 Support

**Issues:** support@aiotlab.edu.vn  
**Response Time:** 1-2 business days

---

## 📜 Changelog

### v1.1.0 (March 2026)
- ✅ Added mobile-compatible video encoding (baseline profile + faststart)
- ✅ Added Driver Monitoring API
- ✅ Fixed `.mp4` extension for all download endpoints
- ✅ Bug fixes: Pydantic validation, database schema, MediaPipe

### v1.0.0 (January 2026)
- 🎉 Initial release

---

**🚀 Happy coding! Video streaming works instantly now!**
