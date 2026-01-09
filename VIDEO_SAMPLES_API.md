# VIDEO API - COMPLETE GUIDE
**Backend API Documentation for Frontend Integration**

---

## 📋 **TẤT CẢ ENDPOINTS:**

| Method | Endpoint | Mục đích |
|--------|----------|----------|
| POST | `/api/video/upload` | Upload video mới |
| GET | `/api/video/result/{job_id}` | Kiểm tra trạng thái xử lý |
| GET | `/api/video/download/{job_id}/{filename}` | Download video ĐÃ XỬ LÝ |
| GET | `/api/video/list` | **[MỚI]** Lấy danh sách tất cả videos |
| GET | `/api/video/sample/{job_id}/{filename}` | **[MỚI]** Download video GỐC (chưa xử lý) |
| DELETE | `/api/video/job/{job_id}` | Xóa job |
| GET | `/api/video/health` | Health check |

---

## 🆕 **API MỚI - LẤY VIDEO MẪU CHO FRONTEND**

### **1. LIST ALL VIDEOS**

Lấy danh sách tất cả videos đã upload (để làm video mẫu).

#### **Endpoint:**
```http
GET /api/video/list
```

#### **Query Parameters:**
```
limit=10          // Optional: Số lượng videos (default: 10)
offset=0          // Optional: Bỏ qua N videos (pagination)
status=completed  // Optional: Filter theo status (pending, processing, completed, failed)
```

#### **Response:**
```json
{
  "videos": [
    {
      "id": 16,
      "job_id": "9d507862-f5ec-4c7e-a617-153528f5377d",
      "video_filename": "project_video.mp4",
      "video_path": "backend/storage/raw/9d507862-f5ec-4c7e-a617-153528f5377d.mp4",
      "video_size_mb": 24.10,
      "duration_seconds": 50,
      "fps": 25.0,
      "resolution": "1280x720",
      "status": "completed",
      "progress_percent": 100,
      "result_path": "backend/storage/result/9d507862-f5ec-4c7e-a617-153528f5377d_result.mp4",
      "created_at": "2026-01-09T00:36:23.812000",
      "completed_at": "2026-01-09T00:37:20.566000"
    },
    {
      "id": 15,
      "job_id": "abc-123-def-456",
      "video_filename": "test_dashcam.mp4",
      "video_path": "backend/storage/raw/abc-123-def-456.mp4",
      "video_size_mb": 15.5,
      "status": "completed",
      "progress_percent": 100,
      "created_at": "2026-01-08T10:20:00.000000",
      "completed_at": "2026-01-08T10:21:30.000000"
    }
  ],
  "total": 2,
  "limit": 10,
  "offset": 0
}
```

#### **Frontend Example:**
```typescript
async function getVideoSamples() {
  const response = await fetch(
    'https://adas-api.aiotlab.edu.vn/api/video/list?limit=5&status=completed'
  );
  
  const data = await response.json();
  
  // data.videos là array các video đã xử lý xong
  return data.videos;
}

// Usage
const samples = await getVideoSamples();
samples.forEach(video => {
  console.log(`${video.video_filename} - ${video.status}`);
});
```

---

### **2. GET RAW VIDEO (Video Gốc - Chưa Xử Lý)**

Download video gốc chưa qua xử lý (để làm video mẫu so sánh before/after).

#### **Endpoint:**
```http
GET /api/video/sample/{job_id}/{filename}
```

#### **Parameters:**
- `job_id`: Job ID từ database (lấy từ /api/video/list)
- `filename`: Tên file gốc (lấy từ field `video_filename`)

#### **Response:**
```
Binary video file (video/mp4)
Content-Type: video/mp4
Content-Disposition: attachment; filename="project_video.mp4"
```

#### **Frontend Example:**
```typescript
function playRawVideo(jobId: string, filename: string) {
  const videoUrl = `https://adas-api.aiotlab.edu.vn/api/video/sample/${jobId}/${filename}`;
  
  // Hiển thị trong video player
  const videoElement = document.querySelector('video');
  videoElement.src = videoUrl;
  videoElement.play();
}

// Hoặc download
function downloadRawVideo(jobId: string, filename: string) {
  const downloadUrl = `https://adas-api.aiotlab.edu.vn/api/video/sample/${jobId}/${filename}`;
  
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.download = filename;
  link.click();
}
```

---

## 🎯 **USE CASE: HIỂN THỊ VIDEO MẪU TRÊN FRONTEND**

### **Kịch bản: Trang demo với video samples**

```typescript
interface VideoSample {
  jobId: string;
  filename: string;
  rawVideoUrl: string;
  processedVideoUrl: string;
  status: string;
  createdAt: string;
}

class VideoSampleService {
  private baseUrl = 'https://adas-api.aiotlab.edu.vn';

  async getSamples(limit = 5): Promise<VideoSample[]> {
    // 1. Lấy danh sách videos đã hoàn thành
    const response = await fetch(
      `${this.baseUrl}/api/video/list?limit=${limit}&status=completed`
    );
    const data = await response.json();

    // 2. Map thành format dễ dùng cho frontend
    return data.videos.map(video => ({
      jobId: video.job_id,
      filename: video.video_filename,
      rawVideoUrl: `${this.baseUrl}/api/video/sample/${video.job_id}/${video.video_filename}`,
      processedVideoUrl: this.getProcessedVideoUrl(video.job_id, video.video_filename),
      status: video.status,
      createdAt: video.created_at
    }));
  }

  private getProcessedVideoUrl(jobId: string, originalFilename: string): string {
    // Tên file result: original_filename được thay bằng {job_id}_result.mp4
    const resultFilename = originalFilename.replace('.mp4', '_result.mp4');
    return `${this.baseUrl}/api/video/download/${jobId}/${resultFilename}`;
  }
}

// Usage trong React component
function VideoSamplesPage() {
  const [samples, setSamples] = useState<VideoSample[]>([]);

  useEffect(() => {
    const service = new VideoSampleService();
    service.getSamples(10).then(setSamples);
  }, []);

  return (
    <div className="samples-grid">
      {samples.map(sample => (
        <div key={sample.jobId} className="sample-card">
          <h3>{sample.filename}</h3>
          
          <div className="video-compare">
            <div>
              <h4>Before (Raw)</h4>
              <video src={sample.rawVideoUrl} controls />
            </div>
            
            <div>
              <h4>After (Processed)</h4>
              <video src={sample.processedVideoUrl} controls />
            </div>
          </div>
          
          <p>Created: {new Date(sample.createdAt).toLocaleString()}</p>
        </div>
      ))}
    </div>
  );
}
```

---

## 📁 **STORAGE PATHS**

### **Trên Server:**
```bash
# Video gốc (uploaded)
/path/to/backend/storage/raw/{job_id}.mp4
Example: ./backend/storage/raw/9d507862-f5ec-4c7e-a617-153528f5377d.mp4

# Video đã xử lý (processed)
/path/to/backend/storage/result/{job_id}_result.mp4
Example: ./backend/storage/result/9d507862-f5ec-4c7e-a617-153528f5377d_result.mp4
```

### **API URLs:**
```
Raw video:       GET /api/video/sample/{job_id}/{filename}
Processed video: GET /api/video/download/{job_id}/{filename}
```

---

## 🔄 **COMPLETE WORKFLOW**

### **1. Lấy danh sách videos có sẵn:**
```bash
GET /api/video/list?limit=10&status=completed
```

### **2. Hiển thị video gốc:**
```bash
GET /api/video/sample/9d507862-f5ec-4c7e-a617-153528f5377d/project_video.mp4
```

### **3. Hiển thị video đã xử lý:**
```bash
GET /api/video/download/9d507862-f5ec-4c7e-a617-153528f5377d/project_video_result.mp4
```

---

## 📊 **RESPONSE FIELDS REFERENCE**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Database ID |
| `job_id` | string (UUID) | Unique job identifier |
| `video_filename` | string | Original filename |
| `video_path` | string | Storage path (internal) |
| `video_size_mb` | float | File size in MB |
| `duration_seconds` | integer | Video duration |
| `fps` | float | Frames per second |
| `resolution` | string | Video resolution |
| `status` | string | "completed", "processing", etc. |
| `progress_percent` | integer | 0-100 |
| `result_path` | string | Processed video path |
| `created_at` | datetime | Upload time |
| `completed_at` | datetime | Processing completion time |

---

## ⚠️ **IMPORTANT NOTES**

### **1. Video Sample vs Processed:**
- **Sample** = Video gốc (raw/input) - chưa qua AI
- **Download** = Video đã xử lý (result/output) - có bounding boxes, alerts

### **2. Filename Convention:**
```
Raw:       project_video.mp4
Processed: project_video_result.mp4  (thêm _result)
```

### **3. Security:**
- Tất cả endpoints đều public (chưa có auth)
- Planning: Thêm authentication sau

### **4. Performance:**
- Video files có thể lớn (100MB+)
- Nên dùng streaming video player
- Không load toàn bộ video vào memory

---

## 📞 **TESTING**

### **Test với curl:**
```bash
# List videos
curl https://adas-api.aiotlab.edu.vn/api/video/list?limit=5

# Get raw video
curl -O https://adas-api.aiotlab.edu.vn/api/video/sample/JOB_ID/filename.mp4

# Get processed video
curl -O https://adas-api.aiotlab.edu.vn/api/video/download/JOB_ID/filename_result.mp4
```

### **Test trong browser:**
```
https://adas-api.aiotlab.edu.vn/api/video/list
```

---

**Last Updated**: 2026-01-09  
**Version**: 1.1  
**Author**: Backend Team
