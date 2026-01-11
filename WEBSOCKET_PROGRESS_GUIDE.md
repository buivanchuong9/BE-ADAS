# WebSocket Video Progress - Frontend Integration Guide

## 🚀 Tóm Tắt

Backend đã có **WebSocket endpoint** để FE nhận **real-time progress** khi video đang xử lý.

---

## 📡 WebSocket Endpoint

```
ws://domain/ws/video/progress/{job_id}
wss://adas-api.aiotlab.edu.vn/ws/video/progress/{job_id}
```

---

## 💻 Frontend Code (JavaScript/React)

### Vanilla JavaScript

```javascript
// 1. Upload video
const formData = new FormData();
formData.append('file', videoFile);

const uploadRes = await fetch('https://adas-api.aiotlab.edu.vn/api/video/upload', {
  method: 'POST',
  body: formData
});

const { job_id } = await uploadRes.json();

// 2. Connect WebSocket for progress
const ws = new WebSocket(`wss://adas-api.aiotlab.edu.vn/ws/video/progress/${job_id}`);

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'connected') {
    console.log('✅ Connected:', data.message);
  }
  
  if (data.type === 'progress') {
    // Update UI
    const percent = data.progress_percent; // 0-100
    const status = data.status; // processing/completed/failed
    
    updateProgressBar(percent);
    updateStatus(status);
    
    console.log(`Progress: ${percent}% - Status: ${status}`);
  }
  
  if (data.type === 'finished') {
    console.log('✅ Video processing finished:', data.status);
    ws.close();
    
    // Show result video
    if (data.status === 'completed') {
      showResultVideo(job_id);
    }
  }
  
  if (data.type === 'error') {
    console.error('❌ Error:', data.message);
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket closed');
};

// Helper functions
function updateProgressBar(percent) {
  const progressBar = document.getElementById('progress-bar');
  progressBar.value = percent;
  progressBar.innerText = `${percent}%`;
}

function updateStatus(status) {
  const statusEl = document.getElementById('status');
  statusEl.innerText = status;
}

function showResultVideo(jobId) {
  const videoUrl = `https://adas-api.aiotlab.edu.vn/api/video/download/${jobId}/result.mp4`;
  const videoEl = document.getElementById('result-video');
  videoEl.src = videoUrl;
  videoEl.play();
}
```

---

### React Hook

```javascript
import { useEffect, useState } from 'react';

export function useVideoProgress(jobId) {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('pending');
  const [isFinished, setIsFinished] = useState(false);
  
  useEffect(() => {
    if (!jobId) return;
    
    const ws = new WebSocket(
      `wss://adas-api.aiotlab.edu.vn/ws/video/progress/${jobId}`
    );
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'progress') {
        setProgress(data.progress_percent);
        setStatus(data.status);
      }
      
      if (data.type === 'finished') {
        setIsFinished(true);
        ws.close();
      }
    };
    
    ws.onerror = (error) => {
      console.error('WS Error:', error);
    };
    
    return () => {
      ws.close();
    };
  }, [jobId]);
  
  return { progress, status, isFinished };
}

// Usage in component
function VideoAnalysis() {
  const [jobId, setJobId] = useState(null);
  const { progress, status, isFinished } = useVideoProgress(jobId);
  
  const handleUpload = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch('/api/video/upload', {
      method: 'POST',
      body: formData
    });
    
    const { job_id } = await res.json();
    setJobId(job_id);
  };
  
  return (
    <div>
      <input type="file" onChange={(e) => handleUpload(e.target.files[0])} />
      
      {jobId && (
        <div>
          <progress value={progress} max="100"></progress>
          <p>Status: {status}</p>
          <p>Progress: {progress}%</p>
          
          {isFinished && (
            <video src={`/api/video/download/${jobId}/result.mp4`} controls />
          )}
        </div>
      )}
    </div>
  );
}
```

---

## 🎯 Progress Data Format

WebSocket sends JSON messages:

### Type: `connected`
```json
{
  "type": "connected",
  "job_id": "uuid-xxx",
  "message": "WebSocket connected..."
}
```

### Type: `progress`
```json
{
  "type": "progress",
  "job_id": "uuid-xxx",
  "status": "processing",
  "progress_percent": 45,
  "result_path": null,
  "error_message": null,
  "processing_time_seconds": 12
}
```

### Type: `finished`
```json
{
  "type": "finished",
  "status": "completed",
  "message": "Job uuid-xxx completed"
}
```

### Type: `error`
```json
{
  "type": "error",
  "message": "Job not found"
}
```

---

## 🔒 Authentication

Nếu cần auth, thêm token vào URL:

```javascript
const ws = new WebSocket(
  `wss://domain/ws/video/progress/${jobId}?token=${authToken}`
);
```

---

## 🌐 CORS & Domain

**✅ Đã config sẵn CORS** trong backend.

FE chỉ cần connect từ:
- `https://adas.aiotlab.edu.vn`
- `http://localhost:3000` (dev)
- Any allowed origin

---

## 📊 So Sánh: Polling vs WebSocket

| Method | Polling (cũ) | WebSocket (mới) |
|--------|--------------|-----------------|
| Realtime | ❌ Delay 2s | ✅ Instant |
| Server load | ❌ High (request mỗi 2s) | ✅ Low (1 connection) |
| Network | ❌ Nhiều requests | ✅ 1 connection |
| Battery (mobile) | ❌ Drain | ✅ Efficient |

---

## 🧪 Testing

### Test WebSocket (Browser Console)

```javascript
const ws = new WebSocket('wss://adas-api.aiotlab.edu.vn/ws/video/progress/test-job-id');

ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log('Message:', JSON.parse(e.data));
ws.onerror = (e) => console.error('Error:', e);
ws.onclose = () => console.log('Closed');
```

### Test với wscat (CLI)

```bash
npm install -g wscat
wscat -c 'wss://adas-api.aiotlab.edu.vn/ws/video/progress/test-job-id'
```

---

## 🐛 Troubleshooting

### WebSocket connection failed

**Lỗi:** `WebSocket connection failed`

**Nguyên nhân:**
- Cloudflare chưa enable WebSocket
- Backend chưa chạy code mới
- Port bị block

**Fix:**
1. Check backend logs: `tail -f backend.log`
2. Check Cloudflare: Enable WebSocket trong settings
3. Test HTTP trước: `GET https://domain/ws/stats`

### Progress không update

**Lỗi:** Progress stuck at 0%

**Nguyên nhân:**
- Job chưa start
- Job ID sai

**Fix:**
```javascript
// Check job status via REST API
const res = await fetch(`/api/video/result/${jobId}`);
const status = await res.json();
console.log(status);
```

---

## ✅ Checklist Deploy

- [ ] Backend code có `video_progress_ws.py`
- [ ] `main.py` đã include router
- [ ] Backend đã restart
- [ ] Test WebSocket endpoint (`/ws/stats` trả về 200)
- [ ] Cloudflare enable WebSocket
- [ ] FE code connect WebSocket
- [ ] Test upload → Progress realtime

---

**Created:** 2026-01-11  
**Status:** ✅ Ready for Frontend Integration
