"""
Comprehensive Test Suite for ADAS Backend API v3.0
===================================================
Tests for all critical endpoints with valid/invalid scenarios.

Run tests:
    pytest test_adas_api_complete.py -v
    pytest test_adas_api_complete.py::TestVideoUpload -v
    pytest test_adas_api_complete.py -k "test_upload" -v

Requirements:
    pip install pytest pytest-asyncio httpx faker
"""

import pytest
import asyncio
import hashlib
import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, Any
from faker import Faker

# Assuming FastAPI app is available
from backend.app.main import app
from httpx import AsyncClient

fake = Faker()


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
async def client():
    """Create async HTTP client for API testing"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_video_bytes() -> bytes:
    """Create small valid video file (dummy)"""
    # In real tests, use actual small MP4 file
    return b"fake_video_data_mp4" * 1000  # ~16KB


@pytest.fixture
def large_video_bytes() -> bytes:
    """Create oversized video (> 500MB)"""
    return b"x" * (550 * 1024 * 1024)  # 550MB


@pytest.fixture
def sample_image_base64() -> str:
    """Create base64-encoded image for driver monitoring"""
    # Dummy 100x100 black image
    img_data = b'\x00' * (100 * 100 * 3)
    return base64.b64encode(img_data).decode('utf-8')


# ============================================================
# Test Case 1: Video Upload (Success)
# ============================================================

@pytest.mark.asyncio
class TestVideoUpload:
    """Test video upload endpoint"""
    
    async def test_upload_new_video_success(self, client: AsyncClient, sample_video_bytes: bytes):
        """✅ Test uploading a new video successfully"""
        files = {"file": ("test_video.mp4", sample_video_bytes, "video/mp4")}
        
        response = await client.post("/api/v3/videos/upload", files=files)
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "video_id" in data
        assert "sha256" in data
        assert "is_duplicate" in data
        assert "original_filename" in data
        assert "size_bytes" in data
        
        # Validate values
        assert isinstance(data["video_id"], int)
        assert data["video_id"] > 0
        assert len(data["sha256"]) == 64  # SHA256 is 64 hex chars
        assert data["is_duplicate"] is False
        assert data["original_filename"] == "test_video.mp4"
        assert data["size_bytes"] == len(sample_video_bytes)
    
    async def test_upload_duplicate_video(self, client: AsyncClient, sample_video_bytes: bytes):
        """✅ Test uploading same video twice (deduplication)"""
        files = {"file": ("duplicate.mp4", sample_video_bytes, "video/mp4")}
        
        # First upload
        response1 = await client.post("/api/v3/videos/upload", files=files)
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second upload (same file)
        files2 = {"file": ("duplicate.mp4", sample_video_bytes, "video/mp4")}
        response2 = await client.post("/api/v3/videos/upload", files=files2)
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Validate deduplication
        assert data2["is_duplicate"] is True
        assert data2["video_id"] == data1["video_id"]
        assert data2["sha256"] == data1["sha256"]
    
    async def test_upload_oversized_video_error(self, client: AsyncClient, large_video_bytes: bytes):
        """❌ Test uploading video larger than 500MB (should fail)"""
        files = {"file": ("large.mp4", large_video_bytes, "video/mp4")}
        
        response = await client.post("/api/v3/videos/upload", files=files)
        
        assert response.status_code == 413  # Payload Too Large
        data = response.json()
        assert "File too large" in data["detail"]
        assert "500MB" in data["detail"]
    
    async def test_upload_missing_file_error(self, client: AsyncClient):
        """❌ Test upload without file (validation error)"""
        response = await client.post("/api/v3/videos/upload", data={})
        
        assert response.status_code == 422  # Unprocessable Entity
        data = response.json()
        assert "detail" in data
    
    async def test_upload_invalid_format_error(self, client: AsyncClient):
        """❌ Test uploading non-video file"""
        files = {"file": ("document.txt", b"plain text", "text/plain")}
        
        response = await client.post("/api/v3/videos/upload", files=files)
        
        # Should either reject or process (depends on validation)
        # If backend validates format:
        assert response.status_code in [400, 422]


# ============================================================
# Test Case 2: Check Video Exists (Deduplication)
# ============================================================

@pytest.mark.asyncio
class TestVideoCheck:
    """Test video existence check endpoint"""
    
    async def test_check_existing_video(self, client: AsyncClient, sample_video_bytes: bytes):
        """✅ Test checking existing video by SHA256"""
        # First upload a video
        files = {"file": ("test.mp4", sample_video_bytes, "video/mp4")}
        upload_response = await client.post("/api/v3/videos/upload", files=files)
        upload_data = upload_response.json()
        sha256_hash = upload_data["sha256"]
        
        # Now check if it exists
        response = await client.get(f"/api/v3/videos/check?sha256={sha256_hash}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["exists"] is True
        assert data["video_id"] == upload_data["video_id"]
        assert data["sha256"] == sha256_hash
    
    async def test_check_nonexistent_video(self, client: AsyncClient):
        """✅ Test checking non-existent video"""
        fake_hash = "a" * 64  # Fake SHA256
        
        response = await client.get(f"/api/v3/videos/check?sha256={fake_hash}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["exists"] is False
        assert data["video_id"] is None
        assert data["sha256"] is None
    
    async def test_check_invalid_sha256_error(self, client: AsyncClient):
        """❌ Test checking with invalid SHA256 format"""
        invalid_hash = "not_a_valid_sha256"
        
        response = await client.get(f"/api/v3/videos/check?sha256={invalid_hash}")
        
        # Should fail validation (SHA256 must be 64 chars)
        assert response.status_code == 422


# ============================================================
# Test Case 3: Create Job
# ============================================================

@pytest.mark.asyncio
class TestJobCreation:
    """Test job creation endpoint"""
    
    async def test_create_job_success(self, client: AsyncClient, sample_video_bytes: bytes):
        """✅ Test creating processing job for uploaded video"""
        # First upload video
        files = {"file": ("test.mp4", sample_video_bytes, "video/mp4")}
        upload_response = await client.post("/api/v3/videos/upload", files=files)
        video_id = upload_response.json()["video_id"]
        
        # Create job
        response = await client.post(
            "/api/v3/videos/jobs",
            data={
                "video_id": video_id,
                "video_type": "dashcam",
                "priority": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate response
        assert "job_id" in data
        assert "video_id" in data
        assert "status" in data
        assert "priority" in data
        assert "queue_position" in data
        
        assert data["video_id"] == video_id
        assert data["status"] == "pending"
        assert data["priority"] == 5
        assert isinstance(data["queue_position"], int)
    
    async def test_create_job_invalid_video_id_error(self, client: AsyncClient):
        """❌ Test creating job with non-existent video_id"""
        response = await client.post(
            "/api/v3/videos/jobs",
            data={
                "video_id": 99999,  # Non-existent
                "video_type": "dashcam"
            }
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "Video not found" in data["detail"]
    
    async def test_create_job_missing_video_id_error(self, client: AsyncClient):
        """❌ Test creating job without video_id"""
        response = await client.post("/api/v3/videos/jobs", data={})
        
        assert response.status_code == 422  # Validation error


# ============================================================
# Test Case 4: Job Status Polling
# ============================================================

@pytest.mark.asyncio
class TestJobStatus:
    """Test job status polling endpoint"""
    
    async def test_get_job_status_pending(self, client: AsyncClient, sample_video_bytes: bytes):
        """✅ Test getting status of pending job"""
        # Upload video and create job
        files = {"file": ("test.mp4", sample_video_bytes, "video/mp4")}
        upload_response = await client.post("/api/v3/videos/upload", files=files)
        video_id = upload_response.json()["video_id"]
        
        job_response = await client.post(
            "/api/v3/videos/jobs",
            data={"video_id": video_id}
        )
        job_id = job_response.json()["job_id"]
        
        # Get status
        response = await client.get(f"/api/v3/videos/jobs/{job_id}/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["job_id"] == job_id
        assert data["status"] in ["pending", "processing"]
        assert "progress_percent" in data
        assert 0 <= data["progress_percent"] <= 100
    
    async def test_get_job_status_invalid_job_id_error(self, client: AsyncClient):
        """❌ Test getting status with non-existent job_id"""
        fake_job_id = "00000000-0000-0000-0000-000000000000"
        
        response = await client.get(f"/api/v3/videos/jobs/{fake_job_id}/status")
        
        assert response.status_code == 404
        data = response.json()
        assert "Job not found" in data["detail"]


# ============================================================
# Test Case 5: Driver Monitoring
# ============================================================

@pytest.mark.asyncio
class TestDriverMonitoring:
    """Test driver monitoring API"""
    
    async def test_analyze_driver_frame_success(self, client: AsyncClient, sample_image_base64: str):
        """✅ Test analyzing driver frame"""
        response = await client.post(
            "/api/driver-monitor/analyze",
            data={
                "frame": sample_image_base64,
                "camera_id": "cabin_cam_01"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert data["success"] is True
        assert "fatigue_level" in data
        assert "distraction_level" in data
        assert "eyes_closed" in data
        assert "head_pose" in data
        assert "alert_triggered" in data
        assert "recommendations" in data
        
        # Validate ranges
        assert 0 <= data["fatigue_level"] <= 100
        assert 0 <= data["distraction_level"] <= 100
        assert isinstance(data["eyes_closed"], bool)
        assert isinstance(data["alert_triggered"], bool)
        assert isinstance(data["recommendations"], list)
        
        # Validate head pose
        head_pose = data["head_pose"]
        assert "yaw" in head_pose
        assert "pitch" in head_pose
        assert "roll" in head_pose
    
    async def test_analyze_driver_missing_frame_error(self, client: AsyncClient):
        """❌ Test analyzing without frame"""
        response = await client.post(
            "/api/driver-monitor/analyze",
            data={"camera_id": "cabin_cam_01"}
        )
        
        assert response.status_code == 422  # Validation error


# ============================================================
# Test Case 6: Streaming API
# ============================================================

@pytest.mark.asyncio
class TestStreaming:
    """Test real-time streaming API"""
    
    async def test_start_streaming_session_success(self, client: AsyncClient):
        """✅ Test starting streaming session"""
        response = await client.post(
            "/api/stream/start",
            json={
                "source": "webcam",
                "model_id": "yolo11n"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "session_id" in data
        assert "polling_url" in data
        assert "message" in data
        
        # Validate session_id is UUID
        import uuid
        try:
            uuid.UUID(data["session_id"])
        except ValueError:
            pytest.fail("session_id is not a valid UUID")
    
    async def test_start_streaming_invalid_model_error(self, client: AsyncClient):
        """❌ Test starting stream with non-existent model"""
        response = await client.post(
            "/api/stream/start",
            json={
                "source": "webcam",
                "model_id": "nonexistent_model"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    async def test_poll_stream_success(self, client: AsyncClient):
        """✅ Test polling stream for detections"""
        # Start session first
        start_response = await client.post(
            "/api/stream/start",
            json={"source": "webcam", "model_id": "yolo11n"}
        )
        session_id = start_response.json()["session_id"]
        
        # Poll for detections
        response = await client.get(f"/api/stream/poll/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "detections" in data
        assert "fps" in data
        assert "latency_ms" in data
        assert "frame_id" in data
        assert "status" in data
        
        assert isinstance(data["detections"], list)
        assert data["fps"] > 0
        assert data["latency_ms"] >= 0
    
    async def test_stop_stream_success(self, client: AsyncClient):
        """✅ Test stopping streaming session"""
        # Start session
        start_response = await client.post(
            "/api/stream/start",
            json={"source": "webcam", "model_id": "yolo11n"}
        )
        session_id = start_response.json()["session_id"]
        
        # Stop session
        response = await client.post(
            "/api/stream/stop",
            json={"session_id": session_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "message" in data
        assert "total_frames" in data


# ============================================================
# Test Case 7: Model Management
# ============================================================

@pytest.mark.asyncio
class TestModelManagement:
    """Test model management API"""
    
    async def test_list_available_models(self, client: AsyncClient):
        """✅ Test listing available models"""
        response = await client.get("/api/models/available")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "models" in data
        assert "total_models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0
        
        # Validate model structure
        model = data["models"][0]
        assert "id" in model
        assert "name" in model
        assert "downloaded" in model
    
    async def test_get_model_info_success(self, client: AsyncClient):
        """✅ Test getting model info"""
        response = await client.get("/api/models/info/yolo11n")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "model" in data
        
        model = data["model"]
        assert model["id"] == "yolo11n"
        assert "name" in model
        assert "size_mb" in model
    
    async def test_get_model_info_not_found_error(self, client: AsyncClient):
        """❌ Test getting info for non-existent model"""
        response = await client.get("/api/models/info/nonexistent")
        
        assert response.status_code == 404


# ============================================================
# Test Case 8: Dataset Management
# ============================================================

@pytest.mark.asyncio
class TestDatasetManagement:
    """Test dataset management API"""
    
    async def test_list_datasets(self, client: AsyncClient):
        """✅ Test listing datasets"""
        response = await client.get("/api/dataset?limit=10&page=1")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert isinstance(data["data"], list)
    
    async def test_upload_dataset_success(self, client: AsyncClient, sample_video_bytes: bytes):
        """✅ Test uploading dataset item"""
        files = {"file": ("dataset_video.mp4", sample_video_bytes, "video/mp4")}
        data = {
            "description": "Test dataset video",
            "type": "video",
            "tags": "test,highway"
        }
        
        response = await client.post("/api/dataset", files=files, data=data)
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["success"] is True
        assert "data" in result
        assert "id" in result["data"]
        assert result["data"]["filename"] == "dataset_video.mp4"


# ============================================================
# Integration Test: Full Workflow
# ============================================================

@pytest.mark.asyncio
@pytest.mark.slow
class TestFullWorkflow:
    """Test complete upload → process → download workflow"""
    
    async def test_complete_video_processing_workflow(
        self, 
        client: AsyncClient, 
        sample_video_bytes: bytes
    ):
        """✅ Integration test: Upload → Job → Poll → Download"""
        
        # Step 1: Upload video
        files = {"file": ("workflow_test.mp4", sample_video_bytes, "video/mp4")}
        upload_response = await client.post("/api/v3/videos/upload", files=files)
        assert upload_response.status_code == 200
        video_id = upload_response.json()["video_id"]
        
        # Step 2: Create job
        job_response = await client.post(
            "/api/v3/videos/jobs",
            data={"video_id": video_id, "video_type": "dashcam"}
        )
        assert job_response.status_code == 200
        job_id = job_response.json()["job_id"]
        
        # Step 3: Poll status until complete (max 60 seconds)
        max_polls = 20
        for i in range(max_polls):
            status_response = await client.get(f"/api/v3/videos/jobs/{job_id}/status")
            assert status_response.status_code == 200
            status_data = status_response.json()
            
            if status_data["status"] == "completed":
                assert status_data["progress_percent"] == 100
                assert status_data["result_path"] is not None
                break
            elif status_data["status"] == "failed":
                pytest.fail(f"Job failed: {status_data['error_message']}")
            
            await asyncio.sleep(3)  # Wait 3 seconds between polls
        
        else:
            pytest.fail("Job did not complete within timeout")
        
        # Step 4: Download result (if endpoint exists)
        # download_response = await client.get(
        #     f"/api/v3/videos/download/{job_id}/result.mp4"
        # )
        # assert download_response.status_code == 200


# ============================================================
# Performance Tests
# ============================================================

@pytest.mark.asyncio
@pytest.mark.performance
class TestPerformance:
    """Performance and load tests"""
    
    async def test_concurrent_uploads(self, client: AsyncClient, sample_video_bytes: bytes):
        """⚡ Test concurrent video uploads"""
        async def upload_video(n: int):
            files = {"file": (f"concurrent_{n}.mp4", sample_video_bytes, "video/mp4")}
            response = await client.post("/api/v3/videos/upload", files=files)
            return response.status_code == 200
        
        # Upload 5 videos concurrently
        tasks = [upload_video(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(results)
    
    async def test_api_response_time(self, client: AsyncClient):
        """⚡ Test API response time < 100ms"""
        import time
        
        start = time.time()
        response = await client.get("/api/models/available")
        duration = (time.time() - start) * 1000  # ms
        
        assert response.status_code == 200
        assert duration < 100, f"Response took {duration:.2f}ms (should be < 100ms)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
```